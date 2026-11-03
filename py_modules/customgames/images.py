"""Image size and format from the file header (no Pillow in Decky's Python), and content hashes."""

import hashlib
import struct
from typing import Optional, Tuple


def info(path: str) -> Optional[Tuple[int, int, str]]:
    """(width, height, "png"|"jpg"|"webp"|"gif"|"ico") or None. Steam sniffs content, so the extension can lie."""
    try:
        with open(path, "rb") as f:
            b = f.read(262144)
    except OSError:
        return None
    return info_bytes(b)


def info_bytes(b: bytes) -> Optional[Tuple[int, int, str]]:
    if b[:8] == b"\x89PNG\r\n\x1a\n" and len(b) >= 24:
        w, h = struct.unpack(">II", b[16:24])
        return w, h, "png"
    if b[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(b):
            if b[i] != 0xFF:
                i += 1
                continue
            m = b[i + 1]
            if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
                i += 2
                continue
            if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", b[i + 5:i + 9])
                return w, h, "jpg"
            i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
        return None
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        chunk = b[12:16]
        if chunk == b"VP8 " and len(b) >= 30:
            w, h = struct.unpack("<HH", b[26:30])
            return w & 0x3FFF, h & 0x3FFF, "webp"
        if chunk == b"VP8L" and len(b) >= 25:
            v = int.from_bytes(b[21:25], "little")
            return (v & 0x3FFF) + 1, ((v >> 14) & 0x3FFF) + 1, "webp"
        if chunk == b"VP8X" and len(b) >= 30:
            return int.from_bytes(b[24:27], "little") + 1, int.from_bytes(b[27:30], "little") + 1, "webp"
        return None
    if b[:6] in (b"GIF87a", b"GIF89a"):
        w, h = struct.unpack("<HH", b[6:10])
        return w, h, "gif"
    if b[:4] == b"\x00\x00\x01\x00" and len(b) >= 22:
        n = struct.unpack("<H", b[4:6])[0]
        sizes = [((b[6 + 16 * k] or 256), (b[7 + 16 * k] or 256)) for k in range(min(n, (len(b) - 6) // 16))]
        if sizes:
            w, h = max(sizes)
            return w, h, "ico"
    return None


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
