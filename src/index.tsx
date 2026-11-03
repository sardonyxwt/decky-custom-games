import {
  ButtonItem, DialogButton, Field, Focusable, PanelSection, PanelSectionRow, Spinner, staticClasses, TextField, ToggleField,
} from "@decky/ui";
import { definePlugin } from "@decky/api";
import { useState } from "react";
import { FaCheckCircle, FaExclamationTriangle, FaLayerGroup, FaSpinner } from "react-icons/fa";
import * as be from "./backend";
import { followDeps, installDeps, loadState, refreshLibrary, runArtQueue, startWatcher, stopWatcher } from "./library";
import { openMapping } from "./modals";
import { patchLibraryApp, unpatchLibraryApp } from "./pagePatch";
import { watchAchievements } from "./achievementWatch";
import { getPluginState, log, update, usePluginState } from "./state";
import { allShortcuts } from "./steam";
import { t } from "./i18n";

/** Button text: a spinner and what is going on while busy (the button is disabled then), else its normal label. */
function BusyLabel({ busy, idle }: { busy: string | null; idle: string }) {
  if (!busy) return <>{idle}</>;
  return (
    <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10, minWidth: 0 }}>
      <Spinner style={{ width: 20, height: 20, flex: "none" }} />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{busy}</span>
    </span>
  );
}

function ago(time: number | null): string {
  if (!time) return t("not yet", "ещё не было");
  const m = Math.round((Date.now() - time) / 60000);
  return m < 1 ? t("just now", "только что") : m < 60 ? t(`${m} min ago`, `${m} мин назад`)
    : t(`${Math.round(m / 60)} h ago`, `${Math.round(m / 60)} ч назад`);
}

async function setSetting(key: string, value: unknown) {
  const r = await be.setSetting(key, value);
  if (r.ok) update({ settings: r.settings, games: r.games, upscaler: r.upscaler });
  else log(t(`Setting ${key}: ${r.error}`, `Настройка ${key}: ${r.error}`), "error");
}

function LibrarySection() {
  const st = usePluginState();
  // Apps such as a browser or a launcher are shortcuts too, but not games.
  const shortcuts = allShortcuts().filter((s) => st.games[String(s.appid)]?.appid_source !== "not_a_game");
  const unlinked = shortcuts.filter((s) => {
    const g = st.games[String(s.appid)];
    return g && !g.steam_appid && g.appid_source !== "not_a_game" && g.appid_source !== "manual";
  });
  const linked = shortcuts.filter((s) => st.games[String(s.appid)]?.steam_appid).length;
  return (
    <PanelSection title={t("Library", "Библиотека")}>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={!!st.busy} onClick={() => refreshLibrary()} description={st.busy ? undefined : st.libResult}>
          <BusyLabel busy={st.busy} idle={t("Update library", "Обновить библиотеку")} />
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field label={t("Last check", "Проверка")} description={t(`Non-Steam games: ${shortcuts.length}, with Steam data: ${linked}`,
          `Сторонних игр: ${shortcuts.length}, с данными Steam: ${linked}`)}>
          {ago(st.lastScan)}
        </Field>
      </PanelSectionRow>
      {st.attention.map((a) => (
        <PanelSectionRow key={a.root + a.reason}>
          <Field label={a.title} description={a.reason} />
        </PanelSectionRow>
      ))}
      {!!unlinked.length && (
        <PanelSectionRow>
          <Field label={t("No Steam data", "Без данных Steam")} description={t("Press to pick the game on Steam", "Нажмите, чтобы выбрать игру в Steam")} />
        </PanelSectionRow>
      )}
      {unlinked.map((s) => (
        <PanelSectionRow key={s.appid}>
          <ButtonItem layout="below" onClick={() => openMapping(s.appid, s.name)}>{s.name}</ButtonItem>
        </PanelSectionRow>
      ))}
    </PanelSection>
  );
}

const DEPS_BADGE = {
  ready: { icon: <FaCheckCircle />, text: () => t("Ready", "Готово"), color: "#59bf40" },
  installing: { icon: <FaSpinner />, text: () => t("Downloading", "Скачиваются"), color: "#dcdedf" },
  missing: { icon: <FaSpinner />, text: () => t("Waiting", "Ожидание"), color: "#8b929a" },
  error: { icon: <FaExclamationTriangle />, text: () => t("Error", "Ошибка"), color: "#e57373" },
};

function DepsBadge({ status }: { status: be.DepsState["status"] }) {
  const b = DEPS_BADGE[status];
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 6, color: b.color, whiteSpace: "nowrap", fontSize: 15 }}>
      {b.icon}{b.text()}
    </span>
  );
}

function ArtworkSection() {
  const st = usePluginState();
  const s = st.settings;
  if (!s) return null;
  const deps = st.deps;
  const depsText = deps.status === "ready" ? t("Installed", "Установлены")
    : deps.status === "installing" ? t("Downloading (about 45 MB)…", "Скачиваются (около 45 МБ)…")
    : deps.status === "error" ? t(`Error: ${deps.error}`, `Ошибка: ${deps.error}`) : t("Not installed yet", "Ещё не установлены");
  return (
    <PanelSection title={t("Artwork", "Обложки")}>
      <PanelSectionRow>
        <Field label={t("Dependencies", "Зависимости")} description={t("The upscayl-bin upscaler (Real-ESRGAN on the GPU) and two models",
          "Апскейлер upscayl-bin (Real-ESRGAN на видеокарте) и две модели")}>
          <DepsBadge status={deps.status} />
        </Field>
      </PanelSectionRow>
      {deps.status !== "ready" && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={deps.status === "installing"} onClick={() => installDeps()}
            description={depsText}>
            {deps.status === "installing" ? t("Installing…", "Устанавливаются…") : t("Install dependencies", "Установить зависимости")}
          </ButtonItem>
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <Field label={t("Queue", "Очередь")} description={t("Worked on while no game is running", "Обрабатывается, пока игра не запущена")}>
          {st.artQueue ? t(`${st.artQueue} left`, `осталось ${st.artQueue}`) : t(`${st.artDone} done`, `готово ${st.artDone}`)}
        </Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label={t("Keep artwork at the right size", "Приводить обложки к нужному размеру")}
          description={t("Small images are upscaled on the GPU, big ones scaled down", "Маленькие увеличиваются на видеокарте, большие уменьшаются")}
          checked={s.upscale} onChange={(v) => setSetting("upscale", v)} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label={t("Steam games too", "И у игр из Steam")} description={t("Images set by hand or with the SteamGridDB plugin", "Картинки, поставленные вручную или плагином SteamGridDB")}
          checked={s.upscale_steam_games} onChange={(v) => setSetting("upscale_steam_games", v)} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label={t("Artwork for new games", "Обложки для новых игр")} description={t("The game's official images from Steam", "Официальные картинки игры из Steam")}
          checked={s.art_new_games} onChange={(v) => setSetting("art_new_games", v)} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={!!st.artBusy} onClick={() => runArtQueue(true)}
          description={st.artBusy ? undefined : st.artResult}>
          <BusyLabel busy={st.artBusy} idle={t("Check artwork now", "Проверить обложки сейчас")} />
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

const SQUARE = { width: 40, minWidth: 40, height: 40, padding: 0, fontSize: 22, lineHeight: "40px", flex: "none" };

function SettingsSection() {
  const st = usePluginState();
  const s = st.settings;
  const [dir, setDir] = useState("");
  if (!s) return null;
  const add = () => {
    if (dir.trim()) void setSetting("game_dirs", [...s.game_dirs, dir.trim()]);
    setDir("");
  };
  return (
    <PanelSection title={t("Settings", "Настройки")}>
      <PanelSectionRow>
        <div className={staticClasses.Text} style={{ fontSize: 14, color: "#dcdedf", marginBottom: 4 }}>{t("Game folders", "Папки с играми")}</div>
      </PanelSectionRow>
      {s.game_dirs.map((d) => (
        <PanelSectionRow key={d}>
          <Focusable style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0" }} flow-children="row">
            {/* right-to-left so a long path is cut at its start; the LRM mark keeps the slashes in place */}
            <div style={{ flex: 1, minWidth: 0, fontSize: 14, color: "#b8bcbf", overflow: "hidden", textOverflow: "ellipsis",
              whiteSpace: "nowrap", direction: "rtl", textAlign: "left" }} title={d}>{"\u200E" + d + "\u200E"}</div>
            <DialogButton style={SQUARE} onClick={() => setSetting("game_dirs", s.game_dirs.filter((x) => x !== d))}>−</DialogButton>
          </Focusable>
        </PanelSectionRow>
      ))}
      <PanelSectionRow>
        <Focusable style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0" }} flow-children="row">
          <div style={{ flex: 1, minWidth: 0 }}>
            <TextField value={dir} onChange={(e) => setDir(e.target.value)} />
          </div>
          <DialogButton style={SQUARE} onClick={add}>+</DialogButton>
        </Focusable>
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label={t("Games from Anker Launcher", "Игры из Anker Launcher")} description={t("Take games and their launch options from the Anker library", "Брать игры и их параметры запуска из библиотеки Anker")}
          checked={s.anker} onChange={(v) => setSetting("anker", v)} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label={t("Look for new games when Steam starts", "Искать новые игры при запуске Steam")} checked={s.scan_on_start}
          onChange={(v) => setSetting("scan_on_start", v)} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label={t("Store texts in Russian", "Тексты Steam на русском")} description={t("Description, genres and achievements; otherwise in Steam's language", "Описание, жанры и достижения; иначе на языке Steam")}
          checked={s.data_lang === "russian"} onChange={(v) => setSetting("data_lang", v ? "russian" : "")} />
      </PanelSectionRow>
    </PanelSection>
  );
}

function Content() {
  return (
    <>
      <LibrarySection />
      <ArtworkSection />
      <SettingsSection />
    </>
  );
}

export default definePlugin(() => {
  const patch = patchLibraryApp();
  const stopAchievements = watchAchievements();
  let startTimer: number | null = window.setTimeout(async () => {
    startTimer = null;
    await loadState();
    if (getPluginState().settings?.scan_on_start) {
      await refreshLibrary();
    } else {
      const r = await be.resolveGames(false);
      if (r.ok) update({ games: r.games });
      void runArtQueue();
    }
    startWatcher();
  }, 15_000); // let Steam finish starting first
  void loadState().then(() => followDeps());
  return {
    name: "Custom Games",
    titleView: <div className={staticClasses.Title}>Custom Games</div>,
    content: <Content />,
    icon: <FaLayerGroup />,
    onDismount() {
      if (startTimer !== null) window.clearTimeout(startTimer);
      stopWatcher();
      stopAchievements();
      unpatchLibraryApp(patch);
    },
  };
});
