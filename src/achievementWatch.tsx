// Achievement pop-ups for non-Steam games: while a linked game runs, its emulator's achievement file is
// checked every few seconds, and every newly earned achievement is announced like Steam does.
import { toaster } from "@decky/api";
import * as be from "./backend";
import { getPluginState, gameFor, log } from "./state";
import { language } from "./steam";
import { t } from "./i18n";

declare const SteamClient: any;

const POLL_MS = 3000;
// Some emulators write the file only when the game closes: one more look after it exits.
const AFTER_EXIT_MS = 6000;
const ICON_BASE = "https://cdn.akamai.steamstatic.com/steamcommunity/public/images/apps";

const running = new Map<number, number>(); // shortcut appid -> interval id
const schemas = new Map<number, Promise<Record<string, be.AchievementDef>>>();

function schema(steamAppid: number): Promise<Record<string, be.AchievementDef>> {
  let p = schemas.get(steamAppid);
  if (!p) {
    const lang = getPluginState().settings?.data_lang || language();
    p = be.achievementSchema(steamAppid, lang).then((r) => {
      if (!r.ok) throw new Error(r.error);
      return Object.fromEntries(r.achievements.map((a) => [a.name, a]));
    });
    p.catch(() => schemas.delete(steamAppid));
    schemas.set(steamAppid, p);
  }
  return p;
}

function Icon({ src }: { src: string }) {
  return <img src={src} style={{ width: "100%", height: "100%", borderRadius: 4, objectFit: "cover" }} />;
}

async function announce(appid: number, steamAppid: number, items: { name: string }[]) {
  let defs: Record<string, be.AchievementDef> = {};
  try {
    defs = await schema(steamAppid);
  } catch (_) {
    /* show the API names then */
  }
  const total = Object.keys(defs).length;
  for (const a of items) {
    const d = defs[a.name];
    const icon = d?.icon ? `${ICON_BASE}/${steamAppid}/${d.icon}` : "";
    toaster.toast({
      title: d?.title || a.name,
      body: d?.desc || t("Achievement unlocked", "Достижение получено"),
      subtext: total ? `${gameFor(appid)?.title ?? ""} · ${d ? d.pct.toFixed(1) + t("% of players", "% игроков") : ""}` : undefined,
      logo: icon ? <Icon src={icon} /> : undefined,
      duration: 6000,
      playSound: true,
      showToast: true,
    });
    log(t("Achievement: ", "Достижение: ") + `${d?.title || a.name} (${gameFor(appid)?.title ?? appid})`);
    await new Promise((r) => setTimeout(r, 1200)); // several at once: one after another
  }
}

async function poll(appid: number, steamAppid: number) {
  const r = await be.pollAchievements(appid, steamAppid);
  if (r.ok && r.new.length) await announce(appid, steamAppid, r.new);
}

function start(appid: number) {
  const g = gameFor(appid);
  if (!g || running.has(appid)) return;
  void poll(appid, g.steam_appid); // the baseline: what was earned before this session
  running.set(appid, window.setInterval(() => void poll(appid, g.steam_appid), POLL_MS));
}

function stop(appid: number) {
  const id = running.get(appid);
  if (id === undefined) return;
  window.clearInterval(id);
  running.delete(appid);
  const g = gameFor(appid);
  window.setTimeout(async () => {
    if (g) await poll(appid, g.steam_appid);
    if (!running.has(appid)) await be.stopAchievements(appid);
  }, AFTER_EXIT_MS);
}

/** Starts listening to game launches; returns the function that stops everything. */
export function watchAchievements(): () => void {
  let reg: any = null;
  try {
    reg = SteamClient.GameSessions.RegisterForAppLifetimeNotifications((n: any) => {
      const appid = (n?.unAppID ?? 0) >>> 0;
      if (!gameFor(appid)) return;
      if (n.bRunning) start(appid);
      else stop(appid);
    });
  } catch (e) {
    console.error("[Custom Games] achievement watcher failed", e);
  }
  return () => {
    try {
      reg?.unregister?.();
    } catch (_) {
      /* ignore */
    }
    running.forEach((id) => window.clearInterval(id));
    running.clear();
  };
}
