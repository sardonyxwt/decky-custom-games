import { DialogButton, Focusable, ModalRoot, Navigation, showModal, TextField } from "@decky/ui";
import Hls from "hls.js/dist/hls.light.mjs";
import { useEffect, useRef, useState } from "react";
import * as be from "./backend";
import { log, update } from "./state";
import { Styles } from "./styles";

/** Pick the Steam game a non-Steam shortcut is, by searching the store. */
function MappingModal({ appid, title, closeModal }: { appid: number; title: string; closeModal?: () => void }) {
  const [term, setTerm] = useState(title);
  const [items, setItems] = useState<{ id: number; name: string; image: string }[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const search = async (t: string) => {
    setItems(null);
    setError(null);
    const r = await be.searchStore(t);
    if (r.ok) setItems(r.items);
    else setError(r.error);
  };
  useEffect(() => {
    void search(title);
  }, []);

  const choose = async (steamAppid: number, name: string) => {
    const r = await be.setMapping(appid, steamAppid);
    if (r.ok) {
      update({ games: r.games });
      log(steamAppid ? `«${title}» привязана к Steam: ${name} (${steamAppid})` : `«${title}»: привязка к Steam убрана`);
    }
    closeModal?.();
  };

  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <div style={{ fontSize: 22, color: "#fff", marginBottom: 12 }}>Какая это игра в Steam?</div>
      <div className="cg-dim" style={{ marginBottom: 12 }}>«{title}» — данные, новости и достижения возьмутся у выбранной игры.</div>
      <Focusable style={{ display: "flex", gap: 10, alignItems: "center" }} flow-children="row">
        <div style={{ flex: 1 }}>
          <TextField value={term} onChange={(e) => setTerm(e.target.value)} />
        </div>
        <DialogButton style={{ width: "auto", minWidth: 0, padding: "0 20px" }} onClick={() => search(term)}>Найти</DialogButton>
      </Focusable>
      <div style={{ marginTop: 12, maxHeight: "50vh", overflowY: "auto" }}>
        {error && <div className="cg-dim">Ошибка поиска: {error}</div>}
        {!items && !error && <div className="cg-dim">Ищу…</div>}
        {items && !items.length && <div className="cg-dim">Ничего не найдено. Попробуйте другое название.</div>}
        {items?.map((it) => (
          <Focusable key={it.id} className="cg-card cg-search-row" onActivate={() => choose(it.id, it.name)}
            onClick={() => choose(it.id, it.name)}>
            {it.image && <img src={it.image} />}
            <div style={{ flex: 1, color: "#fff", fontSize: 17 }}>{it.name}</div>
            <div className="cg-dim">{it.id}</div>
          </Focusable>
        ))}
      </div>
      <Focusable style={{ display: "flex", gap: 10, marginTop: 14 }} flow-children="row">
        <DialogButton onClick={() => choose(0, "")}>Это не игра из Steam</DialogButton>
        <DialogButton onClick={closeModal}>Отмена</DialogButton>
      </Focusable>
    </ModalRoot>
  );
}

export function openMapping(appid: number, title: string) {
  showModal(<MappingModal appid={appid} title={title} />);
}

export interface ViewerItem { src: string; video?: boolean; poster?: string; fallback?: string }

/**
 * Steam serves trailers as HLS (.m3u8), which Chromium does not play by itself; hls.js feeds it to the video
 * element through Media Source Extensions (the browser plays the H.264 inside). Plain files play directly.
 */
function Video({ item, onFail }: { item: ViewerItem; onFail: () => void }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    if (!/\.m3u8(\?|$)/.test(item.src)) {
      v.src = item.src;
      return;
    }
    if (!Hls.isSupported()) {
      onFail();
      return;
    }
    const hls = new Hls({ capLevelToPlayerSize: true });
    hls.on(Hls.Events.ERROR, (_e: any, data: any) => {
      if (data?.fatal) onFail();
    });
    hls.loadSource(item.src);
    hls.attachMedia(v);
    return () => hls.destroy();
  }, [item.src]);
  return <video ref={ref} poster={item.poster} controls autoPlay onError={onFail} />;
}

function ViewerModal({ items, start, closeModal }: { items: ViewerItem[]; start: number; closeModal?: () => void }) {
  const [i, setI] = useState(start);
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const it = items[i];
  const go = (d: number) => {
    setFailed(false);
    setLoaded(false);
    setI((i + d + items.length) % items.length);
  };
  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal} bAllowFullSize modalClassName="cg-wide-modal">
      <Styles />
      <div className="cg-viewer">
        {/* fixed 16:9 stage: the dialog keeps its size while a picture or video loads */}
        <div className="cg-stage">
          {it.video && !failed && <Video key={it.src} item={it} onFail={() => setFailed(true)} />}
          {!it.video && (
            <img key={it.src} src={it.src} onLoad={() => setLoaded(true)} style={{ opacity: loaded ? 1 : 0 }} />
          )}
          {!it.video && !loaded && <div className="cg-stage-note">Загрузка…</div>}
          {it.video && failed && <div className="cg-stage-note">Не удалось воспроизвести видео.</div>}
        </div>
        <Focusable className="cg-viewer-buttons" flow-children="row">
          {items.length > 1 && <DialogButton className="cg-btn" onClick={() => go(-1)}>‹ Назад</DialogButton>}
          {items.length > 1 && <DialogButton className="cg-btn" onClick={() => go(1)}>Дальше ›</DialogButton>}
          {it.fallback && (
            <DialogButton className="cg-btn" onClick={() => { closeModal?.(); openUrl(it.fallback!); }}>Открыть в магазине</DialogButton>
          )}
          <DialogButton className="cg-btn" onClick={closeModal}>Закрыть</DialogButton>
        </Focusable>
        {items.length > 1 && <div className="cg-dim">{i + 1} / {items.length}</div>}
      </div>
    </ModalRoot>
  );
}

export function openViewer(items: ViewerItem[], start: number) {
  showModal(<ViewerModal items={items} start={start} />);
}

export function openUrl(url: string) {
  Navigation.NavigateToExternalWeb(url);
}
