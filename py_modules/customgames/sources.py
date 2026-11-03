"""Where non-Steam games come from: game folders the user lists, and Anker Launcher's library."""

import json
import os
import re
import time
from typing import Dict, Iterable, List, Optional

from . import exepick
from .store import title_from_folder

SKIP_TOP = re.compile(r"^(_|\.)|^(saves?|downloads?|incoming|temp|tmp|backup|backups|prefixes|ankergames|"
                      r"steam|steamlibrary|steamapps|lost\+found)$", re.I)
BUSY_SUFFIXES = (".part", ".crdownload", ".!qb", ".aria2", ".tmp", ".partial")
SETTLE_SECONDS = 120


def _real(p: str) -> str:
    return os.path.realpath(p.rstrip("/")) if p else ""


def _inside(path: str, parent: str) -> bool:
    path, parent = _real(path), _real(parent)
    return path == parent or path.startswith(parent + "/")


def _busy(root: str, now: float) -> bool:
    """Still being downloaded or unpacked: a temporary file, or anything written in the last two minutes."""
    for dirpath, dirnames, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith(BUSY_SUFFIXES):
                return True
        try:
            if now - os.path.getmtime(dirpath) < SETTLE_SECONDS:
                return True
        except OSError:
            pass
    return False


def anker_exe(root: str, rel: str, anchor: str) -> str:
    """Where Anker's exe really is. The profile's path is the repack's default and often not where the files
    ended up; games added to Anker by hand carry the real relative path as the adoption "anchor", and Anker's
    own installs keep the game one folder down. So: anchor, the profile path, the exe's name anywhere inside,
    and our own rules last."""
    for cand in (anchor, rel):
        if cand:
            p = os.path.normpath(os.path.join(root, cand))
            if os.path.isfile(p):
                return p
    name = os.path.basename(rel or anchor).lower()
    if name:
        hits = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not exepick.SKIP_DIR.match(d)]
            hits += [os.path.join(dirpath, f) for f in filenames if f.lower() == name]
        if hits:
            return min(hits, key=lambda h: h.count("/"))
    return exepick.best(root)[0]


def anker_games(home: str, steam_dirs: List[str]) -> List[Dict]:
    """Installed games from Anker Launcher's library.json (a Linux AppImage launcher for AnkerGames repacks)."""
    cfg = os.path.join(home, ".config", "net.ankergames.launcher")
    try:
        with open(os.path.join(cfg, "library.json"), encoding="utf-8") as f:
            lib = json.load(f)
    except (OSError, ValueError):
        return []
    games = lib.get("games") or {}
    out = []
    for g in (games.values() if isinstance(games, dict) else games):
        if not isinstance(g, dict) or g.get("uninstalling"):
            continue
        root = g.get("root") or ""
        if not root or not os.path.isdir(root) or any(_inside(root, d) for d in steam_dirs):
            continue
        prof = (g.get("launch_profiles") or [{}])[0] or {}
        exe = anker_exe(root, prof.get("executable") or g.get("executable") or "",
                        (g.get("adoption") or {}).get("anchor") or "")
        if not exe:
            continue
        workdir = prof.get("working_dir")
        out.append({
            "source": "anker",
            "title": g.get("title") or title_from_folder(os.path.basename(root)),
            "root": _real(root),
            "exe": exe,
            "start_dir": os.path.normpath(os.path.join(root, workdir)) if workdir else os.path.dirname(exe),
            "launch_options": prof.get("arguments") or "",
            "ambiguous": False,
            "anker_id": g.get("game_id"),
        })
    return out


def folder_games(roots: Iterable[str], steam_dirs: List[str], skip: Iterable[str] = ()) -> List[Dict]:
    """One candidate per top-level folder of every games folder."""
    skip_real = {_real(s) for s in skip}
    out = []
    for base in roots:
        try:
            entries = sorted(os.scandir(base), key=lambda e: e.name.lower())
        except OSError:
            continue
        for e in entries:
            if not e.is_dir(follow_symlinks=True) or SKIP_TOP.search(e.name):
                continue
            root = _real(e.path)
            if root in skip_real or any(_inside(root, d) for d in steam_dirs):
                continue
            out.append({"source": "folder", "title": title_from_folder(e.name), "root": root,
                        "exe": "", "start_dir": "", "launch_options": "", "ambiguous": False})
    return out


def anker_roots(home: str) -> List[str]:
    return [g["root"] for g in anker_games(home, [])]


def game_root(path: str, game_dirs: Iterable[str], known_roots: Iterable[str] = ()) -> str:
    """The game's own folder for a file inside it: the first folder under a games folder, stepping over
    containers such as AnkerGames/Games; outside the games folders a known (Anker) game root; else the file's folder."""
    path = _real(path)
    for base in game_dirs:
        base = _real(base)
        if not path.startswith(base + "/"):
            continue
        cur = base
        for part in path[len(base) + 1:].split("/")[:-1]:
            cur = os.path.join(cur, part)
            if not CONTAINER.match(part):
                return cur
    best = ""
    for r in known_roots:
        if _inside(path, r) and len(_real(r)) > len(best):
            best = _real(r)
    return best or os.path.dirname(path)


CONTAINER = re.compile(r"^(ankergames|games|library|installed|common)$", re.I)


def already_in_steam(cand: Dict, shortcuts: List[Dict], game_dirs: Iterable[str] = ()) -> Optional[Dict]:
    """The shortcut that already launches this game: same exe, or any exe inside the game's folder
    (the whole top folder under a games folder: Anker sometimes records a subfolder as the root)."""
    roots = {cand["root"]}
    for base in game_dirs:
        if _inside(cand["root"], base):
            roots.add(game_root(os.path.join(cand["root"], "x"), [base]))
    for s in shortcuts:
        exe = s.get("exe") or ""
        if not exe:
            continue
        if cand.get("exe") and _real(exe) == _real(cand["exe"]):
            return s
        for r in roots:
            if _inside(exe, r) or (s.get("start_dir") and _inside(s["start_dir"], r)):
                return s
    return None


def find_new(home: str, game_roots: List[str], use_anker: bool, steam_dirs: List[str], shortcuts: List[Dict],
             hidden: Iterable[str] = ()) -> Dict[str, List[Dict]]:
    """{"new": ready to add, "busy": still being written, "no_exe": nothing launchable found}."""
    now = time.time()
    hidden_real = {_real(h) for h in hidden}
    anker = anker_games(home, steam_dirs) if use_anker else []
    found: List[Dict] = list(anker)
    for c in folder_games(game_roots, steam_dirs):
        # Anker knows its games better (exe, arguments); skip folders that contain or sit inside an Anker game.
        if any(_inside(a["root"], c["root"]) or _inside(c["root"], a["root"]) for a in anker):
            continue
        found.append(c)
    res: Dict[str, List[Dict]] = {"new": [], "busy": [], "no_exe": []}
    for c in found:
        if c["root"] in hidden_real or already_in_steam(c, shortcuts, game_roots):
            continue
        if _busy(c["root"], now):
            res["busy"].append(c)
            continue
        if not c["exe"]:
            c["exe"], c["ambiguous"] = exepick.best(c["root"])
            c["start_dir"] = os.path.dirname(c["exe"]) if c["exe"] else ""
        if not c["exe"]:
            res["no_exe"].append(c)
            continue
        if already_in_steam(c, shortcuts, game_roots):
            continue
        res["new"].append(c)
    return res
