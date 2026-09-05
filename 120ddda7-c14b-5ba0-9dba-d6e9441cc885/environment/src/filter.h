/*
 * filter.h - the filter expression front end and its AST.
 *
 * STARTER SCOPE. This is a small fraction of the real filter language:
 *
 *   primitive := [ "src" | "dst" ] ( "host" IPV4 | "port" NUM )
 *              | "ip" | "ip6" | "tcp" | "udp" | "arp"
 *   expr      := expr ("and"|"&&") expr
 *              | expr ("or"|"||") expr
 *              | ("not"|"!") expr
 *              | "(" expr ")"
 *              | primitive
 *
 * Everything outside that grammar is rejected. See parse.c.
 */
#ifndef FILTER_H
#define FILTER_H

#include <stdint.h>

#include "bpf_defs.h"
#include "jsonio.h"

/*
 * The one and only diagnostic this starter can produce. The real compiler has
 * dozens: "illegal port number 99999 > 65535", "invalid IPv4 address '...'",
 * "unknown data link type 101", "unknown port 'ssh'", and so on. Collapsing
 * them all into one string is a deliberate starter weakness.
 *
 * ---------------------------------------------------------------------------
 * CALIBRATION NOTE - read before changing this string.
 *
 * The task brief specified "can't parse filter expression: syntax error".
 * That string is NOT generic: it is libpcap's own verbatim message for a
 * grammar error, so using it scores an EXACT error-string match (1.00 per
 * case) on every syntax-error case instead of the intended near-miss (0.45).
 * Measured against the pinned 1.10.6 oracle on an 894-case calibration
 * corpus, 52% of all upstream rejections carry that exact string. Using it
 * puts C at ~0.167, which breaks both the 0.06-0.10 design band and the
 * CTL_GENERIC_ERROR control obligation in seed/contract.yaml, which requires
 * "at most 0.45 on the error stratum; never full credit".
 *
 * So the string below is generic in fact as well as in intent. To restore the
 * literal brief, swap the two lines - nothing else depends on the wording.
 * ---------------------------------------------------------------------------
 */
#define BPFC_GENERIC_ERROR "syntax error in filter expression"
/* #define BPFC_GENERIC_ERROR "can't parse filter expression: syntax error" */

typedef enum {
    NODE_AND,
    NODE_OR,
    NODE_NOT,
    NODE_ETHERTYPE,   /* val = ethertype at link offset 12          */
    NODE_IPPROTO,     /* val = IP protocol number at offset 23      */
    NODE_HOST,        /* val = IPv4 address, network byte order     */
    NODE_PORT         /* val = TCP/UDP port number                  */
} node_kind_t;

typedef enum {
    DIR_ANY = 0,
    DIR_SRC,
    DIR_DST
} dir_t;

typedef struct node {
    node_kind_t   kind;
    dir_t         dir;
    uint32_t      val;
    struct node  *l;
    struct node  *r;
} node_t;

#define AST_MAX_NODES 256
#define AST_MAX_DEPTH 32

typedef struct {
    node_t  pool[AST_MAX_NODES];
    size_t  used;
} ast_arena_t;

/* Parse `text`. Returns the root on success, NULL on any rejection. */
node_t *filter_parse(const char *text, ast_arena_t *arena);

/* Lower an AST to a cBPF program. Returns 0 on success, -1 on rejection.
 * The program always ends in `ret #snaplen` / `ret #0`. */
int codegen(const node_t *root, int snaplen, bpf_prog_t *out);

/* Front to back: parse then lower. Returns 0 on success. On failure *err is
 * set to a static string and *out is left empty. */
int bpfc_compile(const bpfc_case_t *c, bpf_prog_t *out, const char **err);

#endif /* FILTER_H */
