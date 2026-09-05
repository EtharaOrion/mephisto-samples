/*
 * codegen.c - lower an AST to classic BPF.
 *
 * ---------------------------------------------------------------------------
 * STARTER STRATEGY, and its limitations.
 *
 * Every subexpression is materialised as a 0/1 boolean in the accumulator,
 * spilled to scratch memory, and combined with BPF_AND / BPF_OR / BPF_XOR.
 * The program ends with a single test of the final boolean:
 *
 *     ... evaluate root into A ...
 *     jeq #0, jt -> ret #0, jf -> ret #snaplen
 *     ret #snaplen
 *     ret #0
 *
 * This is easy to write and easy to get right, because no jump ever needs a
 * back patched offset: every branch target is one or two instructions ahead.
 * It is also nothing like what a real filter compiler emits. A real one builds
 * a control flow graph of basic blocks, threads the true and false edges of
 * each test directly to the next test, and never touches scratch memory for a
 * boolean at all. Expect programs roughly twice the reference length.
 *
 * Further limitations:
 *   - DLT_EN10MB layout is assumed for EVERY link type. The `dlt` field is
 *     read and then ignored, so a filter compiled for a raw IP or Linux
 *     cooked capture gets Ethernet offsets anyway.
 *   - `tcp` and `udp` test only the IPv4 protocol byte at offset 23. There is
 *     no ethertype guard and no IPv6 next-header path.
 *   - Ports are read from fixed offsets 34 and 36, i.e. the IPv4 header is
 *     assumed to be exactly 20 bytes and the packet is assumed not to be a
 *     fragment. There is no `ldx 4*([14]&0xf)` header length computation and
 *     no fragment offset check.
 *   - `host` compares only the IPv4 source and destination words at 26 and 30.
 *     ARP sender and target addresses are not considered.
 *   - There is NO optimizer. optimize=0 and optimize=1 return byte identical
 *     programs; no redundant load is folded, no jump is threaded, no
 *     unreachable block is deleted.
 * ---------------------------------------------------------------------------
 */
#include <stdlib.h>
#include <string.h>

#include "filter.h"

/* ------------------------------------------------------------------ */
/* program buffer                                                     */
/* ------------------------------------------------------------------ */

void bpf_prog_init(bpf_prog_t *p)
{
    p->insns = NULL;
    p->len = 0;
    p->cap = 0;
    p->overflow = 0;
}

void bpf_prog_free(bpf_prog_t *p)
{
    free(p->insns);
    bpf_prog_init(p);
}

void bpf_prog_reset(bpf_prog_t *p)
{
    p->len = 0;
    p->overflow = 0;
}

void bpf_emit(bpf_prog_t *p, uint16_t code, uint8_t jt, uint8_t jf, uint32_t k)
{
    bpf_insn_t *ins;

    if (p->overflow) return;
    if (p->len >= BPF_MAXINSNS) { p->overflow = 1; return; }
    if (p->len == p->cap) {
        size_t ncap = p->cap ? p->cap * 2 : 64;
        bpf_insn_t *ni = realloc(p->insns, ncap * sizeof(*ni));
        if (!ni) { p->overflow = 1; return; }
        p->insns = ni;
        p->cap = ncap;
    }
    ins = &p->insns[p->len++];
    ins->code = code;
    ins->jt = jt;
    ins->jf = jf;
    ins->k = k;
}

/* ------------------------------------------------------------------ */
/* opcode shorthands                                                  */
/* ------------------------------------------------------------------ */

#define OP_LDB_ABS  (BPF_LD  | BPF_B | BPF_ABS)   /*  48 */
#define OP_LDH_ABS  (BPF_LD  | BPF_H | BPF_ABS)   /*  40 */
#define OP_LDW_ABS  (BPF_LD  | BPF_W | BPF_ABS)   /*  32 */
#define OP_LD_IMM   (BPF_LD  | BPF_W | BPF_IMM)   /*   0 */
#define OP_LD_MEM   (BPF_LD  | BPF_W | BPF_MEM)   /*  96 */
#define OP_LDX_MEM  (BPF_LDX | BPF_W | BPF_MEM)   /*  97 */
#define OP_ST_MEM   (BPF_ST)                      /*   2 */
#define OP_JEQ_K    (BPF_JMP | BPF_JEQ | BPF_K)   /*  21 */
#define OP_JA       (BPF_JMP | BPF_JA)            /*   5 */
#define OP_AND_X    (BPF_ALU | BPF_AND | BPF_X)   /*  92 */
#define OP_OR_X     (BPF_ALU | BPF_OR  | BPF_X)   /*  76 */
#define OP_XOR_K    (BPF_ALU | BPF_XOR | BPF_K)   /* 164 */
#define OP_RET_K    (BPF_RET | BPF_K)             /*   6 */

/* Ethernet II layout, hardcoded for every link type. */
#define OFF_ETHERTYPE   12
#define OFF_IP_PROTO    23
#define OFF_IP_SRC      26
#define OFF_IP_DST      30
#define OFF_SPORT       34   /* assumes a 20 byte IPv4 header */
#define OFF_DPORT       36

typedef struct {
    bpf_prog_t *p;
    int         failed;
} gen_t;

/*
 * Emit a load and an equality test that leaves 1 in A when the loaded value
 * equals `val`, and 0 otherwise. Five instructions, always:
 *
 *     ld  [off]
 *     jeq #val, jt 0, jf 2      ; false -> ld #0
 *     ld  #1
 *     ja  1
 *     ld  #0
 */
static void gen_test(gen_t *g, uint16_t ldop, uint32_t off, uint32_t val)
{
    bpf_emit(g->p, ldop,      0, 0, off);
    bpf_emit(g->p, OP_JEQ_K,  0, 2, val);
    bpf_emit(g->p, OP_LD_IMM, 0, 0, 1);
    bpf_emit(g->p, OP_JA,     0, 0, 1);
    bpf_emit(g->p, OP_LD_IMM, 0, 0, 0);
}

/* Combine the boolean already in scratch slot `slot` with the one now in A. */
static void gen_combine(gen_t *g, uint16_t aluop, int slot)
{
    bpf_emit(g->p, OP_LDX_MEM, 0, 0, (uint32_t)slot);
    bpf_emit(g->p, aluop,      0, 0, 0);
}

/*
 * Leave the value of `n` as a 0/1 boolean BOTH in A and in scratch slot
 * `slot`, using slots >= slot for any temporaries.
 *
 * Note the `st M[slot]` / `ld M[slot]` pair every node ends with. The reload
 * is dead - the value is already in A - and a single peephole pass would
 * delete it. There is no such pass, which is the whole point: this is what
 * "no optimizer" looks like in the emitted bytes.
 */
static void gen_node(gen_t *g, const node_t *n, int slot)
{
    if (g->failed) return;
    if (slot >= BPF_MEMWORDS) { g->failed = 1; return; }

    switch (n->kind) {
    case NODE_ETHERTYPE:
        gen_test(g, OP_LDH_ABS, OFF_ETHERTYPE, n->val);
        break;

    case NODE_IPPROTO:
        /* No ethertype guard: this is one of the starter's known bugs. */
        gen_test(g, OP_LDB_ABS, OFF_IP_PROTO, n->val);
        break;

    case NODE_HOST:
        if (n->dir == DIR_SRC) {
            gen_test(g, OP_LDW_ABS, OFF_IP_SRC, n->val);
        } else if (n->dir == DIR_DST) {
            gen_test(g, OP_LDW_ABS, OFF_IP_DST, n->val);
        } else {
            gen_test(g, OP_LDW_ABS, OFF_IP_SRC, n->val);
            bpf_emit(g->p, OP_ST_MEM, 0, 0, (uint32_t)slot);
            gen_test(g, OP_LDW_ABS, OFF_IP_DST, n->val);
            gen_combine(g, OP_OR_X, slot);
        }
        break;

    case NODE_PORT:
        if (n->dir == DIR_SRC) {
            gen_test(g, OP_LDH_ABS, OFF_SPORT, n->val);
        } else if (n->dir == DIR_DST) {
            gen_test(g, OP_LDH_ABS, OFF_DPORT, n->val);
        } else {
            gen_test(g, OP_LDH_ABS, OFF_SPORT, n->val);
            bpf_emit(g->p, OP_ST_MEM, 0, 0, (uint32_t)slot);
            gen_test(g, OP_LDH_ABS, OFF_DPORT, n->val);
            gen_combine(g, OP_OR_X, slot);
        }
        break;

    case NODE_NOT:
        gen_node(g, n->l, slot);
        bpf_emit(g->p, OP_XOR_K, 0, 0, 1);
        break;

    case NODE_AND:
    case NODE_OR:
        /* the left operand leaves itself in M[slot] on the way out */
        gen_node(g, n->l, slot);
        gen_node(g, n->r, slot + 1);
        gen_combine(g, n->kind == NODE_AND ? OP_AND_X : OP_OR_X, slot);
        break;

    default:
        g->failed = 1;
        return;
    }

    /* Spill and immediately reload. See the comment above. */
    bpf_emit(g->p, OP_ST_MEM, 0, 0, (uint32_t)slot);
    bpf_emit(g->p, OP_LD_MEM, 0, 0, (uint32_t)slot);
}

/*
 * The accept return. STARTER BUG: this is the traditional 65535 snapshot
 * length, hardcoded. The caller's snaplen is passed in and then ignored, so
 * a capture opened with any other snaplen gets the wrong accept constant.
 */
#define STARTER_SNAPLEN 65535

int codegen(const node_t *root, int snaplen, bpf_prog_t *out)
{
    gen_t g;

    (void)snaplen;

    bpf_prog_reset(out);

    g.p = out;
    g.failed = 0;
    gen_node(&g, root, 0);

    if (g.failed || out->overflow) {
        bpf_prog_reset(out);
        return -1;
    }

    /* A == 0 means the filter is false. */
    bpf_emit(out, OP_JEQ_K, 1, 0, 0);
    bpf_emit(out, OP_RET_K, 0, 0, STARTER_SNAPLEN);
    bpf_emit(out, OP_RET_K, 0, 0, 0);

    if (out->overflow) {
        bpf_prog_reset(out);
        return -1;
    }
    return 0;
}

int bpfc_compile(const bpfc_case_t *c, bpf_prog_t *out, const char **err)
{
    ast_arena_t arena;
    node_t *root;

    /* c->dlt and c->netmask are deliberately unused: the starter has one
     * code path, and it assumes Ethernet. */
    (void)c->dlt;
    (void)c->netmask;
    (void)c->optimize;   /* no optimizer exists, so this changes nothing */

    bpf_prog_reset(out);

    root = filter_parse(c->filter, &arena);
    if (!root) {
        *err = BPFC_GENERIC_ERROR;
        return -1;
    }
    if (codegen(root, c->snaplen, out) != 0) {
        *err = BPFC_GENERIC_ERROR;
        return -1;
    }
    return 0;
}
