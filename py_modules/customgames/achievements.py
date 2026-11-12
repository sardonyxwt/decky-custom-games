"""Achievement progress that Steam emulators in repacks keep inside the Proton prefix.

GSE / Goldberg: achievements.json  {"API_NAME": {"earned": true, "earned_time": 1792792307}, ...}
RUNE / CODEX:   achievements.ini   [API_NAME] Achieved=1 CurProgress=0 MaxProgress=0 UnlockTime=1792954717
"""

import json
import os
from typing import Dict, List


def read(paths: List[str]) -> Dict[str, dict]:
    """API name -> {"earned": bool, "time": unix seconds, "cur": n, "max": n}; the newest file wins per name."""
    out: Dict[str, dict] = {}
    for p in sorted(paths, key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0):
        try:
            got = _read_json(p) if p.endswith(".json") else _read_ini(p)
        except (OSError, ValueError):
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
    # Read by hand, not with configparser: RUNE sometimes writes a nameless "[]" section first (Death Stranding 2),
    # and configparser then rejects the whole file.
    sections: Dict[str, Dict[str, str]] = {}
    cur = None
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in ";#":
                continue
            if line.startswith("[") and line.endswith("]"):
                name = line[1:-1].strip()
                cur = sections.setdefault(name, {}) if name else None  # a nameless section is skipped
            elif cur is not None and "=" in line:
                k, v = line.split("=", 1)
                cur[k.strip().lower()] = v.strip()
    out = {}
    for name, s in sections.items():
        if name.lower() in ("steamachievements", "settings"):  # CODEX header section with a count
            continue

        def num(k: str) -> int:
            try:
                return int(float(s.get(k, "0") or 0))
            except ValueError:
                return 0

        out[name] = {"earned": num("achieved") == 1, "time": num("unlocktime"),
                     "cur": num("curprogress"), "max": num("maxprogress")}
    return out
