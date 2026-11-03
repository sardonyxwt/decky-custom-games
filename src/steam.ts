// Thin, defensive wrappers around Steam client globals available to Decky plugins.
import type { LogoPosition } from "./backend";

declare const SteamClient: any;
declare const appStore: any;
declare const appDetailsStore: any;
declare const collectionStore: any;
declare const StoreItemCache: any;
declare const SteamUIStore: any;

export const NON_STEAM_APP_TYPE = 1073741824;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function isShortcut(appid: number): boolean {
  return appid >= 0x80000000;
}

export function gameRunning(): boolean {
  try {
    return (SteamUIStore?.RunningApps?.length ?? 0) > 0;
  } catch (_) {
    return false;
  }
}

export function overview(appid: number): any {
  try {
    return appStore?.GetAppOverviewByAppID?.(appid) ?? null;
  } catch (_) {
    return null;
  }
}

/**
 * Adds a non-Steam game while Steam runs: it shows up at once and Steam saves shortcuts.vdf itself.
 * AddShortcut quotes the exe on its own, mangles a quoted start dir and names the entry after the exe,
 * so the Set* calls afterwards write everything in the usual form ("path" in quotes, the real name).
 */
export async function addShortcut(name: string, exe: string, startDir: string, launchOptions: string,
  compatTool: string): Promise<number> {
  const id: number = await SteamClient.Apps.AddShortcut(name, exe, startDir, launchOptions);
  if (!id) throw new Error("Steam не вернул appid");
  SteamClient.Apps.SetShortcutName(id, name);
  SteamClient.Apps.SetShortcutExe(id, `"${exe}"`);
  SteamClient.Apps.SetShortcutStartDir(id, `"${startDir}"`);
  SteamClient.Apps.SetShortcutLaunchOptions(id, launchOptions || "");
  if (compatTool && exe.toLowerCase().endsWith(".exe")) SteamClient.Apps.SpecifyCompatTool(id, compatTool);
  await sleep(300);
  return id >>> 0;
}

/**
 * Sets one library image through Steam, which writes it into userdata/<user>/config/grid and shows it at once.
 * Clearing first removes the other-extension variants (a leftover .png would otherwise sit next to a new .jpg).
 */
export async function setArtwork(appid: number, base64: string, format: "jpg" | "png", assetType: number) {
  await SteamClient.Apps.ClearCustomArtworkForApp(appid, assetType);
  await sleep(500); // ClearCustomArtworkForApp resolves before the file is gone
  await SteamClient.Apps.SetCustomArtworkForApp(appid, base64, format, assetType);
  await sleep(300);
}

export async function ensureLogoPosition(appid: number, pos: LogoPosition | null) {
  const ov = overview(appid);
  if (!ov || !appDetailsStore?.SaveCustomLogoPosition) return;
  let current = null;
  try {
    current = appDetailsStore.GetCustomLogoPosition?.(ov) ?? null;
  } catch (_) {
    /* none yet */
  }
  // Shortcuts need a position file, or Steam draws no logo at all.
  if (!current || pos) {
    await appDetailsStore.SaveCustomLogoPosition(ov, pos ?? { pinnedPosition: "BottomLeft", nWidthPct: 50, nHeightPct: 50 });
  }
}

export function setShortcutIcon(appid: number, path: string) {
  SteamClient.Apps.SetShortcutIcon(appid, path);
}

/** Official name and asset links of a Steam game, from the client's own store cache (no key needed). */
export async function storeItem(steamAppid: number, opts: Record<string, boolean | number> = {}): Promise<any | null> {
  if (!steamAppid || typeof StoreItemCache === "undefined") return null;
  try {
    await StoreItemCache.QueueAppRequest(steamAppid, {
      include_basic_info: true, include_assets: true, include_release: true, include_reviews: true,
      include_platforms: true, include_tag_count: 12, include_screenshots: true, include_trailers: true,
      include_full_description: true, include_supported_languages: true, include_ratings: true, ...opts,
    });
    return StoreItemCache.GetApp(steamAppid) ?? null;
  } catch (e) {
    console.warn("[Custom Games] store data failed", steamAppid, e);
    return null;
  }
}

export function storeAssets(item: any): Record<string, string> {
  const a = item?.m_Assets ?? {};
  const out: Record<string, string> = {};
  if (a.m_strLibraryCapsuleURL_2x || a.m_strLibraryCapsuleURL) out.portrait = a.m_strLibraryCapsuleURL_2x || a.m_strLibraryCapsuleURL;
  if (a.m_strLibraryHeroURL_2x || a.m_strLibraryHeroURL) out.hero = a.m_strLibraryHeroURL_2x || a.m_strLibraryHeroURL;
  if (a.m_strHeaderURL) out.wide = a.m_strHeaderURL;
  if (a.m_strCommunityIcon_Full) out.icon = a.m_strCommunityIcon_Full;
  return out;
}

export function storeName(item: any): string | null {
  try {
    return item?.GetName?.() || item?.m_strName || null;
  } catch (_) {
    return null;
  }
}

export function allShortcuts(): { appid: number; name: string }[] {
  try {
    return [...collectionStore.allAppsCollection.allApps]
      .filter((a: any) => a.app_type === NON_STEAM_APP_TYPE)
      .map((a: any) => ({ appid: a.appid >>> 0, name: a.display_name }));
  } catch (_) {
    return [];
  }
}

export function language(): string {
  try {
    const l = (window as any).LocalizationManager?.m_rgLocalesToUse?.[0];
    if (typeof l === "string") return l;
  } catch (_) {
    /* ignore */
  }
  return "en";
}
