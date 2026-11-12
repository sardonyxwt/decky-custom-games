"""Backend tests on a fake disk layout shaped like real repacks (no network, no Decky)."""

import json
import os
import struct
import sys
import tempfile
import time
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "py_modules"))

from customgames import achievements, appid, artwork, exepick, images, sources, steamenv, store  # noqa: E402


def touch(path: str, size: int = 70 * 1024, data: bytes = None) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data if data is not None else b"MZ" + b"\0" * (size - 2))
    return path


def png(w: int, h: int) -> bytes:
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))


def jpg(w: int, h: int) -> bytes:
    return b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\0" + b"\0" * 9 + \
        b"\xff\xc0" + struct.pack(">HBHH", 17, 8, h, w) + b"\x03" + b"\0" * 9 + b"\xff\xd9"


def shortcuts_vdf(entries) -> bytes:
    def s(k, v):
        return b"\x01" + k.encode() + b"\0" + v.encode() + b"\0"

    def i(k, v):
        return b"\x02" + k.encode() + b"\0" + struct.pack("<I", v)

    body = b""
    for n, e in enumerate(entries):
        body += b"\x00" + str(n).encode() + b"\0" + i("appid", e["appid"]) + s("AppName", e["name"]) + \
            s("Exe", f'"{e["exe"]}"') + s("StartDir", f'"{os.path.dirname(e["exe"])}"') + s("icon", "") + \
            s("LaunchOptions", "") + i("IsHidden", 0) + b"\x00tags\0\x08\x08"
    return b"\x00shortcuts\0" + body + b"\x08\x08"


class Layout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home = os.path.join(self.tmp, "home")
        self.games = os.path.join(self.tmp, "Games")
        g = self.games
        # Hades: three builds + a CODEX crack backup with its own steam_emu.ini
        for b in ("x64", "x64Vk", "x86"):
            touch(f"{g}/Hades/Hades/{b}/Hades.exe")
        touch(f"{g}/Hades/Crack/CODEX/x64/steam_emu.ini", data=b"[Settings]\nAppId=1145360\n")
        touch(f"{g}/Hades/Hades/x64Vk/steam_emu.ini", data=b"[Settings]\r\nAppId = 1145360\r\n")
        # Black Myth: root launcher + Unreal shipping exe + redist
        touch(f"{g}/Black Myth Wukong/b1.exe")
        touch(f"{g}/Black Myth Wukong/b1/Binaries/Win64/b1-Win64-Shipping.exe", 200 * 1024)
        touch(f"{g}/Black Myth Wukong/_CommonRedist/vc_redist.x64.exe")
        # Split Fiction: only the shipping exe; Goldberg's steam_appid.txt
        touch(f"{g}/Split Fiction/Split/Binaries/Win64/SplitFiction.exe")
        touch(f"{g}/Split Fiction/Split/Binaries/Win64/steam_appid.txt", data=b"2001120\n")
        # Cairn: no AppID in the files
        touch(f"{g}/Cairn/Cairn.exe")
        touch(f"{g}/Cairn/UnityCrashHandler64.exe")
        # Still unpacking
        touch(f"{g}/Fresh Game/Fresh.exe")
        touch(f"{g}/Fresh Game/data.bin.part", 10)
        os.makedirs(f"{g}/Saves/x")
        # Steam library with a real Steam game; Anker library pointing at it and at its own game
        self.steam = os.path.join(self.home, ".steam/steam")
        os.makedirs(f"{self.steam}/steamapps/common/Hollow Knight")
        touch(f"{self.steam}/steamapps/common/Hollow Knight/hollow_knight.exe")
        os.makedirs(f"{self.steam}/userdata/42/config/grid")
        touch(f"{g}/AnkerGames/Games/over the hill-3953/over the hill.exe")
        anker = os.path.join(self.home, ".config/net.ankergames.launcher")
        os.makedirs(anker)
        with open(f"{anker}/library.json", "w") as f:
            json.dump({"games": {
                "244": {"title": "Hollow Knight", "root": f"{self.steam}/steamapps/common/Hollow Knight",
                        "launch_profiles": [{"executable": "hollow_knight.exe"}]},
                "3953": {"title": "over the hill", "root": f"{g}/AnkerGames/Games/over the hill-3953",
                         "launch_profiles": [{"executable": "over the hill.exe", "arguments": "-dx11"}],
                         "source": {"source": {"steam_app_id": "2397840"}}},
                "323": {"title": "Hades", "root": f"{g}/Hades/Hades/x64",
                        "launch_profiles": [{"executable": "x86/Hades.exe"}], "adoption": {"anchor": "Hades.exe"},
                        "source": {"source": {"steam_app_id": "480"}}},
            }, "removed": {}}, f)
        old = time.time() - 3600
        for dirpath, dirnames, filenames in os.walk(g):
            os.utime(dirpath, (old, old))

    def test_exe_rules(self):
        self.assertTrue(exepick.best(f"{self.games}/Hades")[0].endswith("x64Vk/Hades.exe"))
        self.assertTrue(exepick.best(f"{self.games}/Black Myth Wukong")[0].endswith("Wukong/b1.exe"))
        self.assertTrue(exepick.best(f"{self.games}/Split Fiction")[0].endswith("SplitFiction.exe"))
        self.assertTrue(exepick.best(f"{self.games}/Cairn")[0].endswith("Cairn/Cairn.exe"))

    def test_appid_from_files(self):
        hades = f"{self.games}/Hades"
        hit = appid.from_files(hades, f"{hades}/Hades/x64Vk/Hades.exe")
        self.assertEqual(hit[0], 1145360)
        self.assertIn("x64Vk", hit[1])  # the config next to the exe, not the crack backup
        self.assertEqual(appid.from_files(f"{self.games}/Split Fiction")[0], 2001120)
        self.assertIsNone(appid.from_files(f"{self.games}/Cairn"))

    def test_prefix_and_achievements(self):
        pfx = os.path.join(self.tmp, "compatdata/3017837512/pfx")
        touch(f"{pfx}/drive_c/users/Public/Documents/Steam/RUNE/1588550/achievements.ini",
              data=b"[First]\nAchieved=1\nCurProgress=0\nMaxProgress=0\nUnlockTime=1792954717\n\n"
                   b"[Second]\nAchieved=0\nCurProgress=3\nMaxProgress=10\nUnlockTime=0\n")
        touch(f"{pfx}/drive_c/users/steamuser/AppData/Roaming/GSE Saves/settings/configs.user.ini", data=b"x")
        self.assertEqual(appid.from_prefix([pfx]), (1588550, "prefix:RUNE"))
        files = appid.achievement_files([pfx], 1588550)
        got = achievements.read(files)
        self.assertTrue(got["First"]["earned"])
        self.assertEqual(got["First"]["time"], 1792954717)
        self.assertEqual((got["Second"]["cur"], got["Second"]["max"]), (3, 10))
        # RUNE in Death Stranding 2 starts the file with a nameless section; the rest must still be read
        ds2 = f"{pfx}/drive_c/users/Public/Documents/Steam/RUNE/3280350/achievements.ini"
        touch(ds2, data=b"[]\r\nAchieved=1\r\nUnlockTime=1\r\n\r\n[SteamAchievements]\r\n00000=trophy_024\r\nCount=1\r\n\r\n"
                        b"[trophy_024]\r\nAchieved=1\r\nCurProgress=22\r\nMaxProgress=42\r\nUnlockTime=1794183344\r\n")
        self.assertEqual(achievements.read([ds2]), {"trophy_024": {"earned": True, "time": 1794183344, "cur": 22, "max": 42}})
        gse = f"{pfx}/drive_c/users/steamuser/AppData/Roaming/GSE Saves/2445690/achievements.json"
        touch(gse, data=json.dumps({"A": {"earned": True, "earned_time": 5}, "B": {"earned": False, "earned_time": 0}}).encode())
        self.assertEqual(achievements.read([gse])["A"]["time"], 5)

    def test_find_new(self):
        sc = [{"appid": 3006057877, "name": "Hades", "exe": f"{self.games}/Hades/Hades/x64/Hades.exe", "start_dir": ""}]
        res = sources.find_new(self.home, [self.games], True, [f"{self.steam}/steamapps/common"], sc)
        titles = sorted(c["title"] for c in res["new"])
        self.assertEqual(titles, ["Black Myth Wukong", "Cairn", "Split Fiction", "over the hill"])
        anker = next(c for c in res["new"] if c["source"] == "anker")
        self.assertEqual(anker["launch_options"], "-dx11")
        found = {c["title"]: c["exe"] for c in sources.anker_games(self.home, [])}
        self.assertTrue(found["Hades"].endswith("Hades/x64/Hades.exe"))  # the anchor, not the broken profile path
        self.assertTrue(found["over the hill"].endswith("over the hill-3953/over the hill.exe"))
        self.assertEqual([c["title"] for c in res["busy"]], ["Fresh Game"])
        # The catalogue's Steam AppID comes along; Spacewar (480) is not a game id
        self.assertEqual(anker["steam_appid"], 2397840)
        ids = sources.anker_appids(self.home)
        self.assertEqual(ids, {os.path.realpath(f"{self.games}/AnkerGames/Games/over the hill-3953"): 2397840})

    def test_shortcuts_vdf(self):
        path = f"{self.steam}/userdata/42/config/shortcuts.vdf"
        with open(path, "wb") as f:
            f.write(shortcuts_vdf([{"appid": 3006057877, "name": "Hades II", "exe": "/g/Hades II/Hades2.exe"}]))
        got = steamenv.read_shortcuts(self.steam, "42")
        self.assertEqual(got[0]["appid"], 3006057877)
        self.assertEqual(got[0]["exe"], "/g/Hades II/Hades2.exe")

    def test_artwork_change_detection(self):
        grid = f"{self.steam}/userdata/42/config/grid"
        m = artwork.Manifest(os.path.join(self.tmp, "artwork.json"))
        touch(f"{grid}/3006057877p.png", data=png(600, 900))       # small: upscale
        touch(f"{grid}/3006057877_hero.jpg", data=jpg(5760, 1860))  # big enough
        touch(f"{grid}/367520p.png", data=png(600, 900))            # a Steam game
        touch(f"{grid}/3006057877.json", data=b"{}")
        jobs = artwork.scan_changes(grid, m, include_steam_games=False)
        self.assertEqual([(j["appid"], j["kind"]) for j in jobs], [(3006057877, "portrait")])
        self.assertEqual(m.get(3006057877, "hero")["status"], "ok")
        # a pending job stays queued until it is done (e.g. the upscaler was missing); finished ones are not reported
        self.assertEqual(len(artwork.scan_changes(grid, m, include_steam_games=False)), 1)
        artwork.mark_failed(m, 3006057877, "portrait", "boom")
        self.assertEqual(artwork.scan_changes(grid, m, include_steam_games=False), [])
        # our upscaled result is recorded as ours, then a new small image from someone else is a new job
        touch(f"{grid}/3006057877p.png", data=jpg(1200, 1800))
        artwork.record_applied(grid, m, 3006057877, "portrait", "upscale")
        self.assertEqual(artwork.scan_changes(grid, m, include_steam_games=False), [])
        time.sleep(1.1)
        touch(f"{grid}/3006057877p.png", data=png(600, 900) + b"other")
        self.assertEqual(len(artwork.scan_changes(grid, m, include_steam_games=True)), 2)  # + the Steam game
        # oversized pictures are scaled down, also ones the plugin itself made earlier
        touch(f"{grid}/48000.jpg", data=jpg(3680, 1720))
        touch(f"{grid}/48000_logo.png", data=png(5829, 975))
        jobs = {(j["appid"], j["kind"]): j for j in artwork.scan_changes(grid, m, include_steam_games=True)}
        self.assertEqual((jobs[(48000, "wide")]["action"], jobs[(48000, "wide")]["width"], jobs[(48000, "wide")]["height"]),
                         ("down", 1840, 860))
        self.assertEqual((jobs[(48000, "logo")]["width"], jobs[(48000, "logo")]["height"]), (2400, 401))
        touch(f"{grid}/48000.jpg", data=jpg(1840, 860))
        artwork.record_applied(grid, m, 48000, "wide", "downscale")
        self.assertNotIn((48000, "wide"), {(j["appid"], j["kind"]) for j in artwork.scan_changes(grid, m, True)})

    def test_images(self):
        self.assertEqual(images.info_bytes(png(10, 20)), (10, 20, "png"))
        self.assertEqual(images.info_bytes(jpg(30, 40)), (30, 40, "jpg"))

    def test_sizes(self):
        self.assertEqual(artwork.upscale_size("portrait", 600, 900), (1200, 1800))
        self.assertEqual(artwork.upscale_size("portrait", 660, 930), (1200, None))
        self.assertEqual(artwork.upscale_size("hero", 3840, 1240), (5760, 1860))
        self.assertEqual(artwork.upscale_size("logo", 800, 300), (1600, None))
        self.assertFalse(artwork.needs_upscale("logo", 1200, 400))
        self.assertEqual(artwork.action_for("portrait", 2400, 3600, "jpg"), "down")
        self.assertEqual(artwork.fit_size("portrait", 660, 930, "up"), (1200, 1691))
        self.assertIsNone(artwork.action_for("portrait", 1200, 1690, "jpg"))
        self.assertIsNone(artwork.action_for("hero", 5760, 1860, "jpg"))

    def test_titles(self):
        self.assertEqual(store.title_from_folder("Black-Myth-Wukong-AnkerGames"), "Black Myth Wukong")
        self.assertEqual(store.title_from_folder("The Last of Us Part I-361"), "The Last of Us Part I")
        self.assertEqual(store.norm("Hades II"), store.norm("Hades 2"))
        self.assertEqual(store.loose("God of War (2018)"), store.loose("God of War"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
