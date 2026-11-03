// Data for the game page tabs, cached for the session: store item, store details, news, achievements.
import { useEffect, useState } from "react";
import * as be from "./backend";
import { getPluginState } from "./state";
import { language, storeItem } from "./steam";

declare const partnerEventStore: any;

function dataLang(): string {
  return getPluginState().settings?.data_lang || language();
}

const cache = new Map<string, Promise<any>>();

function cached<T>(key: string, load: () => Promise<T>): Promise<T> {
  let p = cache.get(key);
  if (!p) {
    p = load().catch((e) => {
      cache.delete(key); // try again next time
      throw e;
    });
    cache.set(key, p);
  }
  return p as Promise<T>;
}

function useAsync<T>(key: string | null, load: () => Promise<T>): { data: T | null; error: string | null } {
  const [res, setRes] = useState<{ key: string | null; data: T | null; error: string | null }>({ key: null, data: null, error: null });
  useEffect(() => {
    if (!key) return;
    let alive = true;
    cached(key, load).then(
      (data) => alive && setRes({ key, data, error: null }),
      (e) => alive && setRes({ key, data: null, error: String(e) }),
    );
    return () => {
      alive = false;
    };
  }, [key]);
  return res.key === key ? { data: res.data, error: res.error } : { data: null, error: null };
}

export function useStoreItem(steamAppid: number) {
  return useAsync(steamAppid ? `item:${steamAppid}` : null, () => storeItem(steamAppid));
}

export function useDetails(steamAppid: number) {
  const lang = dataLang();
  return useAsync(steamAppid ? `details:${steamAppid}:${lang}` : null, async () => {
    const r = await be.storeDetails(steamAppid, lang);
    if (!r.ok) throw new Error(r.error);
    return r.details;
  });
}

export function useAchievementDefs(steamAppid: number) {
  const lang = dataLang();
  return useAsync(steamAppid ? `ach:${steamAppid}:${lang}` : null, async () => {
    const r = await be.achievementSchema(steamAppid, lang);
    if (!r.ok) throw new Error(r.error);
    return r.achievements;
  });
}

/** Emulator progress is local and changes while playing: not cached across page visits. */
export function useAchievementProgress(appid: number, steamAppid: number) {
  const [data, setData] = useState<{ files: number; progress: Record<string, be.AchievementState> } | null>(null);
  useEffect(() => {
    let alive = true;
    be.getAchievements(appid, steamAppid).then((r) => alive && r.ok && setData({ files: r.files, progress: r.progress }));
    return () => {
      alive = false;
    };
  }, [appid, steamAppid]);
  return data;
}

export interface NewsItem {
  gid: string;
  title: string;
  summary: string;
  image: string;
  time: number;
  type: number;
  comments: number;
  votes: number;
  url: string;
}

function eventImage(ev: any): string {
  for (const f of [() => ev.GetImageURL?.("capsule"), () => ev.GetImageURL?.("spotlight"), () => ev.GetImageFromBeginningOfDescription?.()]) {
    try {
      const v = f();
      if (typeof v === "string" && v) return v;
    } catch (_) {
      /* next */
    }
  }
  return "";
}

function eventSummary(ev: any): string {
  let s = "";
  try {
    s = ev.GetSummaryWithFallback?.(0) || ev.GetSummary?.(0) || "";
  } catch (_) {
    /* ignore */
  }
  return String(s).replace(/\[[^\]]*\]/g, " ").replace(/\{STEAM_CLAN_IMAGE\}\S*/g, "").replace(/^[\s•:·-]+/, "")
    .replace(/\s+/g, " ").trim();
}

/** Steam news and events of a game through the client's own event store (same data the library shows). */
export async function loadNews(steamAppid: number, offset: number, count: number): Promise<NewsItem[]> {
  return cached(`news:${steamAppid}:${offset}:${count}`, async () => {
    if (typeof partnerEventStore === "undefined") throw new Error("partnerEventStore is not available");
    const evs: any[] = await partnerEventStore.LoadPartnerEventsPageable(undefined, steamAppid, offset, count);
    return evs.map((ev) => {
      let title = "";
      try {
        title = ev.GetNameWithFallback?.(0) || "";
      } catch (_) {
        /* ignore */
      }
      const gid = String(ev.AnnouncementGID || ev.GID || "");
      return {
        gid, title, summary: eventSummary(ev), image: eventImage(ev), time: ev.startTime || ev.postTime || 0,
        type: ev.type, comments: ev.nCommentCount || 0, votes: ev.nVotesUp || 0,
        url: `https://store.steampowered.com/news/app/${steamAppid}/view/${gid}`,
      };
    });
  });
}
