/*
 * jsonio.h - JSONL reader and writer for the bpfc invocation contract.
 *
 * Input record, one JSON object per line:
 *   {"i":INT,"dlt":INT,"snaplen":INT,"optimize":0|1,"netmask":UINT32|null,"filter":STRING}
 * `netmask` null means PCAP_NETMASK_UNKNOWN (0xffffffff).
 *
 * Output record, one JSON object per line, in input order:
 *   {"i":INT,"ok":true,"prog":[[code,jt,jf,k],...]}
 *   {"i":INT,"ok":false,"err":"ERROR STRING"}
 *
 * This half of the program is complete and correct. You should not need to
 * touch it; spend your time in parse.c and codegen.c instead.
 */
#ifndef JSONIO_H
#define JSONIO_H

#include <stdint.h>
#include <stdio.h>

#include "bpf_defs.h"

#define NETMASK_UNKNOWN 0xffffffffu

typedef struct {
    long long i;
    int       dlt;
    int       snaplen;
    int       optimize;
    uint32_t  netmask;
    char     *filter;      /* malloc'd, JSON-unescaped, never NULL */
} bpfc_case_t;

typedef struct {
    bpfc_case_t *v;
    size_t       n;
    size_t       cap;
} bpfc_caseset_t;

/* Parse one JSONL line into *c. Returns 0 on success, -1 if the line is not a
 * usable record (blank, malformed, or missing "i" / "dlt" / "filter"). On
 * success the caller owns c->filter. */
int bpfc_case_parse(const char *line, bpfc_case_t *c);

/* Read every record of `path`. Unusable lines are skipped, matching the
 * reference reader. Exits with status 2 if the file cannot be opened. */
void bpfc_cases_load(const char *path, bpfc_caseset_t *out);
void bpfc_cases_free(bpfc_caseset_t *cs);

/* Emit exactly one output record, newline terminated. */
void json_write_ok(FILE *f, long long i, const bpf_prog_t *prog);
void json_write_err(FILE *f, long long i, const char *err);

/* Escape and emit a JSON string literal, quotes included. */
void json_write_string(FILE *f, const char *s);

#endif /* JSONIO_H */
