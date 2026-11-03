"""Achievement progress that Steam emulators in repacks keep inside the Proton prefix.

GSE / Goldberg: achievements.json  {"API_NAME": {"earned": true, "earned_time": 1792792307}, ...}
RUNE / CODEX:   achievements.ini   [API_NAME] Achieved=1 CurProgress=0 MaxProgress=0 UnlockTime=1792954717
"""

import configparser
import json
import os
from typing import Dict, List


def read(paths: List[str]) -> Dict[str, dict]:
    """API name -> {"earned": bool, "time": unix seconds, "cur": n, "max": n}; the newest file wins per name."""
    out: Dict[str, dict] = {}
    for p in sorted(paths, key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0):
        try:
            got = _read_json(p) if p.endswith(".json") else _read_ini(p)
        except (OSError, ValueError, configparser.Error):
            continue
        for k, v in got.items():
            if v["earned"] or k not in out:
                out[k] = v
    return out


def _read_json(path: str) -> Dict[str, dict]:
    with open(path, encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    out = {}
    if isinstance(data, dict):
        for name, v in data.items():
            if isinstance(v, dict):
                out[name] = {"earned": bool(v.get("earned")), "time": int(v.get("earned_time") or 0),
                             "cur": int(v.get("progress") or 0), "max": int(v.get("max_progress") or 0)}
    return out


def _read_ini(path: str) -> Dict[str, dict]:
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str  # keep API names as they are
    with open(path, encoding="utf-8", errors="replace") as f:
        cp.read_file(f)
    out = {}
    for name in cp.sections():
        if name.lower() in ("steamachievements", "settings"):  # CODEX header section with a count
            continue
        s = cp[name]

        def num(k: str) -> int:
            try:
                return int(float(s.get(k, "0") or 0))
            except ValueError:
                return 0

        out[name] = {"earned": num("Achieved") == 1 or num("achieved") == 1, "time": num("UnlockTime"),
                     "cur": num("CurProgress"), "max": num("MaxProgress")}
    return out
