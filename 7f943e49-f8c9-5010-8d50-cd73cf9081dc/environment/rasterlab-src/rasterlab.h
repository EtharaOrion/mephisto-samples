/*
 * rasterlab.h - RasterLab legacy fixed-point raster pipeline (reference).
 *
 * Integer-only. No floating point anywhere in this library. Every arithmetic
 * path below is part of the observable behavioural contract: rounding biases,
 * clamp ordering, phase offsets and normalisation quirks are all load-bearing.
 */
#ifndef RASTERLAB_H
#define RASTERLAB_H

#include <stddef.h>
#include <stdint.h>

#define RL_VERSION_STRING "1.2.0"

#define RL_MAGIC "RLRF"
#define RL_CONTAINER_VERSION 1
#define RL_MAX_DIM 32768u
#define RL_CRC_INIT 0xACE1FADEu
#define RL_SUM_MOD 65213u
#define RL_SUM_INIT_S1 7u
#define RL_SUM_INIT_S2 13u

typedef enum {
    RL_FMT_GRAY8 = 0,
    RL_FMT_RGB24 = 1,
    RL_FMT_BGR24 = 2,
    RL_FMT_RGBA32 = 3,
    RL_FMT_BGRA32 = 4,
    RL_FMT_YCC420P = 5,
    RL_FMT_YCC422P = 6,
    RL_FMT_YCC444P = 7,
    RL_FMT_COUNT = 8
} rl_format;

typedef enum {
    RL_KERNEL_POINT = 0,
    RL_KERNEL_TENT = 1,
    RL_KERNEL_CUBIC4 = 2,
    RL_KERNEL_COUNT = 3
} rl_kernel;

typedef enum {
    RL_OK = 0,
    RL_ERR_USAGE = 2,
    RL_ERR_UNREADABLE = 3,
    RL_ERR_UNSUPPORTED = 4,
    RL_ERR_CORRUPT = 5
} rl_status;

typedef struct {
    uint32_t w;
    uint32_t h;
    uint8_t *data; /* w * h * channels, tightly packed */
} rl_plane;

typedef struct {
    rl_format fmt;
    uint32_t width;
    uint32_t height;
    int plane_count;
    rl_plane planes[3];
} rl_image;

/* --- format geometry --------------------------------------------------- */
int rl_format_plane_count(rl_format fmt);
int rl_format_channels(rl_format fmt); /* interleaved channel count; 1 for planar */
void rl_plane_dims(rl_format fmt, int plane, uint32_t w, uint32_t h,
                   uint32_t *pw, uint32_t *ph);
const char *rl_format_name(rl_format fmt);
int rl_format_parse(const char *s, rl_format *out);
const char *rl_kernel_name(rl_kernel k);
int rl_kernel_parse(const char *s, rl_kernel *out);

/* --- image lifecycle --------------------------------------------------- */
int rl_image_alloc(rl_image *img, rl_format fmt, uint32_t w, uint32_t h);
void rl_image_free(rl_image *img);

/* --- container I/O ----------------------------------------------------- */
rl_status rl_read_file(const char *path, rl_image *img);
rl_status rl_write_file(const char *path, const rl_image *img);

/* --- checksums --------------------------------------------------------- */
uint32_t rl_crc32(uint32_t crc, const uint8_t *buf, size_t len);
uint32_t rl_container_crc(const rl_image *img);
uint32_t rl_plane_sum(const uint8_t *buf, size_t len);

/* --- pipeline ops ------------------------------------------------------ */
rl_status rl_convert(const rl_image *src, rl_format dst_fmt, rl_image *dst);
rl_status rl_resize(const rl_image *src, uint32_t dst_w, uint32_t dst_h,
                    rl_kernel kernel, rl_image *dst);

#endif /* RASTERLAB_H */
