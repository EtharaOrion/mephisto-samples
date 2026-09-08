/*
 * rasterlab.c - RasterLab core. Integer-only fixed-point raster pipeline.
 *
 * Behavioural contract notes (all load-bearing, do not "fix"):
 *   - RL-92 colourspace: original integer matrices, NOT BT.601/709.
 *   - Limited-range clamp on Y/C happens BEFORE storage, never after.
 *   - Resample coefficients are 10.6 fixed point (64 == 1.0), generated at
 *     runtime, quantised half-up from a 16.16 source position, and the
 *     cubic4 tap set is re-normalised by adjusting the CENTRE tap only.
 *   - Chroma planes carry a +0.25 sampling phase per subsampled axis.
 *   - Output rounding everywhere is half-up-then-clamp: (acc + 32) >> 6.
 */
#include "rasterlab.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---------------------------------------------------------------------- */
/* format geometry                                                        */
/* ---------------------------------------------------------------------- */

static const char *const FMT_NAMES[RL_FMT_COUNT] = {
    "GRAY8", "RGB24", "BGR24", "RGBA32", "BGRA32",
    "YCC420P", "YCC422P", "YCC444P",
};

static const char *const KERNEL_NAMES[RL_KERNEL_COUNT] = {
    "point", "tent", "cubic4",
};

int rl_format_plane_count(rl_format fmt) {
    switch (fmt) {
    case RL_FMT_YCC420P:
    case RL_FMT_YCC422P:
    case RL_FMT_YCC444P:
        return 3;
    default:
        return 1;
    }
}

int rl_format_channels(rl_format fmt) {
    switch (fmt) {
    case RL_FMT_GRAY8:
        return 1;
    case RL_FMT_RGB24:
    case RL_FMT_BGR24:
        return 3;
    case RL_FMT_RGBA32:
    case RL_FMT_BGRA32:
        return 4;
    default:
        return 1;
    }
}

void rl_plane_dims(rl_format fmt, int plane, uint32_t w, uint32_t h,
                   uint32_t *pw, uint32_t *ph) {
    if (plane == 0) {
        *pw = w;
        *ph = h;
        return;
    }
    switch (fmt) {
    case RL_FMT_YCC420P:
        *pw = (w + 1u) / 2u;
        *ph = (h + 1u) / 2u;
        return;
    case RL_FMT_YCC422P:
        *pw = (w + 1u) / 2u;
        *ph = h;
        return;
    default:
        *pw = w;
        *ph = h;
        return;
    }
}

const char *rl_format_name(rl_format fmt) {
    return FMT_NAMES[fmt];
}

int rl_format_parse(const char *s, rl_format *out) {
    for (int i = 0; i < RL_FMT_COUNT; i++) {
        if (strcmp(s, FMT_NAMES[i]) == 0) {
            *out = (rl_format)i;
            return 1;
        }
    }
    if (s[0] >= '0' && s[0] <= '7' && s[1] == '\0') {
        *out = (rl_format)(s[0] - '0');
        return 1;
    }
    return 0;
}

const char *rl_kernel_name(rl_kernel k) {
    return KERNEL_NAMES[k];
}

int rl_kernel_parse(const char *s, rl_kernel *out) {
    for (int i = 0; i < RL_KERNEL_COUNT; i++) {
        if (strcmp(s, KERNEL_NAMES[i]) == 0) {
            *out = (rl_kernel)i;
            return 1;
        }
    }
    return 0;
}

/* ---------------------------------------------------------------------- */
/* image lifecycle                                                        */
/* ---------------------------------------------------------------------- */

int rl_image_alloc(rl_image *img, rl_format fmt, uint32_t w, uint32_t h) {
    memset(img, 0, sizeof(*img));
    img->fmt = fmt;
    img->width = w;
    img->height = h;
    img->plane_count = rl_format_plane_count(fmt);
    int channels = rl_format_channels(fmt);
    for (int p = 0; p < img->plane_count; p++) {
        uint32_t pw;
        uint32_t ph;
        rl_plane_dims(fmt, p, w, h, &pw, &ph);
        size_t bytes = (size_t)pw * (size_t)ph * (size_t)(p == 0 ? channels : 1);
        if (img->plane_count == 3) {
            bytes = (size_t)pw * (size_t)ph;
        }
        img->planes[p].w = pw;
        img->planes[p].h = ph;
        img->planes[p].data = (uint8_t *)calloc(1, bytes ? bytes : 1);
        if (!img->planes[p].data) {
            rl_image_free(img);
            return 0;
        }
    }
    return 1;
}

void rl_image_free(rl_image *img) {
    for (int p = 0; p < 3; p++) {
        free(img->planes[p].data);
        img->planes[p].data = NULL;
    }
    img->plane_count = 0;
}

static size_t plane_bytes(const rl_image *img, int p) {
    size_t channels = 1;
    if (img->plane_count == 1) {
        channels = (size_t)rl_format_channels(img->fmt);
    }
    return (size_t)img->planes[p].w * (size_t)img->planes[p].h * channels;
}

/* ---------------------------------------------------------------------- */
/* checksums                                                              */
/* ---------------------------------------------------------------------- */

static uint32_t crc_table[256];
static int crc_table_ready = 0;

static void crc_table_init(void) {
    for (uint32_t n = 0; n < 256; n++) {
        uint32_t c = n;
        for (int k = 0; k < 8; k++) {
            c = (c & 1u) ? (0xEDB88320u ^ (c >> 1)) : (c >> 1);
        }
        crc_table[n] = c;
    }
    crc_table_ready = 1;
}

uint32_t rl_crc32(uint32_t crc, const uint8_t *buf, size_t len) {
    if (!crc_table_ready) {
        crc_table_init();
    }
    for (size_t i = 0; i < len; i++) {
        crc = crc_table[(crc ^ buf[i]) & 0xFFu] ^ (crc >> 8);
    }
    return crc;
}

static void header_bytes(const rl_image *img, uint8_t out[16]) {
    memcpy(out, RL_MAGIC, 4);
    out[4] = RL_CONTAINER_VERSION;
    out[5] = (uint8_t)img->fmt;
    out[6] = 0;
    out[7] = 0;
    out[8] = (uint8_t)(img->width & 0xFFu);
    out[9] = (uint8_t)((img->width >> 8) & 0xFFu);
    out[10] = (uint8_t)((img->width >> 16) & 0xFFu);
    out[11] = (uint8_t)((img->width >> 24) & 0xFFu);
    out[12] = (uint8_t)(img->height & 0xFFu);
    out[13] = (uint8_t)((img->height >> 8) & 0xFFu);
    out[14] = (uint8_t)((img->height >> 16) & 0xFFu);
    out[15] = (uint8_t)((img->height >> 24) & 0xFFu);
}

uint32_t rl_container_crc(const rl_image *img) {
    uint8_t hdr[16];
    header_bytes(img, hdr);
    uint32_t crc = rl_crc32(RL_CRC_INIT, hdr, sizeof(hdr));
    for (int p = 0; p < img->plane_count; p++) {
        crc = rl_crc32(crc, img->planes[p].data, plane_bytes(img, p));
    }
    return crc ^ 0xFFFFFFFFu;
}

uint32_t rl_plane_sum(const uint8_t *buf, size_t len) {
    uint32_t s1 = RL_SUM_INIT_S1;
    uint32_t s2 = RL_SUM_INIT_S2;
    for (size_t i = 0; i < len; i++) {
        s1 = (s1 + buf[i]) % RL_SUM_MOD;
        s2 = (s2 + s1) % RL_SUM_MOD;
    }
    return (s2 << 16) | s1;
}

/* ---------------------------------------------------------------------- */
/* container I/O                                                          */
/* ---------------------------------------------------------------------- */

rl_status rl_read_file(const char *path, rl_image *img) {
    FILE *f = fopen(path, "rb");
    if (!f) {
        return RL_ERR_UNREADABLE;
    }
    uint8_t hdr[16];
    if (fread(hdr, 1, sizeof(hdr), f) != sizeof(hdr)) {
        fclose(f);
        return RL_ERR_CORRUPT;
    }
    if (memcmp(hdr, RL_MAGIC, 4) != 0 || hdr[4] != RL_CONTAINER_VERSION) {
        fclose(f);
        return RL_ERR_CORRUPT;
    }
    if (hdr[5] >= RL_FMT_COUNT) {
        fclose(f);
        return RL_ERR_UNSUPPORTED;
    }
    if (hdr[6] != 0 || hdr[7] != 0) {
        fclose(f);
        return RL_ERR_CORRUPT;
    }
    rl_format fmt = (rl_format)hdr[5];
    uint32_t w = (uint32_t)hdr[8] | ((uint32_t)hdr[9] << 8) |
                 ((uint32_t)hdr[10] << 16) | ((uint32_t)hdr[11] << 24);
    uint32_t h = (uint32_t)hdr[12] | ((uint32_t)hdr[13] << 8) |
                 ((uint32_t)hdr[14] << 16) | ((uint32_t)hdr[15] << 24);
    if (w == 0 || h == 0 || w > RL_MAX_DIM || h > RL_MAX_DIM) {
        fclose(f);
        return RL_ERR_CORRUPT;
    }
    if (!rl_image_alloc(img, fmt, w, h)) {
        fclose(f);
        return RL_ERR_CORRUPT;
    }
    uint32_t crc = rl_crc32(RL_CRC_INIT, hdr, sizeof(hdr));
    for (int p = 0; p < img->plane_count; p++) {
        size_t n = plane_bytes(img, p);
        if (fread(img->planes[p].data, 1, n, f) != n) {
            rl_image_free(img);
            fclose(f);
            return RL_ERR_CORRUPT;
        }
        crc = rl_crc32(crc, img->planes[p].data, n);
    }
    crc ^= 0xFFFFFFFFu;
    uint8_t tail[4];
    if (fread(tail, 1, 4, f) != 4) {
        rl_image_free(img);
        fclose(f);
        return RL_ERR_CORRUPT;
    }
    uint32_t stored = (uint32_t)tail[0] | ((uint32_t)tail[1] << 8) |
                      ((uint32_t)tail[2] << 16) | ((uint32_t)tail[3] << 24);
    int extra = fgetc(f);
    fclose(f);
    if (extra != EOF) {
        rl_image_free(img);
        return RL_ERR_CORRUPT;
    }
    if (stored != crc) {
        rl_image_free(img);
        return RL_ERR_CORRUPT;
    }
    return RL_OK;
}

rl_status rl_write_file(const char *path, const rl_image *img) {
    FILE *f = fopen(path, "wb");
    if (!f) {
        return RL_ERR_UNREADABLE;
    }
    uint8_t hdr[16];
    header_bytes(img, hdr);
    uint32_t crc = rl_crc32(RL_CRC_INIT, hdr, sizeof(hdr));
    if (fwrite(hdr, 1, sizeof(hdr), f) != sizeof(hdr)) {
        fclose(f);
        return RL_ERR_UNREADABLE;
    }
    for (int p = 0; p < img->plane_count; p++) {
        size_t n = plane_bytes(img, p);
        crc = rl_crc32(crc, img->planes[p].data, n);
        if (fwrite(img->planes[p].data, 1, n, f) != n) {
            fclose(f);
            return RL_ERR_UNREADABLE;
        }
    }
    crc ^= 0xFFFFFFFFu;
    uint8_t tail[4] = {
        (uint8_t)(crc & 0xFFu),
        (uint8_t)((crc >> 8) & 0xFFu),
        (uint8_t)((crc >> 16) & 0xFFu),
        (uint8_t)((crc >> 24) & 0xFFu),
    };
    if (fwrite(tail, 1, 4, f) != 4) {
        fclose(f);
        return RL_ERR_UNREADABLE;
    }
    if (fclose(f) != 0) {
        return RL_ERR_UNREADABLE;
    }
    return RL_OK;
}

/* ---------------------------------------------------------------------- */
/* RL-92 colourspace (original matrices; limited-range clamp pre-store)   */
/* ---------------------------------------------------------------------- */

static uint8_t clamp8(int32_t v) {
    if (v < 0) {
        return 0;
    }
    if (v > 255) {
        return 255;
    }
    return (uint8_t)v;
}

static uint8_t clamp_range(int32_t v, int32_t lo, int32_t hi) {
    if (v < lo) {
        return (uint8_t)lo;
    }
    if (v > hi) {
        return (uint8_t)hi;
    }
    return (uint8_t)v;
}

static void rgb_to_ycc(uint8_t r, uint8_t g, uint8_t b,
                       uint8_t *y, uint8_t *cb, uint8_t *cr) {
    int32_t yv = 16 + ((250 * r + 493 * g + 97 * b + 420) >> 10);
    int32_t cbv = 128 + ((-121 * r - 239 * g + 360 * b + 512) >> 10);
    int32_t crv = 128 + ((360 * r - 301 * g - 59 * b + 512) >> 10);
    *y = clamp_range(yv, 16, 235);
    *cb = clamp_range(cbv, 16, 240);
    *cr = clamp_range(crv, 16, 240);
}

static void ycc_to_rgb(uint8_t y, uint8_t cb, uint8_t cr,
                       uint8_t *r, uint8_t *g, uint8_t *b) {
    int32_t yy = (((int32_t)y - 16) * 1250 + 512) >> 10;
    int32_t cbv = (int32_t)cb - 128;
    int32_t crv = (int32_t)cr - 128;
    *r = clamp8(yy + ((1634 * crv + 512) >> 10));
    *g = clamp8(yy - ((401 * cbv + 833 * crv + 512) >> 10));
    *b = clamp8(yy + ((2066 * cbv + 512) >> 10));
}

static uint8_t rgb_to_gray(uint8_t r, uint8_t g, uint8_t b) {
    return clamp8((250 * r + 493 * g + 97 * b + 420) >> 10);
}

/* ---------------------------------------------------------------------- */
/* conversion hub: everything routes through interleaved RGB24            */
/* (legacy quirk: alpha is dropped at the hub and re-set to 255)          */
/* ---------------------------------------------------------------------- */

static void chroma_down_axis(const uint8_t *src, uint32_t sw, uint32_t sh,
                             uint8_t *dst, uint32_t dw, uint32_t dh,
                             int sub_x, int sub_y) {
    for (uint32_t y = 0; y < dh; y++) {
        for (uint32_t x = 0; x < dw; x++) {
            uint32_t x0 = sub_x ? x * 2u : x;
            uint32_t y0 = sub_y ? y * 2u : y;
            uint32_t sum = 0;
            uint32_t n = 0;
            for (uint32_t dy = 0; dy < (sub_y ? 2u : 1u); dy++) {
                for (uint32_t dx = 0; dx < (sub_x ? 2u : 1u); dx++) {
                    uint32_t sx = x0 + dx;
                    uint32_t sy = y0 + dy;
                    if (sx < sw && sy < sh) {
                        sum += src[(size_t)sy * sw + sx];
                        n++;
                    }
                }
            }
            uint32_t v;
            if (n == 4u) {
                v = (sum + 2u) >> 2;
            } else if (n == 2u) {
                v = (sum + 1u) >> 1;
            } else {
                v = sum;
            }
            dst[(size_t)y * dw + x] = (uint8_t)v;
        }
    }
}

static int to_rgb24(const rl_image *src, rl_image *rgb) {
    if (!rl_image_alloc(rgb, RL_FMT_RGB24, src->width, src->height)) {
        return 0;
    }
    uint32_t w = src->width;
    uint32_t h = src->height;
    uint8_t *out = rgb->planes[0].data;
    const uint8_t *p0 = src->planes[0].data;
    switch (src->fmt) {
    case RL_FMT_GRAY8:
        for (size_t i = 0; i < (size_t)w * h; i++) {
            out[i * 3 + 0] = p0[i];
            out[i * 3 + 1] = p0[i];
            out[i * 3 + 2] = p0[i];
        }
        break;
    case RL_FMT_RGB24:
        memcpy(out, p0, (size_t)w * h * 3);
        break;
    case RL_FMT_BGR24:
        for (size_t i = 0; i < (size_t)w * h; i++) {
            out[i * 3 + 0] = p0[i * 3 + 2];
            out[i * 3 + 1] = p0[i * 3 + 1];
            out[i * 3 + 2] = p0[i * 3 + 0];
        }
        break;
    case RL_FMT_RGBA32:
        for (size_t i = 0; i < (size_t)w * h; i++) {
            out[i * 3 + 0] = p0[i * 4 + 0];
            out[i * 3 + 1] = p0[i * 4 + 1];
            out[i * 3 + 2] = p0[i * 4 + 2];
        }
        break;
    case RL_FMT_BGRA32:
        for (size_t i = 0; i < (size_t)w * h; i++) {
            out[i * 3 + 0] = p0[i * 4 + 2];
            out[i * 3 + 1] = p0[i * 4 + 1];
            out[i * 3 + 2] = p0[i * 4 + 0];
        }
        break;
    case RL_FMT_YCC420P:
    case RL_FMT_YCC422P:
    case RL_FMT_YCC444P: {
        const uint8_t *py = src->planes[0].data;
        const uint8_t *pcb = src->planes[1].data;
        const uint8_t *pcr = src->planes[2].data;
        uint32_t cw = src->planes[1].w;
        int sub_x = (src->fmt != RL_FMT_YCC444P);
        int sub_y = (src->fmt == RL_FMT_YCC420P);
        for (uint32_t y = 0; y < h; y++) {
            for (uint32_t x = 0; x < w; x++) {
                uint32_t cx = sub_x ? x / 2u : x;
                uint32_t cy = sub_y ? y / 2u : y;
                uint8_t r;
                uint8_t g;
                uint8_t b;
                ycc_to_rgb(py[(size_t)y * w + x],
                           pcb[(size_t)cy * cw + cx],
                           pcr[(size_t)cy * cw + cx], &r, &g, &b);
                size_t o = ((size_t)y * w + x) * 3;
                out[o + 0] = r;
                out[o + 1] = g;
                out[o + 2] = b;
            }
        }
        break;
    }
    default:
        rl_image_free(rgb);
        return 0;
    }
    return 1;
}

static int from_rgb24(const rl_image *rgb, rl_format dst_fmt, rl_image *dst) {
    uint32_t w = rgb->width;
    uint32_t h = rgb->height;
    if (!rl_image_alloc(dst, dst_fmt, w, h)) {
        return 0;
    }
    const uint8_t *in = rgb->planes[0].data;
    uint8_t *out = dst->planes[0].data;
    switch (dst_fmt) {
    case RL_FMT_GRAY8:
        for (size_t i = 0; i < (size_t)w * h; i++) {
            out[i] = rgb_to_gray(in[i * 3], in[i * 3 + 1], in[i * 3 + 2]);
        }
        break;
    case RL_FMT_RGB24:
        memcpy(out, in, (size_t)w * h * 3);
        break;
    case RL_FMT_BGR24:
        for (size_t i = 0; i < (size_t)w * h; i++) {
            out[i * 3 + 0] = in[i * 3 + 2];
            out[i * 3 + 1] = in[i * 3 + 1];
            out[i * 3 + 2] = in[i * 3 + 0];
        }
        break;
    case RL_FMT_RGBA32:
        for (size_t i = 0; i < (size_t)w * h; i++) {
            out[i * 4 + 0] = in[i * 3 + 0];
            out[i * 4 + 1] = in[i * 3 + 1];
            out[i * 4 + 2] = in[i * 3 + 2];
            out[i * 4 + 3] = 255;
        }
        break;
    case RL_FMT_BGRA32:
        for (size_t i = 0; i < (size_t)w * h; i++) {
            out[i * 4 + 0] = in[i * 3 + 2];
            out[i * 4 + 1] = in[i * 3 + 1];
            out[i * 4 + 2] = in[i * 3 + 0];
            out[i * 4 + 3] = 255;
        }
        break;
    case RL_FMT_YCC420P:
    case RL_FMT_YCC422P:
    case RL_FMT_YCC444P: {
        uint8_t *full_cb = (uint8_t *)malloc((size_t)w * h);
        uint8_t *full_cr = (uint8_t *)malloc((size_t)w * h);
        if (!full_cb || !full_cr) {
            free(full_cb);
            free(full_cr);
            rl_image_free(dst);
            return 0;
        }
        uint8_t *py = dst->planes[0].data;
        for (size_t i = 0; i < (size_t)w * h; i++) {
            rgb_to_ycc(in[i * 3], in[i * 3 + 1], in[i * 3 + 2],
                       &py[i], &full_cb[i], &full_cr[i]);
        }
        int sub_x = (dst_fmt != RL_FMT_YCC444P);
        int sub_y = (dst_fmt == RL_FMT_YCC420P);
        chroma_down_axis(full_cb, w, h, dst->planes[1].data,
                         dst->planes[1].w, dst->planes[1].h, sub_x, sub_y);
        chroma_down_axis(full_cr, w, h, dst->planes[2].data,
                         dst->planes[2].w, dst->planes[2].h, sub_x, sub_y);
        free(full_cb);
        free(full_cr);
        break;
    }
    default:
        rl_image_free(dst);
        return 0;
    }
    return 1;
}

rl_status rl_convert(const rl_image *src, rl_format dst_fmt, rl_image *dst) {
    if (dst_fmt >= RL_FMT_COUNT) {
        return RL_ERR_UNSUPPORTED;
    }
    if (src->fmt == dst_fmt) {
        if (!rl_image_alloc(dst, dst_fmt, src->width, src->height)) {
            return RL_ERR_CORRUPT;
        }
        for (int p = 0; p < src->plane_count; p++) {
            memcpy(dst->planes[p].data, src->planes[p].data, plane_bytes(src, p));
        }
        return RL_OK;
    }
    rl_image rgb;
    if (!to_rgb24(src, &rgb)) {
        return RL_ERR_CORRUPT;
    }
    int ok = from_rgb24(&rgb, dst_fmt, dst);
    rl_image_free(&rgb);
    return ok ? RL_OK : RL_ERR_CORRUPT;
}

/* ---------------------------------------------------------------------- */
/* resampling: 16.16 source mapping -> 10.6 coefficients                  */
/* ---------------------------------------------------------------------- */

static int64_t map_pos(uint32_t dst_i, uint32_t src_dim, uint32_t dst_dim,
                       int phase_quarter) {
    int64_t pos = ((int64_t)(2 * (int64_t)dst_i + 1) * (int64_t)src_dim * 32768)
                      / (int64_t)dst_dim -
                  32768;
    if (phase_quarter) {
        pos += 16384;
    }
    return pos;
}

static int32_t clamp_tap(int32_t i, int32_t dim) {
    if (i < 0) {
        return 0;
    }
    if (i >= dim) {
        return dim - 1;
    }
    return i;
}

static void cubic4_weights(int32_t t6, int32_t w[4]) {
    int32_t t2 = t6 * t6;
    int32_t t3 = t2 * t6;
    w[0] = (-t3 + 128 * t2 - 4096 * t6 + 4096) >> 13;
    w[1] = (3 * t3 - 320 * t2 + 524288 + 4096) >> 13;
    w[2] = (-3 * t3 + 256 * t2 + 4096 * t6 + 4096) >> 13;
    w[3] = (t3 - 64 * t2 + 4096) >> 13;
    int32_t sum = w[0] + w[1] + w[2] + w[3];
    w[1] += 64 - sum;
}

static void resample_line(const uint8_t *src, int32_t src_dim, size_t src_stride,
                          uint8_t *dst, int32_t dst_dim, size_t dst_stride,
                          rl_kernel kernel, int phase_quarter) {
    for (int32_t i = 0; i < dst_dim; i++) {
        int64_t pos = map_pos((uint32_t)i, (uint32_t)src_dim, (uint32_t)dst_dim,
                              phase_quarter);
        int32_t base = (int32_t)(pos >> 16);
        int32_t frac16 = (int32_t)(pos & 0xFFFF);
        int32_t acc;
        switch (kernel) {
        case RL_KERNEL_POINT: {
            int32_t si = clamp_tap((int32_t)((pos + 32768) >> 16), src_dim);
            acc = (int32_t)src[(size_t)si * src_stride] << 6;
            break;
        }
        case RL_KERNEL_TENT: {
            int32_t w1 = (frac16 + 512) >> 10;
            int32_t w0 = 64 - w1;
            int32_t s0 = clamp_tap(base, src_dim);
            int32_t s1 = clamp_tap(base + 1, src_dim);
            acc = w0 * src[(size_t)s0 * src_stride] +
                  w1 * src[(size_t)s1 * src_stride];
            break;
        }
        default: {
            int32_t t6 = (frac16 + 512) >> 10;
            int32_t w[4];
            cubic4_weights(t6, w);
            acc = 0;
            for (int k = 0; k < 4; k++) {
                int32_t s = clamp_tap(base - 1 + k, src_dim);
                acc += w[k] * src[(size_t)s * src_stride];
            }
            break;
        }
        }
        dst[(size_t)i * dst_stride] = clamp8((acc + 32) >> 6);
    }
}

static int resize_plane(const uint8_t *src, uint32_t sw, uint32_t sh,
                        uint8_t *dst, uint32_t dw, uint32_t dh,
                        uint32_t channels, rl_kernel kernel,
                        int phase_x, int phase_y) {
    size_t tmp_bytes = (size_t)dw * sh * channels;
    uint8_t *tmp = (uint8_t *)malloc(tmp_bytes ? tmp_bytes : 1);
    if (!tmp) {
        return 0;
    }
    for (uint32_t y = 0; y < sh; y++) {
        for (uint32_t c = 0; c < channels; c++) {
            resample_line(src + (size_t)y * sw * channels + c, (int32_t)sw,
                          channels, tmp + (size_t)y * dw * channels + c,
                          (int32_t)dw, channels, kernel, phase_x);
        }
    }
    for (uint32_t x = 0; x < dw; x++) {
        for (uint32_t c = 0; c < channels; c++) {
            resample_line(tmp + (size_t)x * channels + c, (int32_t)sh,
                          (size_t)dw * channels,
                          dst + (size_t)x * channels + c, (int32_t)dh,
                          (size_t)dw * channels, kernel, phase_y);
        }
    }
    free(tmp);
    return 1;
}

rl_status rl_resize(const rl_image *src, uint32_t dst_w, uint32_t dst_h,
                    rl_kernel kernel, rl_image *dst) {
    if (kernel >= RL_KERNEL_COUNT) {
        return RL_ERR_UNSUPPORTED;
    }
    if (dst_w == 0 || dst_h == 0 || dst_w > RL_MAX_DIM || dst_h > RL_MAX_DIM) {
        return RL_ERR_UNSUPPORTED;
    }
    if (!rl_image_alloc(dst, src->fmt, dst_w, dst_h)) {
        return RL_ERR_CORRUPT;
    }
    int planar = (src->plane_count == 3);
    uint32_t channels = planar ? 1u : (uint32_t)rl_format_channels(src->fmt);
    for (int p = 0; p < src->plane_count; p++) {
        int sub_x = planar && p > 0 && (src->fmt != RL_FMT_YCC444P);
        int sub_y = planar && p > 0 && (src->fmt == RL_FMT_YCC420P);
        if (!resize_plane(src->planes[p].data, src->planes[p].w,
                          src->planes[p].h, dst->planes[p].data,
                          dst->planes[p].w, dst->planes[p].h, channels, kernel,
                          sub_x, sub_y)) {
            rl_image_free(dst);
            return RL_ERR_CORRUPT;
        }
    }
    return RL_OK;
}
