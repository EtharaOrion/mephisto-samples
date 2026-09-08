// rasterlab (oracle Rust port) - bit-exact mirror of the RasterLab reference C.
//
// Behavioural contract notes (all load-bearing, do not "fix"):
//   - RL-92 colourspace: original integer matrices, NOT BT.601/709.
//   - Limited-range clamp on Y/C happens BEFORE storage, never after.
//   - Resample coefficients are 10.6 fixed point (64 == 1.0), generated at
//     runtime, quantised half-up from a 16.16 source position, and the
//     cubic4 tap set is re-normalised by adjusting the CENTRE tap only.
//   - Chroma planes carry a +0.25 sampling phase per subsampled axis.
//   - Output rounding everywhere is half-up-then-clamp: (acc + 32) >> 6.
//   - parse_u32 mirrors the legacy overflow guard including its wrap quirk.

use std::env;
use std::fs::File;
use std::io::{Read, Write};
use std::process::exit;

const RL_MAGIC: &[u8; 4] = b"RLRF";
const RL_CONTAINER_VERSION: u8 = 1;
const RL_MAX_DIM: u32 = 32768;
const RL_CRC_INIT: u32 = 0xACE1_FADE;
const RL_SUM_MOD: u32 = 65213;
const RL_SUM_INIT_S1: u32 = 7;
const RL_SUM_INIT_S2: u32 = 13;
const RL_FMT_COUNT: u8 = 8;

const RL_OK: i32 = 0;
const RL_ERR_USAGE: i32 = 2;
const RL_ERR_UNREADABLE: i32 = 3;
const RL_ERR_UNSUPPORTED: i32 = 4;
const RL_ERR_CORRUPT: i32 = 5;

#[derive(Clone, Copy, PartialEq, Eq)]
enum Fmt {
    Gray8 = 0,
    Rgb24 = 1,
    Bgr24 = 2,
    Rgba32 = 3,
    Bgra32 = 4,
    Ycc420p = 5,
    Ycc422p = 6,
    Ycc444p = 7,
}

const FMT_NAMES: [&str; 8] = [
    "GRAY8", "RGB24", "BGR24", "RGBA32", "BGRA32", "YCC420P", "YCC422P", "YCC444P",
];

const KERNEL_NAMES: [&str; 3] = ["point", "tent", "cubic4"];

#[derive(Clone, Copy, PartialEq, Eq)]
enum Kernel {
    Point = 0,
    Tent = 1,
    Cubic4 = 2,
}

impl Fmt {
    fn from_u8(v: u8) -> Option<Fmt> {
        match v {
            0 => Some(Fmt::Gray8),
            1 => Some(Fmt::Rgb24),
            2 => Some(Fmt::Bgr24),
            3 => Some(Fmt::Rgba32),
            4 => Some(Fmt::Bgra32),
            5 => Some(Fmt::Ycc420p),
            6 => Some(Fmt::Ycc422p),
            7 => Some(Fmt::Ycc444p),
            _ => None,
        }
    }
}

fn format_plane_count(fmt: Fmt) -> usize {
    match fmt {
        Fmt::Ycc420p | Fmt::Ycc422p | Fmt::Ycc444p => 3,
        _ => 1,
    }
}

fn format_channels(fmt: Fmt) -> usize {
    match fmt {
        Fmt::Gray8 => 1,
        Fmt::Rgb24 | Fmt::Bgr24 => 3,
        Fmt::Rgba32 | Fmt::Bgra32 => 4,
        _ => 1,
    }
}

fn plane_dims(fmt: Fmt, plane: usize, w: u32, h: u32) -> (u32, u32) {
    if plane == 0 {
        return (w, h);
    }
    match fmt {
        Fmt::Ycc420p => ((w + 1) / 2, (h + 1) / 2),
        Fmt::Ycc422p => ((w + 1) / 2, h),
        _ => (w, h),
    }
}

fn format_parse(s: &str) -> Option<Fmt> {
    for (i, name) in FMT_NAMES.iter().enumerate() {
        if s == *name {
            return Fmt::from_u8(i as u8);
        }
    }
    let b = s.as_bytes();
    if b.len() == 1 && (b'0'..=b'7').contains(&b[0]) {
        return Fmt::from_u8(b[0] - b'0');
    }
    None
}

fn kernel_parse(s: &str) -> Option<Kernel> {
    match s {
        _ if s == KERNEL_NAMES[0] => Some(Kernel::Point),
        _ if s == KERNEL_NAMES[1] => Some(Kernel::Tent),
        _ if s == KERNEL_NAMES[2] => Some(Kernel::Cubic4),
        _ => None,
    }
}

struct Plane {
    w: u32,
    h: u32,
    data: Vec<u8>,
}

struct Image {
    fmt: Fmt,
    width: u32,
    height: u32,
    planes: Vec<Plane>,
}

impl Image {
    fn alloc(fmt: Fmt, w: u32, h: u32) -> Image {
        let plane_count = format_plane_count(fmt);
        let channels = format_channels(fmt);
        let mut planes = Vec::with_capacity(plane_count);
        for p in 0..plane_count {
            let (pw, ph) = plane_dims(fmt, p, w, h);
            let bytes = if plane_count == 3 {
                pw as usize * ph as usize
            } else {
                pw as usize * ph as usize * channels
            };
            planes.push(Plane {
                w: pw,
                h: ph,
                data: vec![0u8; bytes],
            });
        }
        Image {
            fmt,
            width: w,
            height: h,
            planes,
        }
    }

    fn plane_bytes(&self, p: usize) -> usize {
        let channels = if self.planes.len() == 1 {
            format_channels(self.fmt)
        } else {
            1
        };
        self.planes[p].w as usize * self.planes[p].h as usize * channels
    }
}

// ---------------------------------------------------------------------------
// checksums
// ---------------------------------------------------------------------------

fn crc_table() -> [u32; 256] {
    let mut table = [0u32; 256];
    for (n, slot) in table.iter_mut().enumerate() {
        let mut c = n as u32;
        for _ in 0..8 {
            c = if c & 1 != 0 {
                0xEDB8_8320 ^ (c >> 1)
            } else {
                c >> 1
            };
        }
        *slot = c;
    }
    table
}

fn crc32(table: &[u32; 256], mut crc: u32, buf: &[u8]) -> u32 {
    for &b in buf {
        crc = table[((crc ^ b as u32) & 0xFF) as usize] ^ (crc >> 8);
    }
    crc
}

fn header_bytes(img: &Image) -> [u8; 16] {
    let mut out = [0u8; 16];
    out[0..4].copy_from_slice(RL_MAGIC);
    out[4] = RL_CONTAINER_VERSION;
    out[5] = img.fmt as u8;
    out[6] = 0;
    out[7] = 0;
    out[8..12].copy_from_slice(&img.width.to_le_bytes());
    out[12..16].copy_from_slice(&img.height.to_le_bytes());
    out
}

fn container_crc(table: &[u32; 256], img: &Image) -> u32 {
    let hdr = header_bytes(img);
    let mut crc = crc32(table, RL_CRC_INIT, &hdr);
    for p in 0..img.planes.len() {
        let n = img.plane_bytes(p);
        crc = crc32(table, crc, &img.planes[p].data[..n]);
    }
    crc ^ 0xFFFF_FFFF
}

fn plane_sum(buf: &[u8]) -> u32 {
    let mut s1 = RL_SUM_INIT_S1;
    let mut s2 = RL_SUM_INIT_S2;
    for &b in buf {
        s1 = (s1 + b as u32) % RL_SUM_MOD;
        s2 = (s2 + s1) % RL_SUM_MOD;
    }
    (s2 << 16) | s1
}

// ---------------------------------------------------------------------------
// container I/O
// ---------------------------------------------------------------------------

fn read_file(table: &[u32; 256], path: &str) -> Result<Image, i32> {
    let mut f = match File::open(path) {
        Ok(f) => f,
        Err(_) => return Err(RL_ERR_UNREADABLE),
    };
    let mut hdr = [0u8; 16];
    if read_exact_count(&mut f, &mut hdr) != 16 {
        return Err(RL_ERR_CORRUPT);
    }
    if &hdr[0..4] != RL_MAGIC || hdr[4] != RL_CONTAINER_VERSION {
        return Err(RL_ERR_CORRUPT);
    }
    if hdr[5] >= RL_FMT_COUNT {
        return Err(RL_ERR_UNSUPPORTED);
    }
    if hdr[6] != 0 || hdr[7] != 0 {
        return Err(RL_ERR_CORRUPT);
    }
    let fmt = Fmt::from_u8(hdr[5]).unwrap();
    let w = u32::from_le_bytes([hdr[8], hdr[9], hdr[10], hdr[11]]);
    let h = u32::from_le_bytes([hdr[12], hdr[13], hdr[14], hdr[15]]);
    if w == 0 || h == 0 || w > RL_MAX_DIM || h > RL_MAX_DIM {
        return Err(RL_ERR_CORRUPT);
    }
    let mut img = Image::alloc(fmt, w, h);
    let mut crc = crc32(table, RL_CRC_INIT, &hdr);
    for p in 0..img.planes.len() {
        let n = img.plane_bytes(p);
        let got = {
            let buf = &mut img.planes[p].data[..n];
            read_exact_count(&mut f, buf)
        };
        if got != n {
            return Err(RL_ERR_CORRUPT);
        }
        crc = crc32(table, crc, &img.planes[p].data[..n]);
    }
    crc ^= 0xFFFF_FFFF;
    let mut tail = [0u8; 4];
    if read_exact_count(&mut f, &mut tail) != 4 {
        return Err(RL_ERR_CORRUPT);
    }
    let stored = u32::from_le_bytes(tail);
    let mut extra = [0u8; 1];
    let more = read_exact_count(&mut f, &mut extra);
    if more != 0 {
        return Err(RL_ERR_CORRUPT);
    }
    if stored != crc {
        return Err(RL_ERR_CORRUPT);
    }
    Ok(img)
}

fn read_exact_count(f: &mut File, buf: &mut [u8]) -> usize {
    let mut total = 0usize;
    while total < buf.len() {
        match f.read(&mut buf[total..]) {
            Ok(0) => break,
            Ok(n) => total += n,
            Err(_) => break,
        }
    }
    total
}

fn write_file(table: &[u32; 256], path: &str, img: &Image) -> Result<(), i32> {
    let mut f = match File::create(path) {
        Ok(f) => f,
        Err(_) => return Err(RL_ERR_UNREADABLE),
    };
    let hdr = header_bytes(img);
    let mut crc = crc32(table, RL_CRC_INIT, &hdr);
    if f.write_all(&hdr).is_err() {
        return Err(RL_ERR_UNREADABLE);
    }
    for p in 0..img.planes.len() {
        let n = img.plane_bytes(p);
        crc = crc32(table, crc, &img.planes[p].data[..n]);
        if f.write_all(&img.planes[p].data[..n]).is_err() {
            return Err(RL_ERR_UNREADABLE);
        }
    }
    crc ^= 0xFFFF_FFFF;
    if f.write_all(&crc.to_le_bytes()).is_err() {
        return Err(RL_ERR_UNREADABLE);
    }
    if f.sync_all().is_err() {
        return Err(RL_ERR_UNREADABLE);
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// RL-92 colourspace (original matrices; limited-range clamp pre-store)
// ---------------------------------------------------------------------------

fn clamp8(v: i32) -> u8 {
    if v < 0 {
        0
    } else if v > 255 {
        255
    } else {
        v as u8
    }
}

fn clamp_range(v: i32, lo: i32, hi: i32) -> u8 {
    if v < lo {
        lo as u8
    } else if v > hi {
        hi as u8
    } else {
        v as u8
    }
}

fn rgb_to_ycc(r: u8, g: u8, b: u8) -> (u8, u8, u8) {
    let r = r as i32;
    let g = g as i32;
    let b = b as i32;
    let yv = 16 + ((250 * r + 493 * g + 97 * b + 420) >> 10);
    let cbv = 128 + ((-121 * r - 239 * g + 360 * b + 512) >> 10);
    let crv = 128 + ((360 * r - 301 * g - 59 * b + 512) >> 10);
    (
        clamp_range(yv, 16, 235),
        clamp_range(cbv, 16, 240),
        clamp_range(crv, 16, 240),
    )
}

fn ycc_to_rgb(y: u8, cb: u8, cr: u8) -> (u8, u8, u8) {
    let yy = ((y as i32 - 16) * 1250 + 512) >> 10;
    let cbv = cb as i32 - 128;
    let crv = cr as i32 - 128;
    (
        clamp8(yy + ((1634 * crv + 512) >> 10)),
        clamp8(yy - ((401 * cbv + 833 * crv + 512) >> 10)),
        clamp8(yy + ((2066 * cbv + 512) >> 10)),
    )
}

fn rgb_to_gray(r: u8, g: u8, b: u8) -> u8 {
    clamp8((250 * r as i32 + 493 * g as i32 + 97 * b as i32 + 420) >> 10)
}

// ---------------------------------------------------------------------------
// conversion hub: everything routes through interleaved RGB24
// (legacy quirk: alpha is dropped at the hub and re-set to 255)
// ---------------------------------------------------------------------------

fn chroma_down_axis(src: &[u8], sw: u32, sh: u32, dst: &mut [u8], dw: u32, dh: u32, sub_x: bool, sub_y: bool) {
    for y in 0..dh {
        for x in 0..dw {
            let x0 = if sub_x { x * 2 } else { x };
            let y0 = if sub_y { y * 2 } else { y };
            let mut sum: u32 = 0;
            let mut n: u32 = 0;
            let ylim = if sub_y { 2 } else { 1 };
            let xlim = if sub_x { 2 } else { 1 };
            for dy in 0..ylim {
                for dx in 0..xlim {
                    let sx = x0 + dx;
                    let sy = y0 + dy;
                    if sx < sw && sy < sh {
                        sum += src[(sy as usize) * sw as usize + sx as usize] as u32;
                        n += 1;
                    }
                }
            }
            let v = if n == 4 {
                (sum + 2) >> 2
            } else if n == 2 {
                (sum + 1) >> 1
            } else {
                sum
            };
            dst[(y as usize) * dw as usize + x as usize] = v as u8;
        }
    }
}

fn to_rgb24(src: &Image) -> Image {
    let w = src.width;
    let h = src.height;
    let mut rgb = Image::alloc(Fmt::Rgb24, w, h);
    let npx = w as usize * h as usize;
    let p0 = &src.planes[0].data;
    let out = &mut rgb.planes[0].data;
    match src.fmt {
        Fmt::Gray8 => {
            for i in 0..npx {
                out[i * 3] = p0[i];
                out[i * 3 + 1] = p0[i];
                out[i * 3 + 2] = p0[i];
            }
        }
        Fmt::Rgb24 => {
            out.copy_from_slice(&p0[..npx * 3]);
        }
        Fmt::Bgr24 => {
            for i in 0..npx {
                out[i * 3] = p0[i * 3 + 2];
                out[i * 3 + 1] = p0[i * 3 + 1];
                out[i * 3 + 2] = p0[i * 3];
            }
        }
        Fmt::Rgba32 => {
            for i in 0..npx {
                out[i * 3] = p0[i * 4];
                out[i * 3 + 1] = p0[i * 4 + 1];
                out[i * 3 + 2] = p0[i * 4 + 2];
            }
        }
        Fmt::Bgra32 => {
            for i in 0..npx {
                out[i * 3] = p0[i * 4 + 2];
                out[i * 3 + 1] = p0[i * 4 + 1];
                out[i * 3 + 2] = p0[i * 4];
            }
        }
        Fmt::Ycc420p | Fmt::Ycc422p | Fmt::Ycc444p => {
            let py = &src.planes[0].data;
            let pcb = &src.planes[1].data;
            let pcr = &src.planes[2].data;
            let cw = src.planes[1].w;
            let sub_x = src.fmt != Fmt::Ycc444p;
            let sub_y = src.fmt == Fmt::Ycc420p;
            for y in 0..h {
                for x in 0..w {
                    let cx = if sub_x { x / 2 } else { x };
                    let cy = if sub_y { y / 2 } else { y };
                    let ci = (cy as usize) * cw as usize + cx as usize;
                    let (r, g, b) = ycc_to_rgb(py[(y as usize) * w as usize + x as usize], pcb[ci], pcr[ci]);
                    let o = ((y as usize) * w as usize + x as usize) * 3;
                    out[o] = r;
                    out[o + 1] = g;
                    out[o + 2] = b;
                }
            }
        }
    }
    rgb
}

fn from_rgb24(rgb: &Image, dst_fmt: Fmt) -> Image {
    let w = rgb.width;
    let h = rgb.height;
    let mut dst = Image::alloc(dst_fmt, w, h);
    let npx = w as usize * h as usize;
    let input = &rgb.planes[0].data;
    match dst_fmt {
        Fmt::Gray8 => {
            let out = &mut dst.planes[0].data;
            for i in 0..npx {
                out[i] = rgb_to_gray(input[i * 3], input[i * 3 + 1], input[i * 3 + 2]);
            }
        }
        Fmt::Rgb24 => {
            dst.planes[0].data.copy_from_slice(&input[..npx * 3]);
        }
        Fmt::Bgr24 => {
            let out = &mut dst.planes[0].data;
            for i in 0..npx {
                out[i * 3] = input[i * 3 + 2];
                out[i * 3 + 1] = input[i * 3 + 1];
                out[i * 3 + 2] = input[i * 3];
            }
        }
        Fmt::Rgba32 => {
            let out = &mut dst.planes[0].data;
            for i in 0..npx {
                out[i * 4] = input[i * 3];
                out[i * 4 + 1] = input[i * 3 + 1];
                out[i * 4 + 2] = input[i * 3 + 2];
                out[i * 4 + 3] = 255;
            }
        }
        Fmt::Bgra32 => {
            let out = &mut dst.planes[0].data;
            for i in 0..npx {
                out[i * 4] = input[i * 3 + 2];
                out[i * 4 + 1] = input[i * 3 + 1];
                out[i * 4 + 2] = input[i * 3];
                out[i * 4 + 3] = 255;
            }
        }
        Fmt::Ycc420p | Fmt::Ycc422p | Fmt::Ycc444p => {
            let mut full_cb = vec![0u8; npx];
            let mut full_cr = vec![0u8; npx];
            {
                let py = &mut dst.planes[0].data;
                for i in 0..npx {
                    let (y, cb, cr) = rgb_to_ycc(input[i * 3], input[i * 3 + 1], input[i * 3 + 2]);
                    py[i] = y;
                    full_cb[i] = cb;
                    full_cr[i] = cr;
                }
            }
            let sub_x = dst_fmt != Fmt::Ycc444p;
            let sub_y = dst_fmt == Fmt::Ycc420p;
            let (cw, chh) = (dst.planes[1].w, dst.planes[1].h);
            chroma_down_axis(&full_cb, w, h, &mut dst.planes[1].data, cw, chh, sub_x, sub_y);
            let (cw2, ch2) = (dst.planes[2].w, dst.planes[2].h);
            chroma_down_axis(&full_cr, w, h, &mut dst.planes[2].data, cw2, ch2, sub_x, sub_y);
        }
    }
    dst
}

fn convert(src: &Image, dst_fmt: Fmt) -> Image {
    if src.fmt == dst_fmt {
        let mut dst = Image::alloc(dst_fmt, src.width, src.height);
        for p in 0..src.planes.len() {
            let n = src.plane_bytes(p);
            dst.planes[p].data[..n].copy_from_slice(&src.planes[p].data[..n]);
        }
        return dst;
    }
    let rgb = to_rgb24(src);
    from_rgb24(&rgb, dst_fmt)
}

// ---------------------------------------------------------------------------
// resampling: 16.16 source mapping -> 10.6 coefficients
// ---------------------------------------------------------------------------

fn map_pos(dst_i: u32, src_dim: u32, dst_dim: u32, phase_quarter: bool) -> i64 {
    let mut pos = ((2 * dst_i as i64 + 1) * src_dim as i64 * 32768) / dst_dim as i64 - 32768;
    if phase_quarter {
        pos += 16384;
    }
    pos
}

fn clamp_tap(i: i32, dim: i32) -> i32 {
    if i < 0 {
        0
    } else if i >= dim {
        dim - 1
    } else {
        i
    }
}

fn cubic4_weights(t6: i32) -> [i32; 4] {
    let t2 = t6 * t6;
    let t3 = t2 * t6;
    let mut w = [
        (-t3 + 128 * t2 - 4096 * t6 + 4096) >> 13,
        (3 * t3 - 320 * t2 + 524288 + 4096) >> 13,
        (-3 * t3 + 256 * t2 + 4096 * t6 + 4096) >> 13,
        (t3 - 64 * t2 + 4096) >> 13,
    ];
    let sum = w[0] + w[1] + w[2] + w[3];
    w[1] += 64 - sum;
    w
}

fn resample_line(
    src: &[u8],
    src_off: usize,
    src_dim: i32,
    src_stride: usize,
    dst: &mut [u8],
    dst_off: usize,
    dst_dim: i32,
    dst_stride: usize,
    kernel: Kernel,
    phase_quarter: bool,
) {
    for i in 0..dst_dim {
        let pos = map_pos(i as u32, src_dim as u32, dst_dim as u32, phase_quarter);
        let base = (pos >> 16) as i32;
        let frac16 = (pos & 0xFFFF) as i32;
        let acc: i32;
        match kernel {
            Kernel::Point => {
                let si = clamp_tap(((pos + 32768) >> 16) as i32, src_dim);
                acc = (src[src_off + si as usize * src_stride] as i32) << 6;
            }
            Kernel::Tent => {
                let w1 = (frac16 + 512) >> 10;
                let w0 = 64 - w1;
                let s0 = clamp_tap(base, src_dim);
                let s1 = clamp_tap(base + 1, src_dim);
                acc = w0 * src[src_off + s0 as usize * src_stride] as i32
                    + w1 * src[src_off + s1 as usize * src_stride] as i32;
            }
            Kernel::Cubic4 => {
                let t6 = (frac16 + 512) >> 10;
                let w = cubic4_weights(t6);
                let mut a = 0i32;
                for (k, wk) in w.iter().enumerate() {
                    let s = clamp_tap(base - 1 + k as i32, src_dim);
                    a += wk * src[src_off + s as usize * src_stride] as i32;
                }
                acc = a;
            }
        }
        dst[dst_off + i as usize * dst_stride] = clamp8((acc + 32) >> 6);
    }
}

fn resize_plane(
    src: &[u8],
    sw: u32,
    sh: u32,
    dst: &mut [u8],
    dw: u32,
    dh: u32,
    channels: u32,
    kernel: Kernel,
    phase_x: bool,
    phase_y: bool,
) {
    let ch = channels as usize;
    let mut tmp = vec![0u8; dw as usize * sh as usize * ch];
    for y in 0..sh as usize {
        for c in 0..ch {
            resample_line(
                src,
                y * sw as usize * ch + c,
                sw as i32,
                ch,
                &mut tmp,
                y * dw as usize * ch + c,
                dw as i32,
                ch,
                kernel,
                phase_x,
            );
        }
    }
    for x in 0..dw as usize {
        for c in 0..ch {
            resample_line(
                &tmp,
                x * ch + c,
                sh as i32,
                dw as usize * ch,
                dst,
                x * ch + c,
                dh as i32,
                dw as usize * ch,
                kernel,
                phase_y,
            );
        }
    }
}

fn resize(src: &Image, dst_w: u32, dst_h: u32, kernel: Kernel) -> Result<Image, i32> {
    if dst_w == 0 || dst_h == 0 || dst_w > RL_MAX_DIM || dst_h > RL_MAX_DIM {
        return Err(RL_ERR_UNSUPPORTED);
    }
    let mut dst = Image::alloc(src.fmt, dst_w, dst_h);
    let planar = src.planes.len() == 3;
    let channels = if planar {
        1u32
    } else {
        format_channels(src.fmt) as u32
    };
    for p in 0..src.planes.len() {
        let sub_x = planar && p > 0 && src.fmt != Fmt::Ycc444p;
        let sub_y = planar && p > 0 && src.fmt == Fmt::Ycc420p;
        let (sw, sh) = (src.planes[p].w, src.planes[p].h);
        let (pw, ph) = (dst.planes[p].w, dst.planes[p].h);
        let sdata = &src.planes[p].data;
        resize_plane(sdata, sw, sh, &mut dst.planes[p].data, pw, ph, channels, kernel, sub_x, sub_y);
    }
    Ok(dst)
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

const USAGE: &str = "usage: rasterlab <command> [args]\n  rasterlab info <in.rlr>\n  rasterlab checksum <in.rlr>\n  rasterlab convert -f <format> <in.rlr> <out.rlr>\n  rasterlab resize -w <width> -h <height> -k <kernel> <in.rlr> <out.rlr>\n  rasterlab chain <spec> <in.rlr> <out.rlr>\n";

fn fail_usage() -> i32 {
    eprint!("{}", USAGE);
    RL_ERR_USAGE
}

fn fail_read(path: &str, st: i32) -> i32 {
    if st == RL_ERR_UNREADABLE {
        eprintln!("rasterlab: cannot open '{}'", path);
    } else if st == RL_ERR_UNSUPPORTED {
        eprintln!("rasterlab: unsupported container '{}'", path);
    } else {
        eprintln!("rasterlab: corrupt container '{}'", path);
    }
    st
}

fn fail_write(path: &str) -> i32 {
    eprintln!("rasterlab: cannot write '{}'", path);
    RL_ERR_UNREADABLE
}

// Mirrors the legacy C guard exactly, including the documented wrap quirk:
// the overflow check fires BEFORE the multiply, so v == 429496729 followed
// by another digit wraps modulo 2^32 just like the reference.
fn parse_u32(s: &str) -> Option<u32> {
    let b = s.as_bytes();
    if b.is_empty() {
        return None;
    }
    let mut v: u32 = 0;
    for &c in b {
        if !c.is_ascii_digit() {
            return None;
        }
        if v > 429_496_729 {
            return None;
        }
        v = v.wrapping_mul(10).wrapping_add((c - b'0') as u32);
    }
    Some(v)
}

fn cmd_info(table: &[u32; 256], args: &[String]) -> i32 {
    if args.len() != 1 {
        return fail_usage();
    }
    let img = match read_file(table, &args[0]) {
        Ok(img) => img,
        Err(st) => return fail_read(&args[0], st),
    };
    let mut out = String::new();
    out.push_str(&format!("file: {}\n", args[0]));
    out.push_str(&format!("format: {} ({})\n", FMT_NAMES[img.fmt as usize], img.fmt as i32));
    out.push_str(&format!("width: {}\n", img.width));
    out.push_str(&format!("height: {}\n", img.height));
    out.push_str(&format!("planes: {}\n", img.planes.len()));
    let channels = if img.planes.len() == 1 {
        format_channels(img.fmt)
    } else {
        1
    };
    let mut payload = 0usize;
    for p in 0..img.planes.len() {
        let bytes = img.planes[p].w as usize * img.planes[p].h as usize * channels;
        out.push_str(&format!(
            "plane {}: {}x{} {} bytes\n",
            p, img.planes[p].w, img.planes[p].h, bytes
        ));
        payload += bytes;
    }
    out.push_str(&format!("payload: {} bytes\n", payload));
    out.push_str(&format!("crc32: {:08x}\n", container_crc(table, &img)));
    print!("{}", out);
    RL_OK
}

fn cmd_checksum(table: &[u32; 256], args: &[String]) -> i32 {
    if args.len() != 1 {
        return fail_usage();
    }
    let img = match read_file(table, &args[0]) {
        Ok(img) => img,
        Err(st) => return fail_read(&args[0], st),
    };
    let mut out = String::new();
    out.push_str(&format!("crc32: {:08x}\n", container_crc(table, &img)));
    let channels = if img.planes.len() == 1 {
        format_channels(img.fmt)
    } else {
        1
    };
    for p in 0..img.planes.len() {
        let bytes = img.planes[p].w as usize * img.planes[p].h as usize * channels;
        out.push_str(&format!("plane {}: {:08x}\n", p, plane_sum(&img.planes[p].data[..bytes])));
    }
    print!("{}", out);
    RL_OK
}

fn cmd_convert(table: &[u32; 256], args: &[String]) -> i32 {
    if args.len() != 4 || args[0] != "-f" {
        return fail_usage();
    }
    let fmt = match format_parse(&args[1]) {
        Some(f) => f,
        None => {
            eprintln!("rasterlab: unsupported format '{}'", args[1]);
            return RL_ERR_UNSUPPORTED;
        }
    };
    let src = match read_file(table, &args[2]) {
        Ok(img) => img,
        Err(st) => return fail_read(&args[2], st),
    };
    let dst = convert(&src, fmt);
    match write_file(table, &args[3], &dst) {
        Ok(()) => RL_OK,
        Err(_) => fail_write(&args[3]),
    }
}

fn cmd_resize(table: &[u32; 256], args: &[String]) -> i32 {
    if args.len() != 8 || args[0] != "-w" || args[2] != "-h" || args[4] != "-k" {
        return fail_usage();
    }
    let w = match parse_u32(&args[1]) {
        Some(v) => v,
        None => return fail_usage(),
    };
    let h = match parse_u32(&args[3]) {
        Some(v) => v,
        None => return fail_usage(),
    };
    if w == 0 || h == 0 || w > RL_MAX_DIM || h > RL_MAX_DIM {
        eprintln!("rasterlab: unsupported dimensions '{}x{}'", w, h);
        return RL_ERR_UNSUPPORTED;
    }
    let k = match kernel_parse(&args[5]) {
        Some(k) => k,
        None => {
            eprintln!("rasterlab: unsupported kernel '{}'", args[5]);
            return RL_ERR_UNSUPPORTED;
        }
    };
    let src = match read_file(table, &args[6]) {
        Ok(img) => img,
        Err(st) => return fail_read(&args[6], st),
    };
    let dst = match resize(&src, w, h, k) {
        Ok(img) => img,
        Err(st) => {
            eprintln!("rasterlab: resize failed");
            return st;
        }
    };
    match write_file(table, &args[7], &dst) {
        Ok(()) => RL_OK,
        Err(_) => fail_write(&args[7]),
    }
}

fn apply_chain_op(table: &[u32; 256], cur: &mut Image, op: &str) -> i32 {
    if let Some(rest) = op.strip_prefix("convert:") {
        let fmt = match format_parse(rest) {
            Some(f) => f,
            None => {
                eprintln!("rasterlab: unsupported format '{}'", rest);
                return RL_ERR_UNSUPPORTED;
            }
        };
        let next = convert(cur, fmt);
        *cur = next;
        return RL_OK;
    }
    if let Some(rest) = op.strip_prefix("resize:") {
        if rest.len() >= 128 {
            return fail_usage();
        }
        let xpos = match rest.find('x') {
            Some(p) => p,
            None => return fail_usage(),
        };
        let cpos = match rest.find(':') {
            Some(p) => p,
            None => return fail_usage(),
        };
        if cpos < xpos {
            return fail_usage();
        }
        let w = match parse_u32(&rest[..xpos]) {
            Some(v) => v,
            None => return fail_usage(),
        };
        let h = match parse_u32(&rest[xpos + 1..cpos]) {
            Some(v) => v,
            None => return fail_usage(),
        };
        if w == 0 || h == 0 || w > RL_MAX_DIM || h > RL_MAX_DIM {
            eprintln!("rasterlab: unsupported dimensions '{}x{}'", w, h);
            return RL_ERR_UNSUPPORTED;
        }
        let k = match kernel_parse(&rest[cpos + 1..]) {
            Some(k) => k,
            None => {
                eprintln!("rasterlab: unsupported kernel '{}'", &rest[cpos + 1..]);
                return RL_ERR_UNSUPPORTED;
            }
        };
        let next = match resize(cur, w, h, k) {
            Ok(img) => img,
            Err(st) => {
                eprintln!("rasterlab: resize failed");
                return st;
            }
        };
        *cur = next;
        return RL_OK;
    }
    let _ = table;
    fail_usage()
}

fn cmd_chain(table: &[u32; 256], args: &[String]) -> i32 {
    if args.len() != 3 {
        return fail_usage();
    }
    let mut cur = match read_file(table, &args[1]) {
        Ok(img) => img,
        Err(st) => return fail_read(&args[1], st),
    };
    for op in args[0].split(';') {
        if op.is_empty() {
            continue;
        }
        let rc = apply_chain_op(table, &mut cur, op);
        if rc != RL_OK {
            return rc;
        }
    }
    match write_file(table, &args[2], &cur) {
        Ok(()) => RL_OK,
        Err(_) => fail_write(&args[2]),
    }
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        exit(fail_usage());
    }
    let table = crc_table();
    let rest = &args[2..];
    let rc = match args[1].as_str() {
        "info" => cmd_info(&table, rest),
        "checksum" => cmd_checksum(&table, rest),
        "convert" => cmd_convert(&table, rest),
        "resize" => cmd_resize(&table, rest),
        "chain" => cmd_chain(&table, rest),
        other => {
            eprintln!("rasterlab: unknown command '{}'", other);
            RL_ERR_USAGE
        }
    };
    exit(rc);
}
