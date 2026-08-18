/*
 * parse.c - hand rolled lexer and recursive descent parser.
 *
 * ---------------------------------------------------------------------------
 * STARTER LIMITATIONS. These are real and they are the point of the exercise.
 *
 *   - Only these primitives exist: ip, ip6, tcp, udp, arp, `host <ipv4>`,
 *     `port <num>`, each optionally prefixed by `src` or `dst`.
 *   - No net / mask / len / gateway / broadcast / multicast / less / greater.
 *   - No portrange, no protochain, no byte slices (`tcp[0:2]`), no arithmetic
 *     or relational operators at all.
 *   - No vlan, mpls, pppoes, geneve, or any other encapsulation keyword.
 *   - No name lookups: `port ssh`, `host localhost`, `proto \tcp` are all
 *     rejected rather than resolved through /etc/services or /etc/hosts.
 *   - No IPv6 literals.
 *   - Numbers are accepted decimal only, and are NOT range checked, so
 *     `port 99999` is happily accepted here even though it is not a port.
 *   - IPv4 literals are parsed leniently: four dot separated decimal numbers,
 *     each truncated to 8 bits, so `300.1.1.1` is accepted as 44.1.1.1.
 *
 * Every rejection produces the same string, BPFC_GENERIC_ERROR. The real
 * compiler distinguishes dozens of diagnostics.
 * ---------------------------------------------------------------------------
 */
#include <stdlib.h>
#include <string.h>

#include "filter.h"

typedef enum {
    T_END,
    T_ID,
    T_NUM,
    T_IPV4,
    T_LPAREN,
    T_RPAREN,
    T_AND,
    T_OR,
    T_NOT,
    T_BAD
} toktype_t;

#define TOK_TEXT_MAX 64

typedef struct {
    toktype_t type;
    char      text[TOK_TEXT_MAX];
    uint32_t  num;    /* T_NUM value, or T_IPV4 address in network order */
} token_t;

typedef struct {
    const char  *src;
    size_t       pos;
    token_t      cur;
    ast_arena_t *arena;
    int          depth;
    int          failed;   /* recoverable: a subexpression did not parse */
    int          fatal;    /* unrecoverable: arena or depth exhausted    */
} parser_t;

/* ------------------------------------------------------------------ */
/* lexer                                                              */
/* ------------------------------------------------------------------ */

static int is_space(int c) { return c == ' ' || c == '\t' || c == '\n' || c == '\r'; }
static int is_digit(int c) { return c >= '0' && c <= '9'; }
static int is_alpha(int c)
{
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_';
}
static int is_word(int c) { return is_alpha(c) || is_digit(c) || c == '-'; }

/*
 * Lenient dotted quad. Requires exactly four decimal groups separated by dots
 * and nothing else, but does not check that each group fits in 8 bits; the
 * low byte is taken. Returns 0 on success.
 */
static int parse_ipv4(const char *t, uint32_t *out)
{
    uint32_t addr = 0;
    int part;
    const char *p = t;

    for (part = 0; part < 4; part++) {
        unsigned long v;
        char *end;
        if (!is_digit((unsigned char)*p)) return -1;
        v = strtoul(p, &end, 10);
        addr = (addr << 8) | (uint32_t)(v & 0xff);
        p = end;
        if (part < 3) {
            if (*p != '.') return -1;
            p++;
        }
    }
    if (*p != '\0') return -1;
    *out = addr;
    return 0;
}

static void lex_next(parser_t *p)
{
    const char *s = p->src;
    size_t i = p->pos;
    size_t start;
    token_t *t = &p->cur;

    memset(t, 0, sizeof(*t));

    while (is_space((unsigned char)s[i])) i++;

    if (s[i] == '\0') { t->type = T_END; p->pos = i; return; }

    if (s[i] == '(') { t->type = T_LPAREN; p->pos = i + 1; return; }
    if (s[i] == ')') { t->type = T_RPAREN; p->pos = i + 1; return; }
    if (s[i] == '!') { t->type = T_NOT;    p->pos = i + 1; return; }
    if (s[i] == '&' && s[i + 1] == '&') { t->type = T_AND; p->pos = i + 2; return; }
    if (s[i] == '|' && s[i + 1] == '|') { t->type = T_OR;  p->pos = i + 2; return; }

    if (is_digit((unsigned char)s[i])) {
        start = i;
        while (is_digit((unsigned char)s[i]) || s[i] == '.') i++;
        if (i - start >= TOK_TEXT_MAX) { t->type = T_BAD; p->pos = i; return; }
        memcpy(t->text, s + start, i - start);
        t->text[i - start] = '\0';
        p->pos = i;
        if (strchr(t->text, '.')) {
            if (parse_ipv4(t->text, &t->num) != 0) { t->type = T_BAD; return; }
            t->type = T_IPV4;
        } else {
            t->num = (uint32_t)strtoul(t->text, NULL, 10);
            t->type = T_NUM;
        }
        return;
    }

    if (is_alpha((unsigned char)s[i])) {
        start = i;
        while (is_word((unsigned char)s[i])) i++;
        if (i - start >= TOK_TEXT_MAX) { t->type = T_BAD; p->pos = i; return; }
        memcpy(t->text, s + start, i - start);
        t->text[i - start] = '\0';
        p->pos = i;
        if      (!strcmp(t->text, "and")) t->type = T_AND;
        else if (!strcmp(t->text, "or"))  t->type = T_OR;
        else if (!strcmp(t->text, "not")) t->type = T_NOT;
        else                              t->type = T_ID;
        return;
    }

    /* Anything else - '[', ']', '<', '>', '=', '/', ':', ':' in an IPv6
     * literal, a backslash escaped protocol name - is simply not lexable. */
    t->type = T_BAD;
    p->pos = i + 1;
}

/* ------------------------------------------------------------------ */
/* arena                                                              */
/* ------------------------------------------------------------------ */

static node_t *node_new(parser_t *p, node_kind_t kind)
{
    node_t *n;
    if (p->arena->used >= AST_MAX_NODES) { p->fatal = p->failed = 1; return NULL; }
    n = &p->arena->pool[p->arena->used++];
    memset(n, 0, sizeof(*n));
    n->kind = kind;
    return n;
}

/* ------------------------------------------------------------------ */
/* recursive descent                                                  */
/* ------------------------------------------------------------------ */

static node_t *parse_or(parser_t *p);

/*
 * primitive := [ "src" | "dst" ] ( "host" IPV4 | "port" NUM )
 *            | "ip" | "ip6" | "tcp" | "udp" | "arp"
 */
static node_t *parse_primitive(parser_t *p)
{
    dir_t dir = DIR_ANY;
    node_t *n;

    if (p->cur.type != T_ID) { p->failed = 1; return NULL; }

    if (!strcmp(p->cur.text, "src")) { dir = DIR_SRC; lex_next(p); }
    else if (!strcmp(p->cur.text, "dst")) { dir = DIR_DST; lex_next(p); }

    if (p->cur.type != T_ID) { p->failed = 1; return NULL; }

    if (!strcmp(p->cur.text, "host")) {
        lex_next(p);
        if (p->cur.type != T_IPV4) { p->failed = 1; return NULL; }
        n = node_new(p, NODE_HOST);
        if (!n) return NULL;
        n->dir = dir;
        n->val = p->cur.num;
        lex_next(p);
        return n;
    }

    if (!strcmp(p->cur.text, "port")) {
        lex_next(p);
        /* No range check: a port of 99999 is accepted here. */
        if (p->cur.type != T_NUM) { p->failed = 1; return NULL; }
        n = node_new(p, NODE_PORT);
        if (!n) return NULL;
        n->dir = dir;
        n->val = p->cur.num;
        lex_next(p);
        return n;
    }

    /* A bare protocol keyword takes no direction qualifier. */
    if (dir != DIR_ANY) { p->failed = 1; return NULL; }

    if (!strcmp(p->cur.text, "ip"))  { n = node_new(p, NODE_ETHERTYPE); if (n) n->val = 0x0800; }
    else if (!strcmp(p->cur.text, "ip6")) { n = node_new(p, NODE_ETHERTYPE); if (n) n->val = 0x86dd; }
    else if (!strcmp(p->cur.text, "arp")) { n = node_new(p, NODE_ETHERTYPE); if (n) n->val = 0x0806; }
    else if (!strcmp(p->cur.text, "tcp")) { n = node_new(p, NODE_IPPROTO);   if (n) n->val = 6; }
    else if (!strcmp(p->cur.text, "udp")) { n = node_new(p, NODE_IPPROTO);   if (n) n->val = 17; }
    else { p->failed = 1; return NULL; }

    if (!n) return NULL;
    lex_next(p);
    return n;
}

static node_t *parse_unary(parser_t *p)
{
    node_t *n;

    if (++p->depth > AST_MAX_DEPTH) { p->fatal = p->failed = 1; return NULL; }

    if (p->cur.type == T_NOT) {
        node_t *sub;
        lex_next(p);
        sub = parse_unary(p);
        if (!sub) { p->depth--; return NULL; }
        n = node_new(p, NODE_NOT);
        if (!n) { p->depth--; return NULL; }
        n->l = sub;
        p->depth--;
        return n;
    }

    if (p->cur.type == T_LPAREN) {
        lex_next(p);
        n = parse_or(p);
        if (!n) { p->depth--; return NULL; }
        /* An unclosed group is tolerated: see filter_parse. */
        if (p->cur.type == T_RPAREN) lex_next(p);
        p->depth--;
        return n;
    }

    n = parse_primitive(p);
    p->depth--;
    return n;
}

static node_t *parse_and(parser_t *p)
{
    node_t *lhs = parse_unary(p);
    if (!lhs) return NULL;

    while (p->cur.type == T_AND) {
        node_t *rhs, *n;
        lex_next(p);
        rhs = parse_unary(p);
        if (!rhs) {
            if (p->fatal) return NULL;
            p->failed = 0;      /* best effort: drop the dangling operator */
            return lhs;
        }
        n = node_new(p, NODE_AND);
        if (!n) return NULL;
        n->l = lhs;
        n->r = rhs;
        lhs = n;
    }
    return lhs;
}

static node_t *parse_or(parser_t *p)
{
    node_t *lhs = parse_and(p);
    if (!lhs) return NULL;

    while (p->cur.type == T_OR) {
        node_t *rhs, *n;
        lex_next(p);
        rhs = parse_and(p);
        if (!rhs) {
            if (p->fatal) return NULL;
            p->failed = 0;      /* best effort: drop the dangling operator */
            return lhs;
        }
        n = node_new(p, NODE_OR);
        if (!n) return NULL;
        n->l = lhs;
        n->r = rhs;
        lhs = n;
    }
    return lhs;
}

node_t *filter_parse(const char *text, ast_arena_t *arena)
{
    parser_t p;
    node_t *root;

    memset(&p, 0, sizeof(p));
    p.src = text;
    p.pos = 0;
    p.arena = arena;
    arena->used = 0;

    lex_next(&p);

    /* An empty expression is rejected here. The real compiler treats it as
     * "accept everything". */
    if (p.cur.type == T_END) return NULL;

    root = parse_or(&p);
    if (!root || p.fatal) return NULL;

    /* NOTE: whatever is left over is silently discarded. This parser stops at
     * the first complete expression and never checks that it reached the end
     * of the input, so `tcp port 80` compiles as plain `tcp`, and `ip)` and
     * `tcp 80` are accepted rather than reported. The real compiler requires
     * the whole expression to be consumed. */
    return root;
}
