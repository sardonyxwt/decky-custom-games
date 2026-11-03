"""Where Steam lives on this machine: root, active user, library folders, shortcuts, grid and Proton prefixes."""

import os
import re
import struct
from typing import Dict, List, Optional

STEAMID64_BASE = 76561197960265728
_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')


def parse_vdf(text: str) -> dict:
    """Valve KeyValues text (libraryfolders.vdf, loginusers.vdf, config.vdf)."""
    stack: List[dict] = [{}]
    key: Optional[str] = None
    for m in _TOKEN.finditer(text):
        s, brace = m.group(1), m.group(2)
        if brace == "{":
            new: dict = {}
            if key is not None:
                stack[-1][key] = new
            stack.append(new)
            key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        else:
            s = s.replace('\\"', '"').replace("\\\\", "\\")
            if key is None:
                key = s
            else:
                stack[-1][key] = s
                key = None
    return stack[0]


def parse_binary_vdf(data: bytes) -> dict:
    """Valve binary KeyValues (shortcuts.vdf): 0x00 map, 0x01 string, 0x02 int32, 0x07 uint64, 0x08 end of map."""
    pos = 0

    def cstr() -> str:
        nonlocal pos
        end = data.index(b"\x00", pos)
        s = data[pos:end].decode("utf-8", errors="replace")
        pos = end + 1
        return s

    def read_map() -> dict:
        nonlocal pos
        out: dict = {}
        while pos < len(data):
            t = data[pos]
            pos += 1
            if t == 0x08:
                return out
            name = cstr()
            if t == 0x00:
                out[name] = read_map()
            elif t == 0x01:
                out[name] = cstr()
            elif t == 0x02:
                out[name] = struct.unpack_from("<I", data, pos)[0]
                pos += 4
            elif t == 0x07:
                out[name] = struct.unpack_from("<Q", data, pos)[0]
                pos += 8
            else:
                raise ValueError(f"unknown binary VDF type {t:#x} at {pos - 1}")
        return out

    return read_map()


def _ci(d: dict, k: str):
    for kk, v in d.items():
        if kk.lower() == k.lower():
            return v
    return None


def steam_root(home: str) -> Optional[str]:
    """The Steam installation that has user data (native first, then Flatpak/Snap)."""
    candidates = [
        ".steam/steam", ".local/share/Steam", ".steam/root", ".steam/debian-installation",
        ".var/app/com.valvesoftware.Steam/.local/share/Steam", "snap/steam/common/.local/share/Steam",
    ]
    for c in candidates:
        p = os.path.join(home, c)
        if os.path.isdir(os.path.join(p, "userdata")) and os.path.isdir(os.path.join(p, "steamapps")):
            return os.path.realpath(p)
    return None


def active_user(root: str) -> Optional[str]:
    """32-bit account id of the user Steam last logged in (loginusers.vdf MostRecent), else the busiest userdata."""
    try:
        with open(os.path.join(root, "config", "loginusers.vdf"), encoding="utf-8", errors="replace") as f:
            users = _ci(parse_vdf(f.read()), "users") or {}
        for sid, u in users.items():
            if isinstance(u, dict) and str(_ci(u, "MostRecent")) == "1" and sid.isdigit():
                return str(int(sid) - STEAMID64_BASE)
    except OSError:
        pass
    best, best_t = None, -1.0
    ud = os.path.join(root, "userdata")
    for name in os.listdir(ud) if os.path.isdir(ud) else []:
        sc = os.path.join(ud, name, "config", "shortcuts.vdf")
        if name.isdigit() and name != "0" and os.path.isfile(sc) and os.path.getmtime(sc) > best_t:
            best, best_t = name, os.path.getmtime(sc)
    return best


def library_folders(root: str) -> List[str]:
    libs, seen = [], set()

    def add(p: str):
        real = os.path.realpath(p)
        if real not in seen and os.path.isdir(os.path.join(real, "steamapps")):
            seen.add(real)
            libs.append(real)

    add(root)
    try:
        with open(os.path.join(root, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="replace") as f:
            lf = _ci(parse_vdf(f.read()), "libraryfolders") or {}
        for v in lf.values():
            if isinstance(v, dict) and _ci(v, "path"):
                add(_ci(v, "path"))
    except OSError:
        pass
    return libs


def unquote(p: str) -> str:
    p = (p or "").strip()
    if len(p) >= 2 and p[0] == p[-1] == '"':
        p = p[1:-1]
    return p


def read_shortcuts(root: str, user: str) -> List[Dict]:
    """Non-Steam shortcuts of the user: appid (unsigned), name, exe, start dir, launch options, icon."""
    path = os.path.join(root, "userdata", user, "config", "shortcuts.vdf")
    try:
        with open(path, "rb") as f:
            data = parse_binary_vdf(f.read())
    except (OSError, ValueError):
        return []
    out = []
    for entry in (_ci(data, "shortcuts") or {}).values():
        if not isinstance(entry, dict):
            continue
        appid = _ci(entry, "appid")
        if appid is None:
            continue
        out.append({
            "appid": int(appid) & 0xFFFFFFFF,
            "name": _ci(entry, "AppName") or "",
            "exe": unquote(_ci(entry, "Exe") or ""),
            "start_dir": unquote(_ci(entry, "StartDir") or ""),
            "launch_options": _ci(entry, "LaunchOptions") or "",
            "icon": _ci(entry, "icon") or "",
        })
    return out


def grid_dir(root: str, user: str) -> str:
    return os.path.join(root, "userdata", user, "config", "grid")


def prefix_dirs(libs: List[str], shortcut_appid: int) -> List[str]:
    """Proton prefixes of a shortcut (Steam puts compatdata into the first library, usually the root)."""
    out = []
    for lib in libs:
        p = os.path.join(lib, "steamapps", "compatdata", str(shortcut_appid), "pfx")
        if os.path.isdir(p):
            out.append(p)
    return out


def installed_steam_dirs(libs: List[str]) -> List[str]:
    """steamapps/common of every library: games there belong to Steam itself."""
    return [os.path.join(lib, "steamapps", "common") for lib in libs]
