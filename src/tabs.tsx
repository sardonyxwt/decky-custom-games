// Contents of the four native tabs on a non-Steam game's page, filled with the real Steam game's data.
import { DialogButton, Focusable } from "@decky/ui";
import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { FaCloud, FaComments, FaGamepad, FaThumbsUp, FaTrophy, FaUser, FaUsers } from "react-icons/fa";
import { ACHIEVEMENT_ICON_BASE } from "./backend";
import type { AchievementDef, GameRecord } from "./backend";
import { openMapping, openUrl, openViewer } from "./modals";
import {
  loadNews, NewsItem, useAchievementDefs, useAchievementProgress, useDetails, useStoreItem,
} from "./pageData";
import { isRussian, t } from "./i18n";
import { getPluginState } from "./state";
import { Styles } from "./styles";

declare const appDetailsStore: any;

export interface TabProps { appid: number; game: GameRecord; native: ReactNode }

// Steam's Focusable takes "focusable" for items that do nothing on A but must be reachable with the D-pad
// (reading text, browsing achievements). Decky's typings do not list it.
const READABLE = { focusable: true } as any;

/**
 * The game page's scroll containers are wider than the screen (Steam's blurred background canvas sticks out),
 * so a focus jump can scroll the whole page sideways. While our tab is shown, keep every horizontally
 * hidden-overflow ancestor at scrollLeft 0. Steam's own vertical scrolling is untouched.
 */
function useNoSideScroll() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    const win = el?.ownerDocument?.defaultView;
    if (!el || !win) return;
    const fixed: HTMLElement[] = [];
    for (let p = el.parentElement; p; p = p.parentElement) {
      const ox = win.getComputedStyle(p).overflowX;
      if (ox === "hidden" || ox === "clip" || ox === "auto" || ox === "scroll") fixed.push(p);
    }
    const reset = (e: Event) => {
      const t = e.currentTarget as HTMLElement;
      if (t.scrollLeft !== 0) t.scrollLeft = 0;
    };
    fixed.forEach((p) => {
      if (p.scrollLeft !== 0) p.scrollLeft = 0;
      p.addEventListener("scroll", reset, { passive: true });
    });
    return () => fixed.forEach((p) => p.removeEventListener("scroll", reset));
  }, []);
  return ref;
}

function locale(): string | undefined {
  const l = getPluginState().settings?.data_lang;
  return isRussian() || l === "russian" || l === "ru" ? "ru-RU" : undefined;
}

function fmtDay(t: number) {
  return new Date(t * 1000).toLocaleDateString(locale(), { day: "numeric", month: "long", year: "numeric" });
}

function fmtDate(t: number) {
  return new Date(t * 1000).toLocaleDateString(locale(), { day: "numeric", month: "short", year: "numeric" });
}

const NEWS_TYPE: Record<number, [string, string]> = {
  12: ["Patch notes", "Патч"], 13: ["Update", "Обновление"], 14: ["Major update", "Крупное обновление"],
  28: ["News", "Новости"], 9: ["Broadcast", "Трансляция"], 11: ["In-game event", "Внутриигровое событие"],
  15: ["DLC release", "Выход DLC"], 20: ["Sale", "Распродажа"],
};

function Loading({ error }: { error?: string | null }) {
  return <div className="cg-dim" style={{ padding: "20px 0" }}>{error ? t(`Could not load: ${error}`, `Не удалось загрузить: ${error}`) : t("Loading…", "Загрузка…")}</div>;
}

// ---------------- Activity ----------------

export function ActivityTab({ appid, game, native }: TabProps) {
  const root = useNoSideScroll();
  const sid = game.steam_appid;
  const item = useStoreItem(sid).data;
  const defs = useAchievementDefs(sid).data;
  const prog = useAchievementProgress(appid, sid);
  const [news, setNews] = useState<NewsItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [end, setEnd] = useState(false);

  const more = async () => {
    try {
      const page = await loadNews(sid, news?.length ?? 0, 8);
      setNews([...(news ?? []), ...page]);
      if (page.length < 8) setEnd(true);
    } catch (e) {
      setError(String(e));
    }
  };
  useEffect(() => {
    setNews(null);
    setEnd(false);
    loadNews(sid, 0, 8).then((p) => {
      setNews(p);
      if (p.length < 8) setEnd(true);
    }, (e) => setError(String(e)));
  }, [sid]);

  const fallback = item?.m_Assets?.m_strHeaderURL || "";
  // One timeline, newest first: news cards, and per day a card with the achievements earned that day
  // (like the "… achieved" entries Steam shows for bought games).
  type Entry = { time: number; key: string; node: ReactNode };
  const entries: Entry[] = [];
  for (const n of news ?? []) {
    entries.push({ time: n.time, key: n.gid, node: (
      <Focusable className="cg-card cg-news" onActivate={() => openUrl(n.url)} onClick={() => openUrl(n.url)}>
        <div className="cg-news-img" style={{ backgroundImage: `url("${n.image || fallback}")` }} />
        <div className="cg-news-body">
          <div className="cg-news-type">{NEWS_TYPE[n.type] ? t(...NEWS_TYPE[n.type]) : t("Event", "Событие")}</div>
          <div className="cg-news-title">{n.title}</div>
          <div className="cg-news-sum">{n.summary}</div>
          <div className="cg-news-meta">
            <span><FaComments style={{ marginRight: 6 }} />{n.comments}</span>
            <span><FaThumbsUp style={{ marginRight: 6 }} />{n.votes.toLocaleString(locale())}</span>
          </div>
        </div>
      </Focusable>
    ) });
  }
  const byName = new Map((defs ?? []).map((d) => [d.name, d]));
  const days = new Map<string, { time: number; list: AchievementDef[] }>();
  for (const [name, p] of Object.entries(prog?.progress ?? {})) {
    const d = byName.get(name);
    if (!p.earned || !p.time || !d) continue;
    const day = fmtDay(p.time);
    const g = days.get(day) ?? { time: 0, list: [] };
    g.time = Math.max(g.time, p.time);
    g.list.push(d);
    days.set(day, g);
  }
  // achievements older than the news shown so far wait until more news is loaded
  const oldest = news?.length && !end ? news[news.length - 1].time : 0;
  for (const [day, g] of days) {
    if (g.time < oldest) continue;
    entries.push({ time: g.time, key: "ach-" + day, node: (
      <Focusable className="cg-card cg-achday" {...READABLE}>
        <div className="cg-achday-head"><FaTrophy /> {t("Achievements unlocked: ", "Получено достижений: ")}{g.list.length}</div>
        <div className="cg-achday-list">
          {g.list.slice(0, 8).map((d) => (
            <div key={d.name} className="cg-achday-item">
              <img src={`${ACHIEVEMENT_ICON_BASE}/${sid}/${d.icon}`} />
              <div><div className="cg-ach-title">{d.title}</div><div className="cg-ach-desc">{d.desc}</div></div>
            </div>
          ))}
          {g.list.length > 8 && <div className="cg-dim">{t(`and ${g.list.length - 8} more`, `и ещё ${g.list.length - 8}`)}</div>}
        </div>
      </Focusable>
    ) });
  }
  entries.sort((a, b) => b.time - a.time);
  let lastDay = "";
  return (
    <div className="cg-tab" ref={root}>
      <Styles />
      <div className="cg-h2">{t("News and achievements", "Новости и достижения")}</div>
      {!news && <Loading error={error} />}
      {news && !entries.length && <div className="cg-dim">{t("This game has no news on Steam.", "У этой игры нет новостей в Steam.")}</div>}
      {entries.map((e) => {
        const day = fmtDay(e.time);
        const sep = day !== lastDay ? <div className="cg-day">{day}</div> : null;
        lastDay = day;
        return <div key={e.key}>{sep}{e.node}</div>;
      })}
      {news && !end && (
        <Focusable className="cg-buttons"><DialogButton onClick={more}>{t("Show more", "Показать ещё")}</DialogButton></Focusable>
      )}
      {native}
    </div>
  );
}

// ---------------- Game info ----------------

const DECK: Record<number, [[string, string], boolean]> = {
  3: [["Verified", "Проверено"], true], 2: [["Playable", "Играбельно"], true], 1: [["Unsupported", "Не поддерживается"], false],
};

function featureIcon(id: number) {
  if (id === 2) return <FaUser />;
  if ([1, 9, 20, 27, 36, 37, 38, 39, 47, 48, 49].includes(id)) return <FaUsers />;
  if (id === 22) return <FaTrophy />;
  if (id === 23) return <FaCloud />;
  if (id === 18 || id === 28) return <FaGamepad />;
  return <span style={{ width: 16, display: "inline-block" }}>•</span>;
}

/** Store HTML (about the game) as plain paragraphs; headings kept, pictures dropped. */
function paragraphs(html: string): { text: string; head: boolean }[] {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const out: { text: string; head: boolean }[] = [];
  const walk = (el: Element) => {
    for (const child of Array.from(el.children)) {
      const tag = child.tagName.toLowerCase();
      if (["h1", "h2", "h3", "h4", "p", "li"].includes(tag) || (tag === "div" && !child.children.length)) {
        const text = (child.textContent || "").replace(/\s+/g, " ").trim();
        if (text) out.push({ text: (tag === "li" ? "• " : "") + text, head: tag.startsWith("h") });
      } else {
        walk(child);
      }
    }
  };
  walk(doc.body);
  if (!out.length) {
    for (const part of (doc.body.innerHTML || "").split(/<br\s*\/?>/i)) {
      const text = new DOMParser().parseFromString(part, "text/html").body.textContent?.replace(/\s+/g, " ").trim();
      if (text) out.push({ text, head: false });
    }
  }
  return out;
}

function compatText(appid: number): string | null {
  try {
    const d = appDetailsStore?.GetAppDetails?.(appid);
    return d?.strCompatToolDisplayName || d?.strCompatToolName || null;
  } catch (_) {
    return null;
  }
}

export function GameInfoTab({ appid, game }: TabProps) {
  const root = useNoSideScroll();
  const sid = game.steam_appid;
  const { data: item, error } = useStoreItem(sid);
  const details = useDetails(sid).data;
  const [full, setFull] = useState(false);
  const paras = useMemo(() => (details?.about_the_game ? paragraphs(details.about_the_game) : []), [details]);

  if (!item && !details) return <div className="cg-tab" ref={root}><Styles /><Loading error={error} /></div>;
  const basic = item?.m_BasicInfo ?? {};
  const rev = item?.m_ReviewInfo?.summary_filtered;
  const release = item?.m_ReleaseInfo?.steam_release_date || item?.m_ReleaseInfo?.original_steam_release_date;
  const deck = DECK[item?.m_Platforms?.steam_deck_compat_category ?? 0];
  const cover = item?.m_Assets?.m_strLibraryCapsuleURL_2x || item?.m_Assets?.m_strLibraryCapsuleURL || "";
  const langs = (details?.supported_languages || "").replace(/<br>.*$/i, "").replace(/<strong>\*<\/strong>/g, "*")
    .replace(/<[^>]+>/g, "");
  const proton = compatText(appid);
  const rows: [string, ReactNode][] = [];
  const devs = (basic.developers ?? []).map((d: any) => d.name).join(", ") || details?.developers?.join(", ");
  const pubs = (basic.publishers ?? []).map((d: any) => d.name).join(", ") || details?.publishers?.join(", ");
  if (devs) rows.push([t("Developer:", "Разработчик:"), devs]);
  if (pubs) rows.push([t("Publisher:", "Издатель:"), pubs]);
  if (basic.franchises?.length) rows.push([t("Franchise:", "Серия:"), basic.franchises.map((f: any) => f.name).join(", ")]);
  if (details?.genres?.length) rows.push([t("Genre:", "Жанр:"), details.genres.map((g) => g.description).join(", ")]);
  if (release) rows.push([t("Release date:", "Дата выхода:"), fmtDate(release)]);
  else if (details?.release_date?.date) rows.push([t("Release date:", "Дата выхода:"), details.release_date.date]);
  if (rev?.review_count) {
    rows.push([t("Reviews:", "Отзывы:"), <span><span className="cg-good">{rev.review_score_label}</span>
      {t(` (${rev.percent_positive}% of ${rev.review_count.toLocaleString(locale())})`, ` (${rev.percent_positive}% из ${rev.review_count.toLocaleString(locale())})`)}</span>]);
  }
  if (details?.metacritic?.score) rows.push(["Metacritic:", String(details.metacritic.score)]);
  const desc = details?.short_description || basic.short_description || "";
  const community = `https://steamcommunity.com/app/${sid}`;

  return (
    <div className="cg-tab" ref={root}>
      <Styles />
      <div className="cg-info-top">
        {cover && <img className="cg-cover" src={cover} />}
        <div className="cg-info-main">
          <div className="cg-desc">{desc}</div>
          <div className="cg-rows">{rows.map(([k, v]) => [<div key={k}>{k}</div>, <div key={k + "v"}>{v}</div>])}</div>
        </div>
        {!!details?.categories?.length && (
          <div className="cg-features">
            {details.categories.filter((c, i, all) => all.findIndex((x) => x.description === c.description) === i)
              .slice(0, 9).map((c) => (
              <div className="cg-feature" key={c.id}>{featureIcon(c.id)}<span>{c.description}</span></div>
            ))}
          </div>
        )}
      </div>
      {deck && <div className="cg-line">Steam Deck: <b className={deck[1] ? "cg-good" : ""}>{t(...deck[0])}</b> {t("(Valve's rating)", "(оценка Valve)")}</div>}
      {langs && <div className="cg-line">{t("Languages: ", "Языки: ")}{langs}{langs.includes("*") ? t("  (* — with voice-over)", "  (* — с озвучкой)") : ""}</div>}
      {proton && <div className="cg-line">{t("Runs through ", "Запускается через ")}<b>{proton}</b>.</div>}
      <Focusable className="cg-buttons" flow-children="row">
        <DialogButton onClick={() => openUrl(`https://store.steampowered.com/app/${sid}`)}>{t("Store page", "Магазин")}</DialogButton>
        <DialogButton onClick={() => openUrl(community)}>{t("Community hub", "Центр сообщества")}</DialogButton>
        <DialogButton onClick={() => openUrl(`${community}/discussions/`)}>{t("Discussions", "Обсуждения")}</DialogButton>
        <DialogButton onClick={() => openUrl(`${community}/guides/`)}>{t("Guides", "Руководства")}</DialogButton>
        {details?.website && <DialogButton onClick={() => openUrl(details.website!)}>{t("Website", "Сайт игры")}</DialogButton>}
      </Focusable>
      {!!paras.length && (
        <>
          <div className="cg-h3">{t("About the game", "Об игре")}</div>
          {(full ? paras : paras.slice(0, 3)).map((p, i) => (
            <Focusable key={i} className={"cg-para" + (p.head ? " cg-head" : "")} noFocusRing {...READABLE}>{p.text}</Focusable>
          ))}
          {paras.length > 3 && (
            <Focusable className="cg-buttons">
              <DialogButton onClick={() => setFull(!full)}>{full ? t("Show less", "Свернуть") : t("Read more", "Читать полностью")}</DialogButton>
            </Focusable>
          )}
        </>
      )}
      <Focusable className="cg-card cg-mapping" flow-children="row">
        <span>{t("Steam data: ", "Данные Steam: ")}{basic.name || item?.m_strName || details?.name || sid} ({sid}) · {sourceText(game.appid_source)}</span>
        <DialogButton className="cg-btn" onClick={() => openMapping(appid, game.title)}>{t("Change", "Изменить")}</DialogButton>
      </Focusable>
    </div>
  );
}

function sourceText(src: string): string {
  if (src.startsWith("file:")) return t(`found in ${src.slice(5).split("/").pop()}`, `найдено в файле ${src.slice(5).split("/").pop()}`);
  if (src.startsWith("prefix:")) return t(`found in ${src.slice(7)} saves`, `найдено в сохранениях ${src.slice(7)}`);
  if (src.startsWith("name:")) return t("matched by name", "найдено по названию");
  if (src === "manual") return t("chosen by hand", "выбрано вручную");
  return "";
}

// ---------------- Your stuff: achievements ----------------


export function YourStuffTab({ appid, game, native }: TabProps) {
  const root = useNoSideScroll();
  const sid = game.steam_appid;
  const { data: defs, error } = useAchievementDefs(sid);
  const prog = useAchievementProgress(appid, sid);

  const earned: (AchievementDef & { time: number })[] = [];
  const locked: (AchievementDef & { cur: number; max: number })[] = [];
  for (const d of defs ?? []) {
    const p = prog?.progress[d.name];
    if (p?.earned) earned.push({ ...d, time: p.time });
    else locked.push({ ...d, cur: p?.cur ?? 0, max: p?.max ?? 0 });
  }
  earned.sort((a, b) => b.time - a.time);
  locked.sort((a, b) => b.pct - a.pct);
  const total = defs?.length ?? 0;

  return (
    <div className="cg-tab" ref={root}>
      <Styles />
      <div className="cg-h2">{t("Achievements", "Достижения")}</div>
      {!defs && <Loading error={error} />}
      {defs && !total && <div className="cg-dim">{t("This game has no achievements on Steam.", "У этой игры нет достижений в Steam.")}</div>}
      {!!total && (
        <>
          <div style={{ fontSize: 18 }}>
            {prog?.files ? <>{t("Unlocked ", "Получено ")}<b style={{ color: "#fff" }}>{earned.length}</b>{t(" of ", " из ")}{total}</> : <>{t("Total: ", "Всего: ")}{total}</>}
          </div>
          {!!prog?.files && <div className="cg-bar"><div style={{ width: `${(earned.length / total) * 100}%` }} /></div>}
          {prog && !prog.files && (
            <div className="cg-dim" style={{ margin: "8px 0 16px" }}>
              {t("Progress appears after the game has run, if its Steam emulator saves achievements (GSE/Goldberg, RUNE, CODEX).",
                "Прогресс появится после запуска игры, если её эмулятор Steam сохраняет достижения (GSE/Goldberg, RUNE, CODEX).")}
            </div>
          )}
          {!!earned.length && <div className="cg-h3">{t("Unlocked", "Полученные")}</div>}
          <Focusable className="cg-ach-grid" flow-children="grid">
            {earned.map((a) => (
              <Focusable key={a.name} className="cg-card cg-ach" {...READABLE}>
                <img src={`${ACHIEVEMENT_ICON_BASE}/${sid}/${a.icon}`} />
                <div className="cg-ach-text">
                  <div className="cg-ach-title">{a.title}</div>
                  <div className="cg-ach-desc">{a.desc}</div>
                </div>
                <div className="cg-ach-side">{a.time ? fmtDate(a.time) : ""}<br />{a.pct.toFixed(1)}{t("% of players", "% игроков")}</div>
              </Focusable>
            ))}
          </Focusable>
          {!!locked.length && <div className="cg-h3">{prog?.files ? t("Locked", "Ещё не получены") : t("All achievements", "Все достижения")}</div>}
          <Focusable className="cg-ach-grid" flow-children="grid">
            {locked.map((a) => (
              <Focusable key={a.name} className="cg-card cg-ach cg-locked" {...READABLE}>
                <img src={`${ACHIEVEMENT_ICON_BASE}/${sid}/${a.icon_gray || a.icon}`} />
                <div className="cg-ach-text">
                  <div className="cg-ach-title">{a.title}</div>
                  <div className="cg-ach-desc">{a.hidden && !a.desc ? t("Hidden achievement", "Скрытое достижение") : a.desc}</div>
                </div>
                <div className="cg-ach-side">
                  {a.max > 0 && <>{a.cur} / {a.max}<br /></>}
                  {a.pct.toFixed(1)}{t("% of players", "% игроков")}
                </div>
              </Focusable>
            ))}
          </Focusable>
        </>
      )}
      {native}
    </div>
  );
}

// ---------------- Community: trailers, screenshots, links ----------------

function thumb(url: string): string {
  return url.replace(/\.jpg(\?|$)/, ".600x338.jpg$1");
}

function TrailerCard({ t, onOpen }: { t: any; onOpen: () => void }) {
  const [focus, setFocus] = useState(false);
  return (
    <Focusable className="cg-card cg-shot" style={{ backgroundImage: `url("${t.m_strScreenshotMedium}")` }}
      onActivate={onOpen} onClick={onOpen} onGamepadFocus={() => setFocus(true)} onGamepadBlur={() => setFocus(false)}
      onMouseEnter={() => setFocus(true)} onMouseLeave={() => setFocus(false)}>
      {focus && t.m_MicroTrailer?.strMP4URL && <video src={t.m_MicroTrailer.strMP4URL} autoPlay muted loop />}
      <div className="cg-shot-label">▶ {t.m_strTrailerName}</div>
    </Focusable>
  );
}

export function CommunityTab({ game, native }: TabProps) {
  const root = useNoSideScroll();
  const sid = game.steam_appid;
  const { data: item, error } = useStoreItem(sid);
  const community = `https://steamcommunity.com/app/${sid}`;
  const trailers: any[] = [...(item?.m_Trailers?.m_highlightTrailers ?? []), ...(item?.m_Trailers?.m_otherTrailers ?? [])];
  const shots: string[] = item?.m_Screenshots?.m_rgAllScreenshots ?? [];
  const store = `https://store.steampowered.com/app/${sid}`;
  return (
    <div className="cg-tab" ref={root}>
      <Styles />
      <Focusable className="cg-buttons" flow-children="row" style={{ marginTop: 8 }}>
        <DialogButton onClick={() => openUrl(community)}>{t("Community hub", "Центр сообщества")}</DialogButton>
        <DialogButton onClick={() => openUrl(`${community}/discussions/`)}>{t("Discussions", "Обсуждения")}</DialogButton>
        <DialogButton onClick={() => openUrl(`${community}/guides/`)}>{t("Guides", "Руководства")}</DialogButton>
        <DialogButton onClick={() => openUrl(`${community}/screenshots/`)}>{t("Player screenshots", "Скриншоты игроков")}</DialogButton>
        <DialogButton onClick={() => openUrl(`${community}/workshop/`)}>{t("Workshop", "Мастерская")}</DialogButton>
      </Focusable>
      {!item && <Loading error={error} />}
      {!!trailers.length && (
        <>
          <div className="cg-h3">{t("Trailers", "Трейлеры")}</div>
          <Focusable className="cg-media" flow-children="grid">
            {trailers.map((t, i) => (
              <TrailerCard key={t.m_nBaseID ?? i} t={t} onOpen={() => openViewer(
                trailers.map((x) => ({ src: x.m_rgHlsTrailer || x.m_MicroTrailer?.strMP4URL, video: true,
                  poster: x.m_strScreenshotFull, fallback: store })), i)} />
            ))}
          </Focusable>
        </>
      )}
      {!!shots.length && (
        <>
          <div className="cg-h3">{t("Screenshots", "Скриншоты")}</div>
          <Focusable className="cg-media" flow-children="grid">
            {shots.map((s, i) => (
              <Focusable key={s} className="cg-card cg-shot" style={{ backgroundImage: `url("${thumb(s)}")` }}
                onActivate={() => openViewer(shots.map((x) => ({ src: x })), i)}
                onClick={() => openViewer(shots.map((x) => ({ src: x })), i)}>
                <span />
              </Focusable>
            ))}
          </Focusable>
        </>
      )}
      {native}
    </div>
  );
}
