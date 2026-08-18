/*
 * main.c - CLI entry point.
 *
 *   ./bpfc --cases <in.jsonl> --out <out.jsonl>
 *   ./bpfc --bench <in.jsonl> --reps N
 *
 * --cases compiles every record and writes one output record per input
 * record, in input order.
 *
 * --bench compiles every record `reps` times, writes nothing to the output
 * file, and prints exactly one JSON line to stdout:
 *   {"elapsed_sec":FLOAT,"cases":N,"reps":R,"compiles":N*R,"sink":INT}
 * `sink` accumulates program lengths so the compile cannot be optimised away.
 *
 * Determinism: no clock, no locale, no randomness on the --cases path.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "filter.h"
#include "jsonio.h"

static double now_sec(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

static void run_cases(const bpfc_caseset_t *cs, FILE *out)
{
    bpf_prog_t prog;
    size_t k;

    bpf_prog_init(&prog);
    for (k = 0; k < cs->n; k++) {
        const bpfc_case_t *c = &cs->v[k];
        const char *err = NULL;

        if (bpfc_compile(c, &prog, &err) == 0)
            json_write_ok(out, c->i, &prog);
        else
            json_write_err(out, c->i, err);
    }
    bpf_prog_free(&prog);
}

static void run_bench(const bpfc_caseset_t *cs, int reps)
{
    bpf_prog_t prog;
    volatile unsigned long sink = 0;
    double t0, el;
    int r;
    size_t k;

    bpf_prog_init(&prog);
    t0 = now_sec();
    for (r = 0; r < reps; r++) {
        for (k = 0; k < cs->n; k++) {
            const bpfc_case_t *c = &cs->v[k];
            const char *err = NULL;
            if (bpfc_compile(c, &prog, &err) == 0)
                sink += (unsigned long)prog.len;
        }
    }
    el = now_sec() - t0;
    bpf_prog_free(&prog);

    printf("{\"elapsed_sec\":%.9f,\"cases\":%zu,\"reps\":%d,\"compiles\":%zu,\"sink\":%lu}\n",
           el, cs->n, reps, cs->n * (size_t)reps, (unsigned long)sink);
}

static void usage(void)
{
    fprintf(stderr, "usage: bpfc --cases <in.jsonl> --out <out.jsonl>\n"
                    "       bpfc --bench <in.jsonl> --reps N\n");
}

int main(int argc, char **argv)
{
    const char *cases_path = NULL, *out_path = NULL, *bench_path = NULL;
    int reps = 1;
    int i;
    bpfc_caseset_t cs;
    FILE *out;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--cases") && i + 1 < argc)      cases_path = argv[++i];
        else if (!strcmp(argv[i], "--out") && i + 1 < argc)   out_path   = argv[++i];
        else if (!strcmp(argv[i], "--bench") && i + 1 < argc) bench_path = argv[++i];
        else if (!strcmp(argv[i], "--reps") && i + 1 < argc)  reps       = atoi(argv[++i]);
        else { fprintf(stderr, "bpfc: unknown argument %s\n", argv[i]); return 2; }
    }

    if (bench_path) {
        bpfc_cases_load(bench_path, &cs);
        run_bench(&cs, reps > 0 ? reps : 1);
        bpfc_cases_free(&cs);
        return 0;
    }

    if (!cases_path || !out_path) { usage(); return 2; }

    bpfc_cases_load(cases_path, &cs);
    out = fopen(out_path, "w");
    if (!out) {
        fprintf(stderr, "bpfc: cannot write %s\n", out_path);
        bpfc_cases_free(&cs);
        return 2;
    }
    run_cases(&cs, out);
    fclose(out);
    bpfc_cases_free(&cs);
    return 0;
}
