"""Choosing the game's executable inside a game folder.

Rules learned from real repacks (see the import skill): the launcher at the game folder's root wins
(SB.exe, b1.exe, AOW4.exe); Unreal also ships Binaries/Win64/*-Shipping.exe, used only when there is no
root exe (Split Fiction, REANIMAL); of several builds (Hades: x64, x64Vk, x86) the Vulkan one runs best
under Proton; redistributables, crash reporters, installers and crack backups are never the game.
"""

import difflib
import os
import re
from typing import List, Tuple

SKIP_FILE = re.compile(
    r"(redist|crash|unins|vcredist|dxsetup|dxwebsetup|setup|easyanticheat|eac_|battleye|be_service|prereq|dotnet|"
    r"vc_redist|physx|dowser|cpatch|xdelta|epiconlineservices|benchmark|editor|wallpaper|soundtrack|webhelper|"
    r"cefsubprocess|crs-handler|crs-uploader|unitycrashhandler|notification_helper|quicksfv|7z|winrar|"
    r"dxdiag|directx|oalinst|ue4prereq|ueprereq|reporter|updater|patcher|touchup|cleanup)", re.I)
SKIP_DIR = re.compile(
    r"^(redist|_commonredist|commonredist|directx|vcredist|dotnet|support|crack|backup crack.*|_crack|__installer|"
    r"installer|installers|prerequisites|extras|soundtrack|ost|artbook|engine|easyanticheat|battleye|"
    r"\$pluginsdir|_redist|redistributables|tools)$", re.I)
WEAK_NAME = re.compile(r"^(launcher|start|play|config|settings|setup|run|game_launcher)\b", re.I)
MAX_DEPTH = 6
MIN_SIZE = 60 * 1024


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def candidates(root: str) -> List[str]:
    """All plausible game executables under root, best first (absolute paths)."""
    found: List[Tuple[tuple, str]] = []
    title = _norm(os.path.basename(root.rstrip("/")))
    base_depth = root.rstrip("/").count("/")
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath.count("/") - base_depth
        dirnames[:] = [d for d in dirnames if not SKIP_DIR.match(d) and depth < MAX_DEPTH]
        for fn in filenames:
            if not fn.lower().endswith(".exe") or SKIP_FILE.search(fn):
                continue
            p = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            if size < MIN_SIZE:
                continue
            rel = os.path.relpath(p, root)
            stem = _norm(os.path.splitext(fn)[0])
            vulkan = any(re.search(r"(^|[^a-z])vk([^a-z]|$)|vulkan", part, re.I) for part in rel.split("/")[:-1])
            shipping = "shipping" in fn.lower()
            similar = difflib.SequenceMatcher(None, title, stem).ratio() if title and stem else 0.0
            key = (
                rel.count("/") - (1 if vulkan else 0),  # shallow first; a Vulkan build counts one level up
                shipping,                               # Unreal's Shipping exe only without a root launcher
                bool(WEAK_NAME.match(fn)),               # launcher.exe / start.exe lose to the real exe
                -round(similar, 1),                     # name close to the folder name
                -size,                                  # the game is usually the biggest exe
            )
            found.append((key, p))
    found.sort()
    return [p for _, p in found]


def best(root: str) -> Tuple[str, bool]:
    """(exe or "", ambiguous). Ambiguous = two different-named exes at the same depth, neither preferred by a rule."""
    c = candidates(root)
    if not c:
        return "", False
    if len(c) == 1:
        return c[0], False
    a, b = os.path.relpath(c[0], root), os.path.relpath(c[1], root)
    same_depth = a.count("/") == b.count("/")
    rule_decides = ("shipping" in b.lower()) != ("shipping" in a.lower()) or bool(WEAK_NAME.match(os.path.basename(b)))
    ambiguous = same_depth and not rule_decides and os.path.basename(a).lower() != os.path.basename(b).lower()
    return c[0], ambiguous
