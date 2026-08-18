/*
 * jsonio.c - JSONL reader and writer. Complete and correct; leave it alone.
 *
 * The reader is a real (if small) JSON object scanner rather than a substring
 * search: it walks the object key by key and skips values structurally, so a
 * filter expression containing braces, brackets, colons, commas or escaped
 * quotes cannot be mistaken for record structure.
 */
#include <stdlib.h>
#include <string.h>

#include "jsonio.h"

/* ------------------------------------------------------------------ */
/* scanner                                                            */
/* ------------------------------------------------------------------ */

typedef struct {
    const char *p;
} jscan_t;

static void js_ws(jscan_t *s)
{
    while (*s->p == ' ' || *s->p == '\t' || *s->p == '\n' ||
           *s->p == '\r' || *s->p == '\f' || *s->p == '\v')
        s->p++;
}

/* Append one Unicode scalar to buf as UTF-8. */
static void utf8_put(char *buf, size_t *o, unsigned long cp)
{
    if (cp < 0x80) {
        buf[(*o)++] = (char)cp;
    } else if (cp < 0x800) {
        buf[(*o)++] = (char)(0xc0 | (cp >> 6));
        buf[(*o)++] = (char)(0x80 | (cp & 0x3f));
    } else if (cp < 0x10000) {
        buf[(*o)++] = (char)(0xe0 | (cp >> 12));
        buf[(*o)++] = (char)(0x80 | ((cp >> 6) & 0x3f));
        buf[(*o)++] = (char)(0x80 | (cp & 0x3f));
    } else {
        buf[(*o)++] = (char)(0xf0 | (cp >> 18));
        buf[(*o)++] = (char)(0x80 | ((cp >> 12) & 0x3f));
        buf[(*o)++] = (char)(0x80 | ((cp >> 6) & 0x3f));
        buf[(*o)++] = (char)(0x80 | (cp & 0x3f));
    }
}

static int hex4(const char *p, unsigned long *out)
{
    unsigned long v = 0;
    int i;
    for (i = 0; i < 4; i++) {
        char c = p[i];
        v <<= 4;
        if (c >= '0' && c <= '9')      v |= (unsigned long)(c - '0');
        else if (c >= 'a' && c <= 'f') v |= (unsigned long)(c - 'a' + 10);
        else if (c >= 'A' && c <= 'F') v |= (unsigned long)(c - 'A' + 10);
        else return -1;
    }
    *out = v;
    return 0;
}

/*
 * Parse a JSON string starting at the opening quote. On success *out is a
 * freshly malloc'd, unescaped, NUL-terminated C string.
 *
 * The output can never be longer than the input, because every escape
 * sequence is at least as long as the bytes it produces (\uXXXX is 6 input
 * bytes and yields at most 3 UTF-8 bytes; a surrogate pair is 12 input bytes
 * and yields 4), so one allocation sized to the remaining input is enough.
 */
static int js_string(jscan_t *s, char **out)
{
    const char *p = s->p;
    char *buf;
    size_t o = 0;

    if (*p != '"') return -1;
    p++;

    buf = malloc(strlen(p) + 1);
    if (!buf) return -1;

    while (*p && *p != '"') {
        if (*p != '\\') {
            buf[o++] = *p++;
            continue;
        }
        p++;
        switch (*p) {
        case '"':  buf[o++] = '"';  p++; break;
        case '\\': buf[o++] = '\\'; p++; break;
        case '/':  buf[o++] = '/';  p++; break;
        case 'b':  buf[o++] = '\b'; p++; break;
        case 'f':  buf[o++] = '\f'; p++; break;
        case 'n':  buf[o++] = '\n'; p++; break;
        case 'r':  buf[o++] = '\r'; p++; break;
        case 't':  buf[o++] = '\t'; p++; break;
        case 'u': {
            unsigned long cp;
            if (hex4(p + 1, &cp) != 0) { free(buf); return -1; }
            p += 5;
            if (cp >= 0xd800 && cp <= 0xdbff && p[0] == '\\' && p[1] == 'u') {
                unsigned long lo;
                if (hex4(p + 2, &lo) == 0 && lo >= 0xdc00 && lo <= 0xdfff) {
                    cp = 0x10000 + ((cp - 0xd800) << 10) + (lo - 0xdc00);
                    p += 6;
                }
            }
            utf8_put(buf, &o, cp);
            break;
        }
        default:
            free(buf);
            return -1;
        }
    }
    if (*p != '"') { free(buf); return -1; }

    buf[o] = '\0';
    s->p = p + 1;
    *out = buf;
    return 0;
}

/* Numbers in this schema are integral. `is_null` reports a JSON null. */
static int js_number(jscan_t *s, long long *sv, unsigned long long *uv, int *is_null)
{
    const char *p = s->p;
    char *end;

    *is_null = 0;
    if (strncmp(p, "null", 4) == 0) { *is_null = 1; s->p = p + 4; return 0; }

    if (*p == '-') {
        long long n = strtoll(p, &end, 10);
        if (end == p) return -1;
        *sv = n;
        *uv = (unsigned long long)n;
    } else {
        unsigned long long n = strtoull(p, &end, 10);
        if (end == p) return -1;
        *uv = n;
        *sv = (long long)n;
    }
    /* tolerate (and discard) a fractional or exponent tail */
    while (*end == '.' || *end == 'e' || *end == 'E' || *end == '+' ||
           *end == '-' || (*end >= '0' && *end <= '9'))
        end++;
    s->p = end;
    return 0;
}

static int js_skip_value(jscan_t *s);

static int js_skip_container(jscan_t *s, char open, char close)
{
    if (*s->p != open) return -1;
    s->p++;
    js_ws(s);
    if (*s->p == close) { s->p++; return 0; }
    for (;;) {
        if (open == '{') {
            char *key = NULL;
            js_ws(s);
            if (js_string(s, &key) != 0) return -1;
            free(key);
            js_ws(s);
            if (*s->p != ':') return -1;
            s->p++;
        }
        js_ws(s);
        if (js_skip_value(s) != 0) return -1;
        js_ws(s);
        if (*s->p == ',') { s->p++; continue; }
        if (*s->p == close) { s->p++; return 0; }
        return -1;
    }
}

static int js_skip_value(jscan_t *s)
{
    js_ws(s);
    switch (*s->p) {
    case '"': {
        char *tmp = NULL;
        if (js_string(s, &tmp) != 0) return -1;
        free(tmp);
        return 0;
    }
    case '{': return js_skip_container(s, '{', '}');
    case '[': return js_skip_container(s, '[', ']');
    case 't': if (strncmp(s->p, "true", 4)) return -1;  s->p += 4; return 0;
    case 'f': if (strncmp(s->p, "false", 5)) return -1; s->p += 5; return 0;
    case 'n': if (strncmp(s->p, "null", 4)) return -1;  s->p += 4; return 0;
    default: {
        long long sv; unsigned long long uv; int nul;
        return js_number(s, &sv, &uv, &nul);
    }
    }
}

/* ------------------------------------------------------------------ */
/* record parsing                                                     */
/* ------------------------------------------------------------------ */

int bpfc_case_parse(const char *line, bpfc_case_t *c)
{
    jscan_t s;
    int have_i = 0, have_dlt = 0;

    memset(c, 0, sizeof(*c));
    c->snaplen  = 262144;
    c->optimize = 1;
    c->netmask  = NETMASK_UNKNOWN;
    c->filter   = NULL;

    s.p = line;
    js_ws(&s);
    if (*s.p != '{') return -1;
    s.p++;
    js_ws(&s);

    if (*s.p == '}') goto finish;

    for (;;) {
        char *key = NULL;
        long long sv;
        unsigned long long uv;
        int nul;

        js_ws(&s);
        if (js_string(&s, &key) != 0) goto fail;
        js_ws(&s);
        if (*s.p != ':') { free(key); goto fail; }
        s.p++;
        js_ws(&s);

        if (!strcmp(key, "filter")) {
            char *val = NULL;
            if (*s.p != '"' || js_string(&s, &val) != 0) { free(key); goto fail; }
            free(c->filter);
            c->filter = val;
        } else if (!strcmp(key, "i")) {
            if (js_number(&s, &sv, &uv, &nul) != 0) { free(key); goto fail; }
            if (!nul) { c->i = sv; have_i = 1; }
        } else if (!strcmp(key, "dlt")) {
            if (js_number(&s, &sv, &uv, &nul) != 0) { free(key); goto fail; }
            if (!nul) { c->dlt = (int)sv; have_dlt = 1; }
        } else if (!strcmp(key, "snaplen")) {
            if (js_number(&s, &sv, &uv, &nul) != 0) { free(key); goto fail; }
            if (!nul) c->snaplen = (int)sv;
        } else if (!strcmp(key, "optimize")) {
            if (js_number(&s, &sv, &uv, &nul) != 0) { free(key); goto fail; }
            if (!nul) c->optimize = (int)sv;
        } else if (!strcmp(key, "netmask")) {
            if (js_number(&s, &sv, &uv, &nul) != 0) { free(key); goto fail; }
            c->netmask = nul ? NETMASK_UNKNOWN : (uint32_t)uv;
        } else {
            if (js_skip_value(&s) != 0) { free(key); goto fail; }
        }
        free(key);

        js_ws(&s);
        if (*s.p == ',') { s.p++; continue; }
        if (*s.p == '}') { s.p++; break; }
        goto fail;
    }

finish:
    if (!have_i || !have_dlt || c->filter == NULL) goto fail;
    return 0;

fail:
    free(c->filter);
    c->filter = NULL;
    return -1;
}

/* ------------------------------------------------------------------ */
/* file loading                                                       */
/* ------------------------------------------------------------------ */

/* Read one line of arbitrary length. Returns -1 at EOF with nothing read. */
static int read_line(FILE *f, char **buf, size_t *cap)
{
    size_t len = 0;
    int ch;

    if (*cap == 0) {
        *cap = 4096;
        *buf = malloc(*cap);
        if (!*buf) { *cap = 0; return -1; }
    }
    for (;;) {
        ch = fgetc(f);
        if (ch == EOF) break;
        if (len + 2 > *cap) {
            size_t ncap = *cap * 2;
            char *nb = realloc(*buf, ncap);
            if (!nb) return -1;
            *buf = nb;
            *cap = ncap;
        }
        if (ch == '\n') break;
        (*buf)[len++] = (char)ch;
    }
    if (ch == EOF && len == 0) return -1;
    (*buf)[len] = '\0';
    return 0;
}

void bpfc_cases_load(const char *path, bpfc_caseset_t *out)
{
    FILE *f;
    char *line = NULL;
    size_t cap = 0;

    out->v = NULL;
    out->n = 0;
    out->cap = 0;

    f = fopen(path, "r");
    if (!f) {
        fprintf(stderr, "bpfc: cannot open %s\n", path);
        exit(2);
    }
    while (read_line(f, &line, &cap) == 0) {
        bpfc_case_t c;
        if (line[0] == '\0') continue;
        if (bpfc_case_parse(line, &c) != 0) continue;
        if (out->n == out->cap) {
            size_t ncap = out->cap ? out->cap * 2 : 1024;
            bpfc_case_t *nv = realloc(out->v, ncap * sizeof(*nv));
            if (!nv) { fprintf(stderr, "bpfc: out of memory\n"); exit(2); }
            out->v = nv;
            out->cap = ncap;
        }
        out->v[out->n++] = c;
    }
    free(line);
    fclose(f);
}

void bpfc_cases_free(bpfc_caseset_t *cs)
{
    size_t i;
    for (i = 0; i < cs->n; i++)
        free(cs->v[i].filter);
    free(cs->v);
    cs->v = NULL;
    cs->n = cs->cap = 0;
}

/* ------------------------------------------------------------------ */
/* output                                                             */
/* ------------------------------------------------------------------ */

void json_write_string(FILE *f, const char *s)
{
    const unsigned char *p;

    fputc('"', f);
    for (p = (const unsigned char *)s; *p; p++) {
        switch (*p) {
        case '"':  fputs("\\\"", f); break;
        case '\\': fputs("\\\\", f); break;
        case '\n': fputs("\\n", f);  break;
        case '\r': fputs("\\r", f);  break;
        case '\t': fputs("\\t", f);  break;
        case '\b': fputs("\\b", f);  break;
        case '\f': fputs("\\f", f);  break;
        default:
            if (*p < 0x20) fprintf(f, "\\u%04x", *p);
            else fputc((int)*p, f);
        }
    }
    fputc('"', f);
}

void json_write_ok(FILE *f, long long i, const bpf_prog_t *prog)
{
    size_t j;

    fprintf(f, "{\"i\":%lld,\"ok\":true,\"prog\":[", i);
    for (j = 0; j < prog->len; j++) {
        const bpf_insn_t *ins = &prog->insns[j];
        fprintf(f, "%s[%u,%u,%u,%lu]", j ? "," : "",
                (unsigned)ins->code, (unsigned)ins->jt,
                (unsigned)ins->jf, (unsigned long)ins->k);
    }
    fputs("]}\n", f);
}

void json_write_err(FILE *f, long long i, const char *err)
{
    fprintf(f, "{\"i\":%lld,\"ok\":false,\"err\":", i);
    json_write_string(f, err);
    fputs("}\n", f);
}
