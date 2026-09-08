#define _POSIX_C_SOURCE 200809L

#include "rasterlab.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *USAGE =
    "usage: rasterlab <command> [args]\n"
    "  rasterlab info <in.rlr>\n"
    "  rasterlab checksum <in.rlr>\n"
    "  rasterlab convert -f <format> <in.rlr> <out.rlr>\n"
    "  rasterlab resize -w <width> -h <height> -k <kernel> <in.rlr> <out.rlr>\n"
    "  rasterlab chain <spec> <in.rlr> <out.rlr>\n";

static int fail_usage(void) {
    fputs(USAGE, stderr);
    return RL_ERR_USAGE;
}

static int fail_read(const char *path, rl_status st) {
    if (st == RL_ERR_UNREADABLE) {
        fprintf(stderr, "rasterlab: cannot open '%s'\n", path);
    } else if (st == RL_ERR_UNSUPPORTED) {
        fprintf(stderr, "rasterlab: unsupported container '%s'\n", path);
    } else {
        fprintf(stderr, "rasterlab: corrupt container '%s'\n", path);
    }
    return (int)st;
}

static int fail_write(const char *path) {
    fprintf(stderr, "rasterlab: cannot write '%s'\n", path);
    return RL_ERR_UNREADABLE;
}

static int parse_u32(const char *s, uint32_t *out) {
    if (*s == '\0') {
        return 0;
    }
    uint32_t v = 0;
    for (const char *p = s; *p; p++) {
        if (*p < '0' || *p > '9') {
            return 0;
        }
        if (v > 429496729u) {
            return 0;
        }
        v = v * 10u + (uint32_t)(*p - '0');
    }
    *out = v;
    return 1;
}

static int cmd_info(int argc, char **argv) {
    if (argc != 1) {
        return fail_usage();
    }
    rl_image img;
    rl_status st = rl_read_file(argv[0], &img);
    if (st != RL_OK) {
        return fail_read(argv[0], st);
    }
    printf("file: %s\n", argv[0]);
    printf("format: %s (%d)\n", rl_format_name(img.fmt), (int)img.fmt);
    printf("width: %u\n", img.width);
    printf("height: %u\n", img.height);
    printf("planes: %d\n", img.plane_count);
    size_t payload = 0;
    int channels = img.plane_count == 1 ? rl_format_channels(img.fmt) : 1;
    for (int p = 0; p < img.plane_count; p++) {
        size_t bytes =
            (size_t)img.planes[p].w * img.planes[p].h * (size_t)channels;
        printf("plane %d: %ux%u %zu bytes\n", p, img.planes[p].w,
               img.planes[p].h, bytes);
        payload += bytes;
    }
    printf("payload: %zu bytes\n", payload);
    printf("crc32: %08x\n", rl_container_crc(&img));
    rl_image_free(&img);
    return RL_OK;
}

static int cmd_checksum(int argc, char **argv) {
    if (argc != 1) {
        return fail_usage();
    }
    rl_image img;
    rl_status st = rl_read_file(argv[0], &img);
    if (st != RL_OK) {
        return fail_read(argv[0], st);
    }
    printf("crc32: %08x\n", rl_container_crc(&img));
    int channels = img.plane_count == 1 ? rl_format_channels(img.fmt) : 1;
    for (int p = 0; p < img.plane_count; p++) {
        size_t bytes =
            (size_t)img.planes[p].w * img.planes[p].h * (size_t)channels;
        printf("plane %d: %08x\n", p, rl_plane_sum(img.planes[p].data, bytes));
    }
    rl_image_free(&img);
    return RL_OK;
}

static int cmd_convert(int argc, char **argv) {
    if (argc != 4 || strcmp(argv[0], "-f") != 0) {
        return fail_usage();
    }
    rl_format fmt;
    if (!rl_format_parse(argv[1], &fmt)) {
        fprintf(stderr, "rasterlab: unsupported format '%s'\n", argv[1]);
        return RL_ERR_UNSUPPORTED;
    }
    rl_image src;
    rl_status st = rl_read_file(argv[2], &src);
    if (st != RL_OK) {
        return fail_read(argv[2], st);
    }
    rl_image dst;
    st = rl_convert(&src, fmt, &dst);
    rl_image_free(&src);
    if (st != RL_OK) {
        fprintf(stderr, "rasterlab: conversion failed\n");
        return (int)st;
    }
    st = rl_write_file(argv[3], &dst);
    rl_image_free(&dst);
    if (st != RL_OK) {
        return fail_write(argv[3]);
    }
    return RL_OK;
}

static int cmd_resize(int argc, char **argv) {
    if (argc != 8 || strcmp(argv[0], "-w") != 0 || strcmp(argv[2], "-h") != 0 ||
        strcmp(argv[4], "-k") != 0) {
        return fail_usage();
    }
    uint32_t w;
    uint32_t h;
    if (!parse_u32(argv[1], &w) || !parse_u32(argv[3], &h)) {
        return fail_usage();
    }
    if (w == 0 || h == 0 || w > RL_MAX_DIM || h > RL_MAX_DIM) {
        fprintf(stderr, "rasterlab: unsupported dimensions '%ux%u'\n", w, h);
        return RL_ERR_UNSUPPORTED;
    }
    rl_kernel k;
    if (!rl_kernel_parse(argv[5], &k)) {
        fprintf(stderr, "rasterlab: unsupported kernel '%s'\n", argv[5]);
        return RL_ERR_UNSUPPORTED;
    }
    rl_image src;
    rl_status st = rl_read_file(argv[6], &src);
    if (st != RL_OK) {
        return fail_read(argv[6], st);
    }
    rl_image dst;
    st = rl_resize(&src, w, h, k, &dst);
    rl_image_free(&src);
    if (st != RL_OK) {
        fprintf(stderr, "rasterlab: resize failed\n");
        return (int)st;
    }
    st = rl_write_file(argv[7], &dst);
    rl_image_free(&dst);
    if (st != RL_OK) {
        return fail_write(argv[7]);
    }
    return RL_OK;
}

/*
 * chain spec grammar (single argv token):
 *   spec    := op (';' op)*
 *   op      := "convert:" format
 *            | "resize:" width 'x' height ':' kernel
 * Ops apply left to right; each op consumes the previous op's output.
 */
static int apply_chain_op(rl_image *cur, const char *op) {
    if (strncmp(op, "convert:", 8) == 0) {
        rl_format fmt;
        if (!rl_format_parse(op + 8, &fmt)) {
            fprintf(stderr, "rasterlab: unsupported format '%s'\n", op + 8);
            return RL_ERR_UNSUPPORTED;
        }
        rl_image next;
        rl_status st = rl_convert(cur, fmt, &next);
        if (st != RL_OK) {
            fprintf(stderr, "rasterlab: conversion failed\n");
            return (int)st;
        }
        rl_image_free(cur);
        *cur = next;
        return RL_OK;
    }
    if (strncmp(op, "resize:", 7) == 0) {
        char buf[128];
        if (strlen(op + 7) >= sizeof(buf)) {
            return fail_usage();
        }
        strcpy(buf, op + 7);
        char *x = strchr(buf, 'x');
        char *colon = strchr(buf, ':');
        if (!x || !colon || colon < x) {
            return fail_usage();
        }
        *x = '\0';
        *colon = '\0';
        uint32_t w;
        uint32_t h;
        if (!parse_u32(buf, &w) || !parse_u32(x + 1, &h)) {
            return fail_usage();
        }
        if (w == 0 || h == 0 || w > RL_MAX_DIM || h > RL_MAX_DIM) {
            fprintf(stderr, "rasterlab: unsupported dimensions '%ux%u'\n", w, h);
            return RL_ERR_UNSUPPORTED;
        }
        rl_kernel k;
        if (!rl_kernel_parse(colon + 1, &k)) {
            fprintf(stderr, "rasterlab: unsupported kernel '%s'\n", colon + 1);
            return RL_ERR_UNSUPPORTED;
        }
        rl_image next;
        rl_status st = rl_resize(cur, w, h, k, &next);
        if (st != RL_OK) {
            fprintf(stderr, "rasterlab: resize failed\n");
            return (int)st;
        }
        rl_image_free(cur);
        *cur = next;
        return RL_OK;
    }
    return fail_usage();
}

static int cmd_chain(int argc, char **argv) {
    if (argc != 3) {
        return fail_usage();
    }
    rl_image cur;
    rl_status st = rl_read_file(argv[1], &cur);
    if (st != RL_OK) {
        return fail_read(argv[1], st);
    }
    char *spec = (char *)malloc(strlen(argv[0]) + 1);
    if (!spec) {
        rl_image_free(&cur);
        return RL_ERR_CORRUPT;
    }
    strcpy(spec, argv[0]);
    int rc = RL_OK;
    char *save = NULL;
    for (char *op = strtok_r(spec, ";", &save); op;
         op = strtok_r(NULL, ";", &save)) {
        rc = apply_chain_op(&cur, op);
        if (rc != RL_OK) {
            break;
        }
    }
    free(spec);
    if (rc != RL_OK) {
        rl_image_free(&cur);
        return rc;
    }
    st = rl_write_file(argv[2], &cur);
    rl_image_free(&cur);
    if (st != RL_OK) {
        return fail_write(argv[2]);
    }
    return RL_OK;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        return fail_usage();
    }
    if (strcmp(argv[1], "info") == 0) {
        return cmd_info(argc - 2, argv + 2);
    }
    if (strcmp(argv[1], "checksum") == 0) {
        return cmd_checksum(argc - 2, argv + 2);
    }
    if (strcmp(argv[1], "convert") == 0) {
        return cmd_convert(argc - 2, argv + 2);
    }
    if (strcmp(argv[1], "resize") == 0) {
        return cmd_resize(argc - 2, argv + 2);
    }
    if (strcmp(argv[1], "chain") == 0) {
        return cmd_chain(argc - 2, argv + 2);
    }
    fprintf(stderr, "rasterlab: unknown command '%s'\n", argv[1]);
    return RL_ERR_USAGE;
}
