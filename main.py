import asyncio
import base64
import json
import os
import shutil
import time
import traceback

import decky  # provided by Decky Loader

from customgames import achievements, appid as appid_mod, artwork, images, sources, steamenv, store
from customgames.upscaler import DEFAULT_MODEL, MODELS, Upscaler, UpscaleError

SETTINGS = "settings.json"
GAMES = "games.json"        # shortcut appid -> what we know about it (Steam AppID and where it came from)
ARTWORK = "artwork.json"    # hashes of every library image the plugin has seen
DEFAULT_SETTINGS = {
    "game_dirs": [],            # folders whose subfolders are games
    "anker": True,              # read Anker Launcher's library
    "scan_on_start": True,      # look for new games when Steam starts
    "art_new_games": True,      # pick artwork for games the plugin adds
    "upscale": True,            # upscale small library images
    "upscale_steam_games": True,  # ... also of Steam's own games (custom artwork only)
    "upscale_model": DEFAULT_MODEL,
    "compat_tool": "proton_experimental",
    "hidden": [],               # game folders the user removed from the plugin's view
    "data_lang": "",            # language of store texts and achievements; "" = Steam's own language
}
NAME_RETRY_SECONDS = 24 * 3600
# Steam client locale -> Steam Web API language name
STEAM_LANG = {"en": "english", "ru": "russian", "uk": "ukrainian", "de": "german", "fr": "french", "es": "spanish",
              "it": "italian", "pl": "polish", "pt": "portuguese", "pt-BR": "brazilian", "ja": "japanese",
              "ko": "koreana", "zh-CN": "schinese", "zh-TW": "tchinese", "tr": "turkish", "cs": "czech"}


def _err(e: Exception) -> dict:
    decky.logger.error("".join(traceback.format_exception(e)))
    return {"ok": False, "error": str(e)}


class Plugin:
    # ---------------- lifecycle ----------------
    async def _main(self):
        self.lock = asyncio.Lock()
        self.art_lock = asyncio.Lock()
        os.makedirs(decky.DECKY_PLUGIN_SETTINGS_DIR, exist_ok=True)
        self.workdir = os.path.join(decky.DECKY_PLUGIN_RUNTIME_DIR, "work")
        os.makedirs(self.workdir, exist_ok=True)
        self._clean_workdir()
        self.upscaler = Upscaler(decky.DECKY_PLUGIN_RUNTIME_DIR)
        self.manifest = artwork.Manifest(self._path(ARTWORK))
        self._first_run_defaults()
        # Dependencies (the GPU upscaler and its models) come with the plugin: fetched in the background on the
        # first start, so nobody has to install anything by hand. The panel shows progress and offers a retry.
        self.deps = {"status": "ready" if self.upscaler.installed() else "missing", "error": ""}
        self._deps_task = None
        if self.deps["status"] == "missing":
            self._deps_task = asyncio.get_running_loop().create_task(self._install_deps())
        decky.logger.info("Custom Games backend started")

    async def _unload(self):
        if self._deps_task:
            self._deps_task.cancel()

    async def _install_deps(self) -> None:
        self.deps = {"status": "installing", "error": ""}
        try:
            await asyncio.to_thread(self.upscaler.install)
            self.deps = {"status": "ready" if self.upscaler.installed() else "error", "error": ""}
            decky.logger.info("dependencies installed")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - shown in the panel with a retry button
            decky.logger.error(f"dependency install failed: {e}")
            self.deps = {"status": "error", "error": str(e)}

    async def _uninstall(self):
        pass

    # ---------------- helpers ----------------
    def _path(self, name: str) -> str:
        return os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, name)

    def _read(self, name: str, default):
        try:
            with open(self._path(name), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    def _write(self, name: str, data) -> None:
        tmp = self._path(name) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self._path(name))

    def _settings(self) -> dict:
        s = dict(DEFAULT_SETTINGS)
        s.update({k: v for k, v in self._read(SETTINGS, {}).items() if k in DEFAULT_SETTINGS})
        return s

    def _games(self) -> dict:
        return self._read(GAMES, {})

    def _first_run_defaults(self) -> None:
        if os.path.exists(self._path(SETTINGS)):
            return
        s = dict(DEFAULT_SETTINGS)
        home = decky.DECKY_USER_HOME
        # Anker Launcher knows where the user keeps games; ~/Games is the common default elsewhere.
        try:
            with open(os.path.join(home, ".config/net.ankergames.launcher/preferences.json"), encoding="utf-8") as f:
                root = json.load(f).get("library_root")
            if root and os.path.isdir(root):
                s["game_dirs"].append(root)
        except (OSError, ValueError):
            pass
        for d in ("Games", "games"):
            p = os.path.join(home, d)
            if os.path.isdir(p) and p not in s["game_dirs"]:
                s["game_dirs"].append(p)
        self._write(SETTINGS, s)

    def _clean_workdir(self) -> None:
        now = time.time()
        for fn in os.listdir(self.workdir):
            p = os.path.join(self.workdir, fn)
            try:
                if now - os.path.getmtime(p) > 6 * 3600:
                    shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
            except OSError:
                pass

    def _steam(self):
        root = steamenv.steam_root(decky.DECKY_USER_HOME)
        if not root:
            raise RuntimeError("Steam not found")
        user = steamenv.active_user(root)
        if not user:
            raise RuntimeError("No Steam user found")
        libs = steamenv.library_folders(root)
        return root, user, libs

    def _game_root(self, exe: str, settings: dict) -> str:
        return sources.game_root(exe, settings["game_dirs"],
                                 sources.anker_roots(decky.DECKY_USER_HOME) if settings["anker"] else [])

    # ---------------- state ----------------
    async def get_state(self) -> dict:
        try:
            s = self._settings()
            return {"ok": True, "settings": s, "games": self._games(), "upscaler": self.upscaler.installed(),
                    "models": list(MODELS), "deps": self.deps}
        except Exception as e:  # noqa: BLE001
            return _err(e)

    async def set_setting(self, key: str, value) -> dict:
        try:
            if key not in DEFAULT_SETTINGS:
                return {"ok": False, "error": f"unknown setting {key}"}
            s = self._read(SETTINGS, {})
            if key == "game_dirs":
                value = [os.path.realpath(os.path.expanduser(v)) for v in value if str(v).strip()]
            s[key] = value
            self._write(SETTINGS, s)
            return await self.get_state()
        except Exception as e:  # noqa: BLE001
            return _err(e)

    # ---------------- library ----------------
    async def scan_library(self) -> dict:
        """New games on disk that Steam does not have yet, each with its Steam AppID when found."""
        async with self.lock:
            try:
                return await asyncio.to_thread(self._scan_library)
            except Exception as e:  # noqa: BLE001
                return _err(e)

    def _scan_library(self) -> dict:
        s = self._settings()
        root, user, libs = self._steam()
        shortcuts = steamenv.read_shortcuts(root, user)
        found = sources.find_new(decky.DECKY_USER_HOME, s["game_dirs"], s["anker"],
                                 steamenv.installed_steam_dirs(libs), shortcuts, s["hidden"])
        for c in found["new"]:
            hit = (c["steam_appid"], "anker") if c.get("steam_appid") else appid_mod.from_files(c["root"], c["exe"])
            if not hit:
                try:
                    m = store.match(c["title"])
                    hit = (m[0], "name:" + m[1]) if m else None
                except Exception as e:  # noqa: BLE001 - offline: add without info, resolved later
                    decky.logger.warning(f"store search failed for {c['title']}: {e}")
            c["steam_appid"], c["appid_source"] = (hit[0], hit[1]) if hit else (0, "")
        decky.logger.info(f"scan: {len(found['new'])} new, {len(found['busy'])} busy, {len(found['no_exe'])} without exe")
        return {"ok": True, **found, "compat_tool": s["compat_tool"]}

    async def register_added(self, shortcut_appid: int, cand: dict) -> dict:
        """The frontend added a shortcut for a scanned game: remember where it came from."""
        try:
            g = self._games()
            g[str(shortcut_appid)] = {
                "steam_appid": int(cand.get("steam_appid") or 0), "appid_source": cand.get("appid_source", ""),
                "title": cand.get("title", ""), "root": cand.get("root", ""), "exe": cand.get("exe", ""),
                "source": cand.get("source", ""), "added_by_plugin": True, "added_at": int(time.time()),
                "checked_at": int(time.time()),
            }
            self._write(GAMES, g)
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return _err(e)

    async def resolve_games(self, force: bool = False) -> dict:
        """Finds the Steam AppID of every non-Steam shortcut (also ones added by hand before the plugin)."""
        async with self.lock:
            try:
                return await asyncio.to_thread(self._resolve_games, force)
            except Exception as e:  # noqa: BLE001
                return _err(e)

    def _resolve_games(self, force: bool) -> dict:
        s = self._settings()
        root, user, libs = self._steam()
        games = self._games()
        anker = sources.anker_appids(decky.DECKY_USER_HOME) if s["anker"] else {}
        now = int(time.time())
        changed = 0
        for sc in steamenv.read_shortcuts(root, user):
            key = str(sc["appid"])
            g = games.get(key) or {}
            if g.get("appid_source") == "manual":
                continue
            exe = sc["exe"]
            is_game = exe.lower().endswith(".exe") or any(
                os.path.realpath(exe).startswith(os.path.realpath(d) + "/") for d in s["game_dirs"])
            if not is_game:
                if not g:
                    games[key] = {"steam_appid": 0, "appid_source": "not_a_game", "title": sc["name"], "exe": exe,
                                  "checked_at": now}
                    changed += 1
                continue
            # Anker's catalogue id wins and also corrects an earlier wrong one taken from the repack's files.
            real_exe = os.path.realpath(exe)
            hit = next(((n, "anker") for r, n in anker.items() if real_exe.startswith(r + "/")), None)
            if hit and (g.get("steam_appid"), g.get("appid_source")) == hit and not force:
                continue
            if not hit and g.get("steam_appid") and not force \
                    and g.get("appid_source", "").startswith(("file:", "prefix:", "anker")):
                continue
            groot = g.get("root") or self._game_root(exe, s)
            if not hit:
                hit = appid_mod.from_files(groot, exe) if os.path.isdir(groot) else None
                hit = hit or appid_mod.from_prefix(steamenv.prefix_dirs(libs, sc["appid"]))
            if not hit and g.get("steam_appid") and g.get("appid_source", "").startswith("name:"):
                continue  # keep the earlier name match
            if not hit and (force or now - int(g.get("checked_at") or 0) > NAME_RETRY_SECONDS):
                try:
                    m = store.match(sc["name"]) or store.match(store.title_from_folder(os.path.basename(groot)))
                    hit = (m[0], "name:" + m[1]) if m else None
                except Exception as e:  # noqa: BLE001
                    decky.logger.warning(f"store search failed for {sc['name']}: {e}")
            new = {**g, "title": sc["name"], "root": groot, "exe": exe, "checked_at": now}
            if hit:
                new["steam_appid"], new["appid_source"] = hit
            else:
                new.setdefault("steam_appid", 0)
                new.setdefault("appid_source", "")
            if new != g:
                games[key] = new
                changed += 1
        if changed:
            self._write(GAMES, games)
        return {"ok": True, "games": games, "changed": changed}

    async def set_mapping(self, shortcut_appid: int, steam_appid: int) -> dict:
        try:
            g = self._games()
            rec = g.get(str(shortcut_appid), {})
            rec.update(steam_appid=int(steam_appid), appid_source="manual" if steam_appid else "", checked_at=int(time.time()))
            g[str(shortcut_appid)] = rec
            self._write(GAMES, g)
            return {"ok": True, "games": g}
        except Exception as e:  # noqa: BLE001
            return _err(e)

    async def search_store(self, term: str) -> dict:
        try:
            return {"ok": True, "items": await asyncio.to_thread(store.search, term)}
        except Exception as e:  # noqa: BLE001
            return _err(e)

    async def hide_game(self, root: str, hidden: bool) -> dict:
        try:
            s = self._read(SETTINGS, {})
            lst = [h for h in s.get("hidden", []) if h != root]
            if hidden:
                lst.append(root)
            s["hidden"] = lst
            self._write(SETTINGS, s)
            return await self.get_state()
        except Exception as e:  # noqa: BLE001
            return _err(e)

    # ---------------- artwork ----------------
    async def install_deps(self) -> dict:
        """Retry from the panel; waits for an install that is already running."""
        try:
            if self._deps_task and not self._deps_task.done():
                await self._deps_task
            elif not self.upscaler.installed():
                self._deps_task = asyncio.get_running_loop().create_task(self._install_deps())
                await self._deps_task
            else:
                self.deps = {"status": "ready", "error": ""}
            return {"ok": self.deps["status"] == "ready", "deps": self.deps, "error": self.deps["error"]}
        except Exception as e:  # noqa: BLE001
            return _err(e)

    async def art_for_new(self, appid: int, steam_appid: int, title: str, steam_assets: dict) -> dict:
        """Artwork for a game the plugin just added: picked, upscaled where small, ready to hand to Steam."""
        async with self.art_lock:
            try:
                return await asyncio.to_thread(self._art_for_new, appid, steam_appid, title, steam_assets or {})
            except Exception as e:  # noqa: BLE001
                return _err(e)

    def _art_for_new(self, appid: int, steam_appid: int, title: str, steam_assets: dict) -> dict:
        s = self._settings()
        root, user, _ = self._steam()
        grid = steamenv.grid_dir(root, user)
        work = os.path.join(self.workdir, str(appid))
        os.makedirs(work, exist_ok=True)
        if not steam_appid:
            return {"ok": True, "assets": [], "icon": None, "logo_pos": None}
        picked = artwork.Picker(work).pick(steam_appid, ["portrait", "wide", "hero", "logo", "icon"], steam_assets)
        out = []
        for kind, path in picked["files"].items():
            if kind == "icon":
                continue
            meta = images.info(path)
            if not meta:
                continue
            w, h, fmt = meta
            if s["upscale"] and self.upscaler.installed() and artwork.needs_upscale(kind, w, h):
                try:
                    path = self._upscale_file(path, kind, w, h, s, os.path.join(work, f"{kind}_up"))
                    fmt = "png" if kind == "logo" else "jpg"
                except UpscaleError as e:
                    decky.logger.warning(f"upscale {kind} of {title} failed, using the original: {e}")
            out.append({"kind": kind, "path": path, "format": "jpg" if fmt == "jpg" else "png",
                        "type": artwork.ASSET_TYPE[kind], "source": picked["source"][kind]})
        icon = None
        if "icon" in picked["files"] and artwork.is_shortcut(appid):
            icon = artwork.install_icon(picked["files"]["icon"], grid, appid)
        return {"ok": True, "assets": out, "icon": icon, "logo_pos": picked["logo_pos"]}

    def _upscale_file(self, src: str, kind: str, w: int, h: int, s: dict, dest_noext: str) -> str:
        width, height = artwork.upscale_size(kind, w, h)
        fmt = "png" if kind == "logo" else "jpg"
        model = s["upscale_model"] if s["upscale_model"] in MODELS else DEFAULT_MODEL
        return self.upscaler.run(src, f"{dest_noext}.{fmt}", width, height, fmt=fmt, model=model)

    async def art_scan(self, only: list = None) -> dict:
        """Library images that are not at their size: the upscale / downscale queue."""
        async with self.art_lock:
            try:
                return await asyncio.to_thread(self._art_scan, only)
            except Exception as e:  # noqa: BLE001
                return _err(e)

    def _art_scan(self, only) -> dict:
        s = self._settings()
        root, user, _ = self._steam()
        jobs = artwork.scan_changes(steamenv.grid_dir(root, user), self.manifest, s["upscale_steam_games"],
                                    set(only) if only else None)
        self.manifest.save()
        return {"ok": True, "jobs": jobs, "enabled": bool(s["upscale"]), "installed": self.upscaler.installed()}

    async def art_process(self, job: dict) -> dict:
        """One queue job: "up" runs the GPU upscaler; "down" hands the picture to the frontend, which scales it
        down on a canvas (no image library in Decky's Python, and no AI needed to make a picture smaller)."""
        async with self.art_lock:
            try:
                return await asyncio.to_thread(self._art_process, job)
            except Exception as e:  # noqa: BLE001
                artwork.mark_failed(self.manifest, int(job["appid"]), job["kind"], str(e))
                self.manifest.save()
                return _err(e)

    def _art_process(self, job: dict) -> dict:
        s = self._settings()
        kind, appid = job["kind"], int(job["appid"])
        src = job["path"]
        if not os.path.isfile(src) or images.sha256(src) != job["sha"]:
            return {"ok": False, "error": "changed again meanwhile", "stale": True}
        # Keep the picture we are about to replace, so it can be put back by hand.
        backup = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "originals",
                              f"{appid}_{kind}_{job['sha'][:12]}{os.path.splitext(src)[1]}")
        if not os.path.exists(backup):
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            shutil.copyfile(src, backup)
        fmt = "png" if kind == "logo" else "jpg"
        dest = os.path.join(self.workdir, f"{appid}_{kind}_{int(time.time())}")
        if job.get("action") == "down":
            copy = dest + os.path.splitext(src)[1]
            shutil.copyfile(src, copy)
            return {"ok": True, "path": copy, "format": fmt, "type": artwork.ASSET_TYPE[kind], "resize": True,
                    "mime": "image/" + ("jpeg" if job.get("fmt") == "jpg" else job.get("fmt") or "png"),
                    "width": int(job["width"]), "height": int(job["height"])}
        out = self._upscale_file(src, kind, int(job["w"]), int(job["h"]), s, dest)
        return {"ok": True, "path": out, "format": fmt, "type": artwork.ASSET_TYPE[kind], "resize": False}

    async def art_applied(self, appid: int, kind: str, source: str, src_sha: str = "") -> dict:
        async with self.art_lock:
            try:
                root, user, _ = self._steam()
                rec = artwork.record_applied(steamenv.grid_dir(root, user), self.manifest, int(appid), kind, source, src_sha)
                self.manifest.save()
                return {"ok": bool(rec), "record": rec}
            except Exception as e:  # noqa: BLE001
                return _err(e)

    async def art_failed(self, appid: int, kind: str, error: str) -> dict:
        async with self.art_lock:
            artwork.mark_failed(self.manifest, int(appid), kind, error)
            self.manifest.save()
            return {"ok": True}

    async def read_b64(self, path: str) -> dict:
        """Base64 of a file the plugin produced (only from its own work folder)."""
        try:
            real = os.path.realpath(path)
            if not real.startswith(os.path.realpath(self.workdir) + "/"):
                return {"ok": False, "error": "outside the work folder"}
            with open(real, "rb") as f:
                return {"ok": True, "data": base64.b64encode(f.read()).decode()}
        except Exception as e:  # noqa: BLE001
            return _err(e)

    # ---------------- game page ----------------
    def _cached(self, name: str, max_age: int, fetch):
        """Store data cached on disk for a while: pages open fast and the store is not asked every time."""
        path = os.path.join(decky.DECKY_PLUGIN_RUNTIME_DIR, "cache", name + ".json")
        try:
            if time.time() - os.path.getmtime(path) < max_age:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
        except (OSError, ValueError):
            pass
        data = fetch()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(path + ".tmp", path)
        return data

    async def store_details(self, steam_appid: int, lang: str) -> dict:
        try:
            lang = STEAM_LANG.get(lang, lang if lang in STEAM_LANG.values() else "english")
            data = await asyncio.to_thread(self._cached, f"details_{int(steam_appid)}_{lang}", 24 * 3600,
                                           lambda: store.app_details(int(steam_appid), lang))
            return {"ok": True, "details": data}
        except Exception as e:  # noqa: BLE001
            return _err(e)

    async def achievement_schema(self, steam_appid: int, lang: str) -> dict:
        try:
            lang = STEAM_LANG.get(lang, lang if lang in STEAM_LANG.values() else "english")
            data = await asyncio.to_thread(self._cached, f"achievements_{int(steam_appid)}_{lang}", 7 * 24 * 3600,
                                           lambda: store.achievement_schema(int(steam_appid), lang))
            return {"ok": True, "achievements": data}
        except Exception as e:  # noqa: BLE001
            return _err(e)

    async def poll_achievements(self, shortcut_appid: int, steam_appid: int) -> dict:
        """Achievements earned since the previous poll of this game (the first poll only takes a baseline).
        Cheap while nothing changes: the files are parsed only when their size or time changes."""
        try:
            _, _, libs = self._steam()
            files = appid_mod.achievement_files(steamenv.prefix_dirs(libs, int(shortcut_appid)), int(steam_appid))
            sig = tuple(sorted((f, os.path.getsize(f), os.path.getmtime(f)) for f in files if os.path.exists(f)))
            polls = self.__dict__.setdefault("_ach_polls", {})
            prev = polls.get(int(shortcut_appid))
            if prev and prev["sig"] == sig:
                return {"ok": True, "new": []}
            earned = {k: v for k, v in achievements.read(files).items() if v["earned"]}
            polls[int(shortcut_appid)] = {"sig": sig, "earned": set(earned)}
            if prev is None:
                return {"ok": True, "new": [], "baseline": len(earned)}
            new = [{"name": k, **earned[k]} for k in earned if k not in prev["earned"]]
            return {"ok": True, "new": sorted(new, key=lambda a: a["time"])}
        except Exception as e:  # noqa: BLE001
            return _err(e)

    async def stop_achievements(self, shortcut_appid: int) -> dict:
        self.__dict__.setdefault("_ach_polls", {}).pop(int(shortcut_appid), None)
        return {"ok": True}

    async def get_achievements(self, shortcut_appid: int, steam_appid: int) -> dict:
        try:
            _, _, libs = self._steam()
            files = appid_mod.achievement_files(steamenv.prefix_dirs(libs, int(shortcut_appid)), int(steam_appid))
            return {"ok": True, "files": len(files), "progress": achievements.read(files)}
        except Exception as e:  # noqa: BLE001
            return _err(e)
