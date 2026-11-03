"""Library artwork: official Steam art for new games, and keeping every library image at the size Steam shows.

Steam keeps custom artwork in userdata/<user>/config/grid as <appid>p.* (portrait), <appid>.* (wide),
<appid>_hero.*, <appid>_logo.* and <appid>.json (logo position). The plugin records the SHA-256 of every image
it has seen in artwork.json. A file whose hash is new was changed by someone else (the SteamGridDB plugin,
Steam's own "set custom artwork", a script). Smaller than the target, it is upscaled on the GPU; bigger, it is
scaled down (oversized pictures make scrolling the library slower). The result goes back through Steam's API,
so Steam shows it at once, and its hash is recorded as ours.
"""

import json
import os
import re
import shutil
import time
import urllib.parse
from typing import Dict, List, Optional

from . import images, net

# Steam asset types for SteamClient.Apps.SetCustomArtworkForApp / ClearCustomArtworkForApp
ASSET_TYPE = {"portrait": 0, "hero": 1, "logo": 2, "wide": 3}
SUFFIX = {"p": "portrait", "_hero": "hero", "_logo": "logo", "": "wide"}
GRID_FILE = re.compile(r"^(\d+)(p|_hero|_logo|)\.(png|jpg|jpeg|webp)$", re.I)
EDITABLE = ("png", "jpg", "webp")

# Target sizes: 2x Steam's capsules for sharp covers on a TV, and the 5760x1860 heroes the library already uses.
TARGET = {"portrait": (1200, 1800), "wide": (1840, 860), "hero": (5760, 1860)}
LOGO_MIN_WIDTH = 1000   # smaller logos get upscaled to 2x
LOGO_MAX_WIDTH = 2400   # bigger ones are scaled down to this width
SMALL = 0.9             # upscale when the image is below 90% of the target width
BIG = 1.02              # scale down when it is wider than the target
ASPECT_TOLERANCE = 0.04

STEAM_CDN = "https://cdn.cloudflare.steamstatic.com/steam/apps"
STEAM_FILES = {
    "portrait": ["library_600x900_2x.jpg", "library_600x900.jpg"],
    "hero": ["library_hero_2x.jpg", "library_hero.jpg"],
    "logo": ["logo_2x.png", "logo.png"],
    "wide": ["header.jpg"],
}
DEFAULT_LOGO_POS = {"pinnedPosition": "BottomLeft", "nWidthPct": 50.0, "nHeightPct": 50.0}


def is_shortcut(appid: int) -> bool:
    return appid >= 0x80000000


def needs_upscale(kind: str, w: int, h: int) -> bool:
    if kind == "logo":
        return 0 < w < LOGO_MIN_WIDTH
    tw, _ = TARGET[kind]
    return 0 < w < tw * SMALL


def needs_downscale(kind: str, w: int, h: int) -> bool:
    if kind == "logo":
        return w > LOGO_MAX_WIDTH
    return w > TARGET[kind][0] * BIG


def upscale_size(kind: str, w: int, h: int):
    """(width, height or None): exact target when the shape matches, else the target width keeping the shape."""
    if kind == "logo":
        return min(w * 2, LOGO_MAX_WIDTH), None
    tw, th = TARGET[kind]
    if h and abs((w / h) / (tw / th) - 1) <= ASPECT_TOLERANCE:
        return tw, th
    return tw, None


def fit_size(kind: str, w: int, h: int, action: str):
    """Exact (width, height) of the result."""
    if action == "down" and kind == "logo":
        width, height = LOGO_MAX_WIDTH, None
    else:
        width, height = upscale_size(kind, w, h)
    return width, height or max(1, round(h * width / w))


def action_for(kind: str, w: int, h: int, fmt: str) -> Optional[str]:
    if fmt not in EDITABLE or not w or not h:
        return None
    if needs_upscale(kind, w, h):
        return "up"
    if needs_downscale(kind, w, h):
        return "down"
    return None


def _fmt_of(path: str) -> str:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return "jpg" if ext == "jpeg" else ext


def _job(appid: int, kind: str, path: str, sha: str, w: int, h: int, fmt: str, action: str) -> dict:
    width, height = fit_size(kind, w, h, action)
    return {"appid": appid, "kind": kind, "path": path, "sha": sha, "w": w, "h": h, "fmt": fmt,
            "action": action, "width": width, "height": height}


class Manifest:
    """artwork.json: appid -> kind -> {sha, size, mtime, w, h, by, status}."""

    def __init__(self, path: str):
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                self.data: Dict[str, Dict[str, dict]] = json.load(f)
        except (OSError, ValueError):
            self.data = {}

    def get(self, appid: int, kind: str) -> Optional[dict]:
        return self.data.get(str(appid), {}).get(kind)

    def put(self, appid: int, kind: str, rec: dict) -> None:
        self.data.setdefault(str(appid), {})[kind] = rec

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1, sort_keys=True)
        os.replace(tmp, self.path)


def grid_files(grid: str) -> Dict[tuple, str]:
    """(appid, kind) -> newest file. Several extensions of one kind can coexist; Steam's API clears them on set."""
    out: Dict[tuple, str] = {}
    try:
        names = os.listdir(grid)
    except OSError:
        return out
    for fn in names:
        m = GRID_FILE.match(fn)
        if not m:
            continue
        key = (int(m.group(1)), SUFFIX[m.group(2).lower()])
        p = os.path.join(grid, fn)
        if key not in out or os.path.getmtime(p) > os.path.getmtime(out[key]):
            out[key] = p
    return out


def scan_changes(grid: str, manifest: Manifest, include_steam_games: bool, only: Optional[set] = None) -> List[dict]:
    """Images that are not at their size: [{appid, kind, path, sha, w, h, fmt, action: up|down, width, height}].
    Records everything it looks at in the manifest; a failed picture is not retried until it changes."""
    jobs = []
    for (appid, kind), path in sorted(grid_files(grid).items()):
        if only is not None and appid not in only:
            continue
        if not include_steam_games and not is_shortcut(appid):
            continue
        try:
            st = os.stat(path)
        except OSError:
            continue
        rec = manifest.get(appid, kind)
        unchanged = rec and rec.get("size") == st.st_size and rec.get("mtime") == int(st.st_mtime) \
            and rec.get("file") == path
        if not unchanged:
            sha = images.sha256(path)
            if rec and rec.get("sha") == sha:
                rec.update(size=st.st_size, mtime=int(st.st_mtime), file=path)
            else:
                meta = images.info(path)
                w, h, fmt = meta if meta else (0, 0, "")
                rec = {"sha": sha, "size": st.st_size, "mtime": int(st.st_mtime), "file": path, "w": w, "h": h,
                       "fmt": fmt, "by": "other", "status": "ok", "t": int(time.time())}
                manifest.put(appid, kind, rec)
        if rec.get("status") == "failed":
            continue
        action = action_for(kind, rec.get("w", 0), rec.get("h", 0), rec.get("fmt") or _fmt_of(path))
        if action:
            if rec.get("status") != "done":
                rec["status"] = "pending"
            jobs.append(_job(appid, kind, path, rec["sha"], rec["w"], rec["h"], rec.get("fmt") or _fmt_of(path), action))
        elif rec.get("status") == "pending":
            rec["status"] = "ok"
    return jobs


def record_applied(grid: str, manifest: Manifest, appid: int, kind: str, source: str, src_sha: str = "") -> Optional[dict]:
    """After Steam wrote our image: remember its hash as ours so the scan does not treat it as a change."""
    path = grid_files(grid).get((appid, kind))
    if not path:
        return None
    st = os.stat(path)
    meta = images.info(path) or (0, 0, "")
    rec = {"sha": images.sha256(path), "size": st.st_size, "mtime": int(st.st_mtime), "file": path,
           "w": meta[0], "h": meta[1], "fmt": meta[2], "by": "plugin", "source": source, "status": "done", "t": int(time.time())}
    if src_sha:
        rec["from_sha"] = src_sha
    manifest.put(appid, kind, rec)
    return rec


def mark_failed(manifest: Manifest, appid: int, kind: str, error: str) -> None:
    rec = manifest.get(appid, kind) or {}
    rec.update(status="failed", error=error[-300:], t=int(time.time()))
    manifest.put(appid, kind, rec)


# ---------------- artwork for a new game: the official Steam art ----------------

class Picker:
    def __init__(self, workdir: str):
        self.workdir = workdir

    def download(self, url: str, name: str) -> str:
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower() or ".png"
        dest = os.path.join(self.workdir, name + ext)
        net.download(url, dest)
        return dest

    def steam_official(self, kind: str, steam_appid: int, extra: Optional[dict], name: str) -> Optional[str]:
        """The store's own library art. Links from the client's store cache come first (newer games keep their
        assets under hashed paths), then the classic CDN names."""
        urls = [f"{STEAM_CDN}/{steam_appid}/{fn}" for fn in STEAM_FILES.get(kind, [])]
        if extra and extra.get(kind):
            urls.insert(0, extra[kind])
        for url in urls:
            try:
                p = self.download(url, name)
                if os.path.getsize(p) > 2000 and images.info(p):
                    return p
            except net.NetError:
                continue
        return None

    def pick(self, steam_appid: int, kinds: List[str], steam_assets: Optional[dict] = None) -> dict:
        """Downloads each kind: {"files": {kind: path}, "source": {kind: text}, "logo_pos"}. Kinds Steam has no
        official art for stay empty: the user picks those with the SteamGridDB plugin, and the queue resizes them."""
        os.makedirs(self.workdir, exist_ok=True)
        files, source = {}, {}
        for kind in kinds:
            p = self.steam_official(kind, steam_appid, steam_assets, f"{steam_appid}_{kind}_{int(time.time())}")
            if p and kind == "icon":
                p = icon_png(p)
            if p:
                files[kind], source[kind] = p, "Steam"
        return {"files": files, "source": source, "logo_pos": dict(DEFAULT_LOGO_POS) if "logo" in files else None}


def icon_png(path: str) -> Optional[str]:
    """PNG icon as is; from an .ico the biggest embedded PNG frame (Vista+ icons keep 256 px as PNG)."""
    meta = images.info(path)
    if not meta:
        return None
    if meta[2] in ("png", "jpg"):
        return path
    if meta[2] != "ico":
        return None
    with open(path, "rb") as f:
        b = f.read()
    n = int.from_bytes(b[4:6], "little")
    best = None
    for k in range(n):
        e = b[6 + 16 * k: 22 + 16 * k]
        size, off = int.from_bytes(e[8:12], "little"), int.from_bytes(e[12:16], "little")
        frame = b[off:off + size]
        if frame[:8] == b"\x89PNG\r\n\x1a\n":
            w = (e[0] or 256)
            if best is None or w > best[0]:
                best = (w, frame)
    if not best:
        return None
    out = os.path.splitext(path)[0] + ".png"
    with open(out, "wb") as f:
        f.write(best[1])
    return out


def install_icon(src: str, grid: str, appid: int) -> str:
    """Icons are not found by name: Steam reads the shortcut's icon field, so the file must stay put."""
    os.makedirs(grid, exist_ok=True)
    ext = ".png" if (images.info(src) or (0, 0, "png"))[2] == "png" else ".jpg"
    dest = os.path.join(grid, f"{appid}_icon{ext}")
    shutil.copyfile(src, dest + ".tmp")
    os.replace(dest + ".tmp", dest)
    return dest
