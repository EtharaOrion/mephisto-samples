/*
 * bpf_defs.h - classic (32-bit) packet-filter instruction encoding.
 *
 * These are the historical BSD cBPF opcode bits. They are reproduced here so
 * that this program depends on nothing but the C standard library: it does not
 * include <pcap.h>, <pcap/bpf.h>, <net/bpf.h> or <linux/filter.h>, and it does
 * not link against libpcap.
 *
 * An instruction is the 4-tuple (code, jt, jf, k), which is exactly the shape
 * the JSON contract wants on the wire.
 */
#ifndef BPF_DEFS_H
#define BPF_DEFS_H

#include <stddef.h>
#include <stdint.h>

/* instruction class (low 3 bits of code) */
#define BPF_LD    0x00
#define BPF_LDX   0x01
#define BPF_ST    0x02
#define BPF_STX   0x03
#define BPF_ALU   0x04
#define BPF_JMP   0x05
#define BPF_RET   0x06
#define BPF_MISC  0x07

/* ld/ldx width */
#define BPF_W     0x00
#define BPF_H     0x08
#define BPF_B     0x10

/* ld/ldx addressing mode */
#define BPF_IMM   0x00
#define BPF_ABS   0x20
#define BPF_IND   0x40
#define BPF_MEM   0x60
#define BPF_LEN   0x80
#define BPF_MSH   0xa0

/* alu operation */
#define BPF_ADD   0x00
#define BPF_SUB   0x10
#define BPF_MUL   0x20
#define BPF_DIV   0x30
#define BPF_OR    0x40
#define BPF_AND   0x50
#define BPF_LSH   0x60
#define BPF_RSH   0x70
#define BPF_NEG   0x80
#define BPF_XOR   0xa0

/* jump operation */
#define BPF_JA    0x00
#define BPF_JEQ   0x10
#define BPF_JGT   0x20
#define BPF_JGE   0x30
#define BPF_JSET  0x40

/* alu/jmp operand source */
#define BPF_K     0x00
#define BPF_X     0x08

/* Scratch memory store has 16 slots, M[0] .. M[15]. */
#define BPF_MEMWORDS 16

/* Refuse to emit anything longer than this. */
#define BPF_MAXINSNS 4096

typedef struct {
    uint16_t code;
    uint8_t  jt;
    uint8_t  jf;
    uint32_t k;
} bpf_insn_t;

typedef struct {
    bpf_insn_t *insns;
    size_t      len;
    size_t      cap;
    int         overflow;   /* set once len would exceed BPF_MAXINSNS */
} bpf_prog_t;

void bpf_prog_init(bpf_prog_t *p);
void bpf_prog_free(bpf_prog_t *p);
void bpf_prog_reset(bpf_prog_t *p);
void bpf_emit(bpf_prog_t *p, uint16_t code, uint8_t jt, uint8_t jf, uint32_t k);

#endif /* BPF_DEFS_H */
