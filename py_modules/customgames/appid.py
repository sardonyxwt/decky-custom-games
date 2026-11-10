"""Which Steam game a non-Steam folder is: its Steam AppID, found in the files the game carries.

Order: steam_appid.txt, emulator configs (CODEX/RUNE steam_emu.ini, Goldberg/GSE configs, CreamAPI, OnlineFix),
then the emulator's save folders inside the shortcut's Proton prefix (they are named after the AppID and
appear after the first launch). The Steam store name search is the caller's last resort.
"""

import os
import re
from typing import List, Optional, Tuple

ID_FILES = {"steam_appid.txt"}
INI_FILES = {"steam_emu.ini", "configs.app.ini", "configs.main.ini", "cream_api.ini", "onlinefix.ini", "codex.ini",
             "rune.ini", "steam_api.ini", "coldclientloader.ini", "steamconfig.ini", "ds.ini", "cpy.ini", "valve.ini"}
APPID_LINE = re.compile(r"^\s*(?:appid|app_id|real_app_id|realappid|gameid)\s*=\s*(\d{2,9})\b", re.I | re.M)
# Never the game: Spacewar (OnlineFix and test builds use it) and other Valve placeholders.
BOGUS = {0, 480, 218, 7, 753}
SAVE_DIRS = [
    "users/steamuser/AppData/Roaming/GSE Saves",
    "users/steamuser/AppData/Roaming/Goldberg SteamEmu Saves",
    "users/steamuser/AppData/Roaming/EMPRESS",
    "users/steamuser/AppData/Roaming/Steam/CODEX",
    "users/Public/Documents/Steam/RUNE",
    "users/Public/Documents/Steam/CODEX",
    "users/Public/Documents/Steam/EMPRESS",
    "users/Public/Documents/OnlineFix",
    "users/steamuser/Documents/Steam/CODEX",
]
MAX_DEPTH = 5


def valid(n: int) -> bool:
    return n not in BOGUS and 10 <= n < 100_000_000


def from_files(root: str, exe: str = "") -> Optional[Tuple[int, str]]:
    """(appid, "file:<relative path>") from the game folder; files next to the exe are checked first."""
    dirs: List[str] = []
    if exe:
        d = os.path.dirname(exe)
        while d.startswith(root) and d not in dirs:
            dirs.append(d)
            if d == root:
                break
            d = os.path.dirname(d)
    hits: List[Tuple[int, int, str]] = []  # (priority, appid, path)
    base = root.rstrip("/").count("/")
    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath.count("/") - base >= MAX_DEPTH:
            dirnames[:] = []
        for fn in filenames:
            low = fn.lower()
            if low not in ID_FILES and low not in INI_FILES:
                continue
            p = os.path.join(dirpath, fn)
            n = _read_id(p, low)
            if n is None:
                continue
            near = 0 if dirpath in dirs or os.path.dirname(dirpath) in dirs else 1
            backup = 1 if re.search(r"backup|crack[\\/]|_crack", os.path.relpath(p, root), re.I) else 0
            hits.append(((near, backup, 0 if low in ID_FILES else 1), n, p))
    if not hits:
        return None
    hits.sort(key=lambda h: h[0])
    _, n, p = hits[0]
    return n, "file:" + os.path.relpath(p, root)


def _read_id(path: str, low: str) -> Optional[int]:
    try:
        with open(path, "rb") as f:
            text = f.read(65536).decode("utf-8", errors="replace").lstrip("﻿")
    except OSError:
        return None
    if low in ID_FILES:
        m = re.match(r"\s*(\d{2,9})", text)
    else:
        m = APPID_LINE.search(text)
    if not m:
        return None
    n = int(m.group(1))
    return n if valid(n) else None


def from_prefix(prefixes: List[str]) -> Optional[Tuple[int, str]]:
    """(appid, "prefix:<emulator folder>") from emulator save folders in Proton prefixes."""
    best: Optional[Tuple[float, int, str]] = None
    for pfx in prefixes:
        for rel in SAVE_DIRS:
            d = os.path.join(pfx, "drive_c", rel)
            try:
                names = os.listdir(d)
            except OSError:
                continue
            for name in names:
                if not name.isdigit() or not valid(int(name)):
                    continue
                t = os.path.getmtime(os.path.join(d, name))
                if best is None or t > best[0]:
                    best = (t, int(name), rel.split("/")[-1])
    if best is None:
        return None
    return best[1], "prefix:" + best[2]


def achievement_files(prefixes: List[str], steam_appid: int) -> List[str]:
    """Emulator achievement files for this AppID (GSE achievements.json, RUNE/CODEX achievements.ini)."""
    out = []
    for pfx in prefixes:
        for rel in SAVE_DIRS:
            d = os.path.join(pfx, "drive_c", rel, str(steam_appid))
            for fn in ("achievements.json", "achievements.ini", os.path.join("stats", "achievements.ini")):
                p = os.path.join(d, fn)
                if os.path.isfile(p):
                    out.append(p)
    return out
