// "Update library": find new games, add them to Steam, give them artwork; and the background upscale queue.
import { toaster } from "@decky/api";
import * as be from "./backend";
import { t } from "./i18n";
import { getPluginState, log, update } from "./state";
import {
  addShortcut, ensureLogoPosition, gameRunning, isShortcut, setArtwork, setShortcutIcon, storeAssets,
  storeItem, storeName,
} from "./steam";

export async function loadState(): Promise<void> {
  const r = await be.getState();
  if (r.ok) update({ settings: r.settings, games: r.games, upscaler: r.upscaler, deps: r.deps });
}

/**
 * The backend fetches its dependencies on the first start. Follow it until it finishes, then start upscaling
 * whatever waited for it (the art of games added meanwhile, small pictures already in the library).
 */
export async function followDeps(): Promise<void> {
  for (let i = 0; i < 240 && ["missing", "installing"].includes(getPluginState().deps.status); i++) {
    await new Promise((r) => setTimeout(r, 5000));
    await loadState();
  }
  const d = getPluginState().deps;
  if (d.status === "ready") {
    log(t("Dependencies installed", "Зависимости установлены"));
    void runArtQueue();
  } else if (d.status === "error") {
    log(t(`Dependencies were not installed: ${d.error}`, `Зависимости не установились: ${d.error}`), "error");
  }
}

export async function installDeps(): Promise<void> {
  update({ deps: { status: "installing", error: "" } });
  const r = await be.installDeps();
  update({ deps: r.deps, upscaler: r.deps.status === "ready" });
  if (r.ok) {
    log(t("Dependencies installed", "Зависимости установлены"));
    void runArtQueue();
  } else {
    log(t(`Dependencies: ${r.error}`, `Зависимости: ${r.error}`), "error");
  }
}

async function applyFile(appid: number, path: string, format: "jpg" | "png", type: number) {
  const f = await be.readB64(path);
  if (!f.ok) throw new Error(f.error);
  await setArtwork(appid, f.data, format, type);
}

/** Scales a picture down to exactly width x height in the browser (high-quality smoothing), as JPEG or PNG. */
async function resized(b64: string, mime: string, width: number, height: number, format: "jpg" | "png"): Promise<string> {
  const img = new Image();
  img.src = `data:${mime};base64,${b64}`;
  await img.decode();
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas is not available");
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  // Big reductions in halving steps, which keeps fine detail better than one jump.
  let src: CanvasImageSource = img;
  let w = img.naturalWidth, h = img.naturalHeight;
  while (w / 2 >= width * 1.2) {
    const step = document.createElement("canvas");
    step.width = Math.round(w / 2);
    step.height = Math.round(h / 2);
    const sctx = step.getContext("2d")!;
    sctx.imageSmoothingQuality = "high";
    sctx.drawImage(src, 0, 0, step.width, step.height);
    src = step;
    w = step.width;
    h = step.height;
  }
  ctx.drawImage(src, 0, 0, width, height);
  const url = canvas.toDataURL(format === "jpg" ? "image/jpeg" : "image/png", 0.9);
  return url.slice(url.indexOf(",") + 1);
}

async function artworkForNewGame(appid: number, steamAppid: number, title: string, item: any) {
  const r = await be.artForNew(appid, steamAppid, title, storeAssets(item));
  if (!r.ok) {
    log(t(`Artwork for "${title}": ${r.error}`, `Обложки для «${title}»: ${r.error}`), "warn");
    return;
  }
  for (const a of r.assets) {
    try {
      await applyFile(appid, a.path, a.format, a.type);
      // Recorded as ours only when it is final: a small one stays in the upscale queue for later.
      if (getPluginState().upscaler || !getPluginState().settings?.upscale) {
        await be.artApplied(appid, a.kind, a.source, "");
      }
    } catch (e) {
      log(t(`${a.kind} for "${title}" was not set: ${e}`, `Обложка ${a.kind} для «${title}» не установлена: ${e}`), "warn");
    }
  }
  if (r.assets.some((a) => a.kind === "logo")) await ensureLogoPosition(appid, r.logo_pos);
  if (r.icon) setShortcutIcon(appid, r.icon);
  const list = r.assets.map((a) => `${a.kind} (${a.source})`).join(", ");
  log(t(`Artwork for "${title}": ${list || "none found"}${r.icon ? ", icon" : ""}`,
    `Обложки «${title}»: ${list || "не найдены"}${r.icon ? ", иконка" : ""}`));
}

// A button that finishes in a blink looks like it did nothing: keep its busy state on screen a moment.
const MIN_BUSY_MS = 800;

async function atLeast(started: number) {
  const left = MIN_BUSY_MS - (Date.now() - started);
  if (left > 0) await new Promise((r) => setTimeout(r, left));
}

function clock() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export async function refreshLibrary(): Promise<void> {
  if (getPluginState().busy) return;
  const started = Date.now();
  let result = "";
  update({ busy: t("Looking for new games…", "Ищу новые игры…") });
  try {
    const scan = await be.scanLibrary();
    if (!scan.ok) {
      log(t(`Game search: ${scan.error}`, `Поиск игр: ${scan.error}`), "error");
      result = t(`Error: ${scan.error}`, `Ошибка: ${scan.error}`);
      return;
    }
    const attention = [
      ...scan.busy.map((c) => ({ title: c.title, root: c.root, reason: t("still unpacking or downloading", "ещё распаковывается или скачивается") })),
      ...scan.no_exe.map((c) => ({ title: c.title, root: c.root, reason: t("no game .exe found", "не найден .exe игры") })),
    ];
    const added: { appid: number; cand: be.Candidate; name: string; item: any }[] = [];
    for (const cand of scan.new) {
      update({ busy: t(`Adding "${cand.title}"…`, `Добавляю «${cand.title}»…`) });
      try {
        const item = cand.steam_appid ? await storeItem(cand.steam_appid) : null;
        const name = storeName(item) || cand.title;
        const appid = await addShortcut(name, cand.exe, cand.start_dir, cand.launch_options, scan.compat_tool);
        await be.registerAdded(appid, { ...cand, title: name });
        added.push({ appid, cand, name, item });
        log(t(`Added "${name}"`, `Добавлена «${name}»`) + (cand.steam_appid ? ` (Steam ${cand.steam_appid})` : t(" — no Steam data", " — без данных Steam")));
        if (!cand.steam_appid) attention.push({ title: name, root: cand.root, reason: t("not found on Steam: pick it by hand", "не найдена в Steam: укажите вручную") });
        if (cand.ambiguous) attention.push({ title: name, root: cand.root, reason: t(`check the exe: ${cand.exe.split("/").pop()}`, `проверьте exe: ${cand.exe.split("/").pop()}`) });
      } catch (e) {
        log(t(`"${cand.title}" was not added: ${e}`, `«${cand.title}» не добавлена: ${e}`), "error");
      }
    }
    if (added.length) {
      toaster.toast({
        title: "Custom Games",
        body: added.length === 1 ? t(`Added "${added[0].name}"`, `Добавлена игра «${added[0].name}»`)
          : t(`Games added: ${added.length}`, `Добавлено игр: ${added.length}`),
      });
    }
    update({ attention, lastScan: Date.now() });
    await loadState();
    if (getPluginState().settings?.art_new_games) {
      for (const a of added) {
        update({ busy: t(`Artwork for "${a.name}"…`, `Обложки для «${a.name}»…`) });
        await artworkForNewGame(a.appid, a.cand.steam_appid, a.name, a.item);
      }
    }
    update({ busy: t("Matching games with Steam…", "Сопоставляю игры со Steam…") });
    const res = await be.resolveGames(false);
    if (res.ok) update({ games: res.games });
    result = added.length ? t(`Games added: ${added.length}`, `Добавлено игр: ${added.length}`) : t("No new games", "Новых игр нет");
    if (attention.length) result += t(` · need attention: ${attention.length}`, ` · требуют внимания: ${attention.length}`);
  } catch (e) {
    log(t(`Library update: ${e}`, `Обновление библиотеки: ${e}`), "error");
    result = t(`Error: ${e}`, `Ошибка: ${e}`);
  } finally {
    await atLeast(started);
    update({ busy: null, libResult: result ? `${clock()} · ${result}` : null });
  }
  void runArtQueue();
}

let artRunning = false;

/**
 * Keeps library images at the size Steam shows: too small ones are upscaled on the GPU, too big ones are scaled
 * down (oversized pictures make scrolling slower). Also covers pictures someone else changed later, e.g. with
 * the SteamGridDB plugin.
 */
export async function runArtQueue(manual = false): Promise<void> {
  const s = getPluginState().settings;
  if (artRunning || !s) return;
  const finish = (text: string) => {
    if (manual) update({ artResult: `${clock()} · ${text}` });
  };
  if (!s.upscale) {
    finish(t("resizing is turned off", "подгонка размера выключена"));
    return;
  }
  if (gameRunning()) {
    finish(t("a game is running — will check after it closes", "игра запущена — проверю после её закрытия"));
    return;
  }
  artRunning = true;
  const started = Date.now();
  let done = 0, failed = 0, total = 0;
  // the background check every 90 s shows itself only when it has something to do
  if (manual) update({ artBusy: t("Checking artwork…", "Проверяю обложки…") });
  try {
    const scan = await be.artScan(null);
    if (!scan.ok) {
      log(t(`Artwork check: ${scan.error}`, `Проверка обложек: ${scan.error}`), "warn");
      finish(t(`error: ${scan.error}`, `ошибка: ${scan.error}`));
      return;
    }
    update({ upscaler: scan.installed });
    const jobs = scan.jobs.filter((j) => j.action === "down" || scan.installed);
    total = jobs.length;
    update({ artQueue: jobs.length });
    for (const job of jobs) {
      if (gameRunning()) break; // the GPU belongs to the game; continue after it closes
      const title = getPluginState().games[String(job.appid)]?.title;
      update({ artQueue: jobs.length - done, artBusy: (job.action === "down" ? t("Downscaling", "Уменьшаю") : t("Upscaling", "Апскейл"))
        + t(` ${done + failed + 1} of ${jobs.length}`, ` ${done + failed + 1} из ${jobs.length}`)
        + (title ? `: ${title}` : "") });
      const r = await be.artProcess(job);
      if (!r.ok) {
        if (!r.stale) {
          failed++;
          log(t(`Artwork ${job.kind} ${job.appid}: ${r.error}`, `Обложка ${job.kind} ${job.appid}: ${r.error}`), "warn");
        }
        continue;
      }
      try {
        if (r.resize) {
          const f = await be.readB64(r.path);
          if (!f.ok) throw new Error(f.error);
          const data = await resized(f.data, r.mime || "image/png", r.width!, r.height!, r.format);
          await setArtwork(job.appid, data, r.format, r.type);
        } else {
          await applyFile(job.appid, r.path, r.format, r.type);
        }
        if (job.kind === "logo" && isShortcut(job.appid)) await ensureLogoPosition(job.appid, null);
        await be.artApplied(job.appid, job.kind, job.action === "down" ? "downscale" : "upscale", job.sha);
        done++;
        update({ artDone: getPluginState().artDone + 1 });
      } catch (e) {
        failed++;
        await be.artFailed(job.appid, job.kind, String(e));
        log(t(`Could not set ${job.kind} ${job.appid}: ${e}`, `Не удалось поставить ${job.kind} ${job.appid}: ${e}`), "warn");
      }
    }
    update({ artQueue: Math.max(0, jobs.length - done - failed) });
    if (done) log(t(`Artwork resized: ${done}`, `Обложки приведены к нужному размеру: ${done}`));
  } finally {
    if (manual) await atLeast(started);
    artRunning = false;
    update({ artBusy: null });
  }
  const skipped = total - done - failed;
  finish(!total ? t("all artwork is the right size", "все обложки нужного размера")
    : t(`updated ${done}`, `обновлено ${done}`) + (failed ? t(`, errors ${failed}`, `, ошибок ${failed}`) : "")
      + (skipped > 0 ? t(`, postponed ${skipped} (a game is running)`, `, отложено ${skipped} (запущена игра)`) : ""));
}

let timer: number | null = null;

export function startWatcher() {
  stopWatcher();
  timer = window.setInterval(() => {
    if (!getPluginState().busy) void runArtQueue();
  }, 90_000);
}

export function stopWatcher() {
  if (timer !== null) window.clearInterval(timer);
  timer = null;
}
