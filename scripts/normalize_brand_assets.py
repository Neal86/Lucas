from __future__ import annotations

import struct
import zlib
from pathlib import Path

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def normalize_png(path: Path, *, alpha_gain: float = 7.0, padding: int = 8) -> None:
    raw = path.read_bytes()
    if not raw.startswith(PNG_SIG):
        raise ValueError(f"Not PNG: {path}")

    pos = len(PNG_SIG)
    width = height = bit_depth = color_type = None
    idat = bytearray()
    while pos < len(raw):
        n = struct.unpack(">I", raw[pos:pos + 4])[0]
        kind = raw[pos + 4:pos + 8]
        data = raw[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            width, height, bit_depth, color_type, comp, filt, interlace = struct.unpack(">IIBBBBB", data)
            if bit_depth != 8 or color_type != 6 or interlace != 0:
                raise ValueError(f"Expected non-interlaced 8-bit RGBA PNG: {path}")
        elif kind == b"IDAT":
            idat.extend(data)
        elif kind == b"IEND":
            break

    assert width and height
    packed = zlib.decompress(bytes(idat))
    bpp = 4
    stride = width * bpp
    rows: list[bytearray] = []
    prev = bytearray(stride)
    off = 0
    for _ in range(height):
        ft = packed[off]
        off += 1
        src = packed[off:off + stride]
        off += stride
        out = bytearray(stride)
        for i, x in enumerate(src):
            a = out[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if ft == 0:
                v = x
            elif ft == 1:
                v = (x + a) & 255
            elif ft == 2:
                v = (x + b) & 255
            elif ft == 3:
                v = (x + ((a + b) >> 1)) & 255
            elif ft == 4:
                v = (x + _paeth(a, b, c)) & 255
            else:
                raise ValueError(f"Unsupported PNG filter {ft}")
            out[i] = v
        rows.append(out)
        prev = out

    # Find meaningful alpha content, crop excessive transparent canvas, then
    # make every visible logo pixel pure white and strengthen faint alpha.
    xs: list[int] = []
    ys: list[int] = []
    for y, row in enumerate(rows):
        for x in range(width):
            if row[x * 4 + 3] >= 3:
                xs.append(x)
                ys.append(y)
    if not xs:
        raise ValueError(f"No visible pixels in {path}")

    x0 = max(0, min(xs) - padding)
    x1 = min(width - 1, max(xs) + padding)
    y0 = max(0, min(ys) - padding)
    y1 = min(height - 1, max(ys) + padding)
    new_w = x1 - x0 + 1
    new_h = y1 - y0 + 1

    scan = bytearray()
    for y in range(y0, y1 + 1):
        scan.append(0)  # encode each row with PNG filter None
        row = rows[y]
        for x in range(x0, x1 + 1):
            alpha = row[x * 4 + 3]
            alpha = min(255, int(round(alpha * alpha_gain)))
            if alpha < 6:
                alpha = 0
            scan.extend((255, 255, 255, alpha))

    ihdr = struct.pack(">IIBBBBB", new_w, new_h, 8, 6, 0, 0, 0)
    out_png = PNG_SIG + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(bytes(scan), 9)) + _chunk(b"IEND", b"")
    path.write_bytes(out_png)
    print(f"normalized {path}: {width}x{height} -> {new_w}x{new_h}")


def main() -> None:
    assets = Path("src/gpt_windows_connector/assets")
    for name in ("lucas-logo-horizontal.png", "lucas-logo-square.png"):
        normalize_png(assets / name)


if __name__ == "__main__":
    main()
