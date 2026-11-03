"""Steam store lookups that need no key: name search, used when the game's files carry no AppID."""

import difflib
import re
import unicodedata
from typing import List, Optional, Tuple

from . import net

ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}
EDITION = re.compile(r"\b(remastered|remaster|definitive|complete|goty|game of the year|deluxe|ultimate|directors cut|"
                     r"enhanced|anniversary|edition|digital|standard|gold|premium)\b")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ").replace("™", "").replace("®", "")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(ROMAN.get(w, w) for w in s.split())


def loose(s: str) -> str:
    """Without edition words and a release year: 'God of War (2018)' ~ 'God of War'."""
    s = re.sub(r"\b(19|20)\d\d\b", " ", EDITION.sub(" ", norm(s)))
    return " ".join(s.split())


def title_from_folder(name: str) -> str:
    """'Black-Myth-Wukong-AnkerGames' -> 'Black Myth Wukong', 'The Last of Us Part I-361' -> 'The Last of Us Part I'."""
    s = re.sub(r"[-_.]+", " ", name)
    s = re.sub(r"\b(ankergames|steamrip|fitgirl|dodi|elamigos|repack|portable|codex|rune|empress|tenoke|gog|"
               r"v?\d+(\.\d+)+\w*|build \d+)\b", " ", s, flags=re.I)
    s = re.sub(r"\s\d{2,5}$", "", s.strip())  # Anker's "-<game id>" suffix
    return " ".join(s.split())


def search(term: str, cc: str = "us", lang: str = "english") -> List[dict]:
    data = net.get_json("https://store.steampowered.com/api/storesearch/", {"term": term, "cc": cc, "l": lang})
    return [{"id": int(i["id"]), "name": i["name"], "type": i.get("type", "app"),
             "image": i.get("tiny_image", "")} for i in data.get("items", []) if i.get("id")]


def match(title: str) -> Optional[Tuple[int, str, float]]:
    """(appid, store name, score) when the store search has a confident match, else None."""
    items = search(title)
    if not items:
        loosened = loose(title)
        if loosened and loosened != norm(title):
            items = search(loosened)
    best: Optional[Tuple[int, str, float]] = None
    for it in items:
        if it["type"] not in ("app", "game"):
            continue
        a, b = norm(title), norm(it["name"])
        score = 1.0 if a == b else 0.97 if loose(title) == loose(it["name"]) else \
            difflib.SequenceMatcher(None, a, b).ratio()
        if best is None or score > best[2]:
            best = (it["id"], it["name"], score)
    return best if best and best[2] >= 0.9 else None


def app_details(appid: int, lang: str = "english", cc: str = "us") -> dict:
    """Store page data: genres, categories (features), metacritic, languages, developers, website."""
    data = net.get_json("https://store.steampowered.com/api/appdetails",
                        {"appids": appid, "l": lang, "cc": cc})
    entry = data.get(str(appid)) or {}
    if not entry.get("success"):
        return {}
    d = entry.get("data") or {}
    keep = ("name", "steam_appid", "short_description", "detailed_description", "about_the_game", "developers",
            "publishers", "genres", "categories", "metacritic", "supported_languages", "website", "release_date",
            "pc_requirements", "achievements", "recommendations", "header_image", "controller_support")
    return {k: d[k] for k in keep if k in d}


def achievement_schema(appid: int, lang: str = "english") -> list:
    """All achievements with names, descriptions, icons and the share of players who have them (no key needed)."""
    data = net.get_json("https://api.steampowered.com/IPlayerService/GetGameAchievements/v1/",
                        {"appid": appid, "language": lang})
    out = []
    for a in (data.get("response") or {}).get("achievements") or []:
        try:
            pct = float(a.get("player_percent_unlocked") or 0)
        except ValueError:
            pct = 0.0
        out.append({"name": a.get("internal_name", ""), "title": a.get("localized_name", ""),
                    "desc": a.get("localized_desc", ""), "icon": a.get("icon", ""), "icon_gray": a.get("icon_gray", ""),
                    "hidden": bool(a.get("hidden")), "pct": pct})
    return out
