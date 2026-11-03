# CLAUDE.md — project context

"Custom Games", a Decky Loader plugin for Steam Game Mode on Linux (tested on Ubuntu 26.04 + gamescope-session, Decky 3.3.1).
For non-Steam games it finds them and adds them to Steam without a restart, sets the official Steam artwork, keeps every
library image at the size Steam shows (smaller: GPU upscale; bigger: canvas downscale in the frontend), and fills the
game page tabs with the real game's Steam data. UI mock-ups: `mockups/`.

## Layout
- `main.py` — Decky backend (`Plugin` class); settings `settings.json`, links `games.json` (shortcut appid → Steam AppID and
  where it came from), image hashes `artwork.json`.
- `py_modules/customgames/` — no Decky dependencies, standard library only:
  - `steamenv.py` — Steam root, active user (loginusers.vdf), library folders, binary `shortcuts.vdf`, grid, Proton prefixes
  - `sources.py` — game folders and Anker Launcher's `library.json`; games under `steamapps/common` are skipped; "already in
    Steam" = a shortcut's exe inside the game folder; `game_root` steps over containers (AnkerGames/Games); Anker's real exe
    path is the adoption `anchor`, the launch profile path is often wrong
  - `exepick.py` — choosing the exe (root launcher > Shipping, the Vulkan build, never redist/crash reporters/crack folders)
  - `appid.py` — AppID from `steam_appid.txt` / `steam_emu.ini` / emulator configs, from emulator save folders in the prefix
    (`GSE Saves/<id>`, `RUNE/<id>`…); 480 (Spacewar) is ignored
  - `store.py` — store name search (exact match after normalisation only), appdetails, achievement schema
    (`IPlayerService/GetGameAchievements`, no key)
  - `artwork.py` — hash manifest, up/down queue (targets: portrait 1200×1800, wide 1840×860, hero 5760×1860, logo 1000–2400
    wide), official Steam art for new games. No SteamGridDB and no collection on purpose: SteamGridDB is used through its
    own plugin, and Steam already has a non-Steam filter
  - `upscaler.py` — upscayl-bin (Real-ESRGAN, ncnn/Vulkan): downloaded by the plugin on first start (`_install_deps`, status in
    `get_state().deps`, retry with "Install dependencies"), SHA-256 pinned; one call does x4 + exact size + JPEG
  - `achievements.py` — progress from `achievements.json` (GSE) and `achievements.ini` (RUNE/CODEX)
- `src/` — frontend (React, @decky/ui, @decky/api):
  - `i18n.ts` — `t(english, russian)`: Russian when the Steam client runs in Russian, else English
  - `library.ts` — "Update library" (scan → `AddShortcut` → artwork → matching) and the background resize queue every 90 s
    (not while a game runs); both buttons show a spinner and their result
  - `steam.ts` — `SteamClient.Apps.*`: adding a shortcut (after `AddShortcut` always `SetShortcutName/Exe/StartDir`, see the
    quirks below), `ClearCustomArtworkForApp` + `SetCustomArtworkForApp` (Steam writes the file into grid and shows it at
    once), logo position, `StoreItemCache`
  - `pagePatch.tsx` — replaces the contents of the native tabs (ids `WhatsNew`, `YourStuff`, `Community`, `GameInfo`). The
    route's `renderFunc` returns `<Provider value={pt}><AppPage overview details/></Provider>`; the plugin swaps `value` for a
    wrapper of `pt`, which wraps the component building the `tabs` array (props `fnOnCancelFromTabHeader` + `details`) and
    replaces the tabs' `children`. Wrappers are cached in a WeakMap (stable type → no remounts). **Do not patch deeper
    through `createReactTreePatcher`:** the page is a MobX observer class; after the first render `render` moves onto the
    instance and a prototype patch is lost.
  - `tabs.tsx`, `pageData.ts`, `modals.tsx`, `styles.tsx` (styles are rendered as a `<style>` inside the components: the game
    page lives in Big Picture's window, not in the plugin's document). Gamepad layouts must be `row`/`column`/`grid`
    (`"horizontal"` is silently ignored); items without an action need `focusable` to be reachable with the D-pad.
  - `achievementWatch.tsx` — achievement pop-ups: `RegisterForAppLifetimeNotifications`; while a game runs `poll_achievements`
    every 3 s (the first call is a baseline, then only new ones), one more poll 6 s after exit (some emulators write the file
    on close). Earned achievements are also shown in Activity as one card per day.
- If Steam has no official image of a kind (some older games have no hero or logo), the plugin does not invent one (no
  screenshots, no tiny icons — the user turned such substitutes down): the image is set with the SteamGridDB plugin and
  "Check artwork now" resizes it.

## Commands
```bash
pnpm install && pnpm run typecheck && pnpm run build
python3 tests/test_backend.py
./scripts/deploy.sh user@host   # no sudo: through Decky's installer and Steam's CEF debugger
```

## Verified on real hardware
- `SetCustomArtworkForApp(appid, b64, "jpg"|"png", type)` writes `<appid>{p,,_hero,_logo}.<format>` byte for byte; another
  format leaves the old file next to it → call `ClearCustomArtworkForApp` first (it removes every variant).
- Types: portrait 0, hero 1, logo 2, wide 3. Logo position: `appDetailsStore.SaveCustomLogoPosition(overview, {...})`.
- `AddShortcut` quotes the exe itself, mangles a quoted StartDir and names the shortcut after the exe.
- `StoreItemCache` and `partnerEventStore.LoadPartnerEventsPageable(undefined, appid, offset, n)` work for games not owned.
- Steam trailers are HLS; Chromium in Steam cannot play HLS natively but MSE with H.264 works → hls.js (light build).
- upscayl-bin on an RX 9060 XT: ~5 s per portrait/wide (including setting it in Steam). **Never pass `-s`**: with it
  upscayl-bin ignores `-r`/`-w` and saves the plain x4 result. Originals are kept in `settings/originals/` before replacing.
- CEF screenshots (`Page.captureScreenshot`) sometimes come back black although the display is on; check
  `document.body.innerText` of the Big Picture window then.

## Rules
- The plugin is generic (published): paths and links only through settings; no machine-specific data in the repository.
- Never run anything from game folders, only read them.
- Never kill the plugin process by hand (Decky 3.3.1 then spins at 100% CPU until `sudo systemctl restart plugin_loader`).
