import { callable } from "@decky/api";

interface Fail { ok: false; error: string; stale?: boolean }

export interface Settings {
  game_dirs: string[];
  anker: boolean;
  scan_on_start: boolean;
  art_new_games: boolean;
  upscale: boolean;
  upscale_steam_games: boolean;
  upscale_model: string;
  compat_tool: string;
  hidden: string[];
  data_lang: string;
}

export type ToggleSetting = "anker" | "scan_on_start" | "art_new_games" | "upscale" | "upscale_steam_games";

/** What the plugin knows about a non-Steam shortcut, keyed by the shortcut's appid. */
export interface GameRecord {
  steam_appid: number;
  appid_source: string; // "anker", "file:<path>", "prefix:<emulator>", "name:<store name>", "manual", "not_a_game", ""
  title: string;
  root?: string;
  exe?: string;
  source?: string;       // "anker" | "folder" (games the plugin added)
  added_by_plugin?: boolean;
  added_at?: number;
}

export interface Candidate {
  source: "anker" | "folder";
  title: string;
  root: string;
  exe: string;
  start_dir: string;
  launch_options: string;
  ambiguous: boolean;
  steam_appid: number;
  appid_source: string;
}

export interface ArtJob {
  appid: number; kind: ArtKind; path: string; sha: string; w: number; h: number; fmt: string;
  action: "up" | "down"; width: number; height: number;
}
export type ArtKind = "portrait" | "wide" | "hero" | "logo";
export interface ArtAsset { kind: ArtKind; path: string; format: "jpg" | "png"; type: number; source: string }
export interface LogoPosition { pinnedPosition: string; nWidthPct: number; nHeightPct: number }

export interface AchievementState { earned: boolean; time: number; cur: number; max: number }

export interface DepsState { status: "missing" | "installing" | "ready" | "error"; error: string }

export type StateResult =
  | { ok: true; settings: Settings; games: Record<string, GameRecord>; upscaler: boolean; models: string[]; deps: DepsState }
  | Fail;

export const getState = callable<[], StateResult>("get_state");
export const setSetting = callable<[key: string, value: unknown], StateResult>("set_setting");
export const scanLibrary = callable<[], { ok: true; new: Candidate[]; busy: Candidate[]; no_exe: Candidate[];
  compat_tool: string } | Fail>("scan_library");
export const registerAdded = callable<[appid: number, cand: Candidate], { ok: true } | Fail>("register_added");
export const resolveGames = callable<[force: boolean], { ok: true; games: Record<string, GameRecord>; changed: number } | Fail>("resolve_games");
export const setMapping = callable<[appid: number, steamAppid: number], { ok: true; games: Record<string, GameRecord> } | Fail>("set_mapping");
export const searchStore = callable<[term: string], { ok: true; items: { id: number; name: string; image: string }[] } | Fail>("search_store");
export const hideGame = callable<[root: string, hidden: boolean], StateResult>("hide_game");
export const installDeps = callable<[], { ok: boolean; deps: DepsState; error: string }>("install_deps");
export const artForNew = callable<[appid: number, steamAppid: number, title: string, steamAssets: Record<string, string>],
  { ok: true; assets: ArtAsset[]; icon: string | null; logo_pos: LogoPosition | null } | Fail>("art_for_new");
export const artScan = callable<[only: number[] | null], { ok: true; jobs: ArtJob[]; enabled: boolean; installed: boolean } | Fail>("art_scan");
export const artProcess = callable<[job: ArtJob], { ok: true; path: string; format: "jpg" | "png"; type: number;
  resize: boolean; mime?: string; width?: number; height?: number } | Fail>("art_process");
export const artApplied = callable<[appid: number, kind: ArtKind, source: string, srcSha: string], { ok: boolean }>("art_applied");
export const artFailed = callable<[appid: number, kind: ArtKind, error: string], { ok: true }>("art_failed");
export const readB64 = callable<[path: string], { ok: true; data: string } | Fail>("read_b64");
export const getAchievements = callable<[appid: number, steamAppid: number],
  { ok: true; files: number; progress: Record<string, AchievementState> } | Fail>("get_achievements");

export interface StoreDetails {
  name?: string;
  short_description?: string;
  about_the_game?: string;
  developers?: string[];
  publishers?: string[];
  genres?: { id: string; description: string }[];
  categories?: { id: number; description: string }[];
  metacritic?: { score: number; url: string };
  supported_languages?: string;
  website?: string | null;
  release_date?: { coming_soon: boolean; date: string };
  achievements?: { total: number };
  controller_support?: string;
}

export interface AchievementDef {
  name: string; title: string; desc: string; icon: string; icon_gray: string; hidden: boolean; pct: number;
}

// Where `icon`/`icon_gray` live: `${ACHIEVEMENT_ICON_BASE}/<steam appid>/<file>`. The older
// cdn.akamai/cdn.cloudflare "steamcommunity/public/images/apps" path 404s for newer games (e.g. 3624140).
export const ACHIEVEMENT_ICON_BASE = "https://shared.fastly.steamstatic.com/community_assets/images/apps";

export const storeDetails = callable<[steamAppid: number, lang: string], { ok: true; details: StoreDetails } | Fail>("store_details");
export const achievementSchema = callable<[steamAppid: number, lang: string], { ok: true; achievements: AchievementDef[] } | Fail>("achievement_schema");
export const pollAchievements = callable<[appid: number, steamAppid: number],
  { ok: true; new: ({ name: string } & AchievementState)[]; baseline?: number } | Fail>("poll_achievements");
export const stopAchievements = callable<[appid: number], { ok: true }>("stop_achievements");
