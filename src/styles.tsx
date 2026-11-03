// Styles for the injected tab contents, close to Steam's own game page (dark glass cards, light text).
// Rendered as a <style> element by the components themselves: the game page lives in Big Picture's own
// window, whose document is not the one the plugin's script runs in.
export const CSS = `
.cg-tab { padding: 8px 0 32px; color: #dcdedf; }
.cg-h2 { font-size: 26px; color: #fff; margin: 12px 0 18px; font-weight: 400; }
.cg-h3 { font-size: 20px; color: #fff; margin: 26px 0 12px; font-weight: 400; display: flex; align-items: center; gap: 14px; }
.cg-h3::after { content: ""; flex: 1; height: 1px; background: rgba(255,255,255,0.1); }
.cg-dim { color: #8b929a; }
.cg-day { display: flex; align-items: center; gap: 12px; margin: 26px 14px 8px; color: #8b929a; font-size: 18px;
  letter-spacing: 2px; text-transform: uppercase; }
.cg-day::after { content: ""; flex: 1; height: 1px; background: rgba(255,255,255,0.1); }
.cg-card { background: rgba(61,68,80,0.45); border-radius: 8px; transition: background 120ms, box-shadow 120ms; }
.cg-card.gpfocus, .cg-card:hover { background: rgba(91,100,115,0.65); box-shadow: 0 0 0 2px rgba(255,255,255,0.75); }
.cg-news { display: flex; gap: 20px; padding: 16px; margin-bottom: 14px; cursor: pointer; }
.cg-news-img { flex: none; width: 368px; height: 207px; border-radius: 6px; background: #1b2028 center/cover no-repeat; }
.cg-news-body { min-width: 0; display: flex; flex-direction: column; gap: 8px; padding-top: 2px; }
.cg-news-type { color: #8b929a; font-size: 15px; text-transform: uppercase; letter-spacing: 0.5px; }
.cg-news-title { color: #fff; font-size: 23px; line-height: 1.25; }
.cg-news-sum { color: #8b929a; font-size: 16px; line-height: 1.5; overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 3; -webkit-box-orient: vertical; max-width: 1100px; }
.cg-news-meta { color: #8b929a; font-size: 14px; margin-top: auto; display: flex; gap: 18px; }
.cg-info-top { display: flex; gap: 22px; align-items: stretch; }
.cg-cover { flex: none; width: 226px; height: 339px; border-radius: 6px; object-fit: cover; background: #1b2028; }
.cg-info-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 14px; }
.cg-desc { font-size: 21px; line-height: 1.45; color: #dcdedf; }
.cg-rows { margin-top: auto; display: grid; grid-template-columns: max-content 1fr; gap: 4px 10px; font-size: 16px; }
.cg-rows > :nth-child(odd) { color: #8b929a; }
.cg-features { flex: none; width: 260px; display: flex; flex-direction: column; gap: 10px; font-size: 16px; color: #8b929a; }
.cg-feature { display: flex; align-items: center; gap: 12px; }
.cg-good { color: #66c0f4; }
.cg-line { margin-top: 14px; font-size: 16px; color: #8b929a; line-height: 1.5; }
.cg-line b { color: #dcdedf; font-weight: 600; }
.cg-buttons { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 24px; }
.cg-buttons .DialogButton, .cg-btn { width: auto !important; min-width: 0 !important; min-height: 44px; padding: 0 28px !important;
  display: flex !important; align-items: center; justify-content: center; white-space: nowrap; flex: none; }
.cg-para { font-size: 18px; line-height: 1.55; color: #c6cbd1; padding: 4px 8px; border-radius: 6px; }
.cg-para.gpfocus { background: rgba(255,255,255,0.06); }
.cg-para.cg-head { color: #fff; font-size: 20px; margin-top: 10px; }
.cg-bar { height: 8px; border-radius: 4px; background: rgba(255,255,255,0.12); overflow: hidden; margin: 6px 0 18px; }
.cg-bar > div { height: 100%; background: linear-gradient(90deg, #47bfff, #1a44c2); }
.cg-ach-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(520px, 1fr)); gap: 10px; }
.cg-ach { display: flex; gap: 16px; align-items: center; padding: 12px; }
.cg-ach img { width: 64px; height: 64px; border-radius: 4px; flex: none; }
.cg-ach-text { min-width: 0; flex: 1; }
.cg-ach-title { color: #fff; font-size: 18px; }
.cg-ach-desc { color: #8b929a; font-size: 15px; line-height: 1.35; }
.cg-ach-side { color: #8b929a; font-size: 14px; text-align: right; flex: none; max-width: 160px; }
.cg-locked .cg-ach-title { color: #b8bcbf; }
.cg-achday { padding: 14px 16px; margin-bottom: 14px; }
.cg-achday-head { color: #8b929a; font-size: 15px; text-transform: uppercase; letter-spacing: 0.5px; display: flex;
  align-items: center; gap: 8px; margin-bottom: 10px; }
.cg-achday-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 10px 18px; }
.cg-achday-item { display: flex; gap: 14px; align-items: center; }
.cg-achday-item img { width: 56px; height: 56px; border-radius: 4px; flex: none; }
.cg-media { display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 14px; }
.cg-shot { position: relative; aspect-ratio: 16 / 9; border-radius: 6px; overflow: hidden; cursor: pointer;
  background: #1b2028 center/cover no-repeat; }
.cg-shot video { width: 100%; height: 100%; object-fit: cover; display: block; }
.cg-shot-label { position: absolute; left: 0; right: 0; bottom: 0; padding: 26px 14px 10px; font-size: 16px; color: #fff;
  background: linear-gradient(transparent, rgba(0,0,0,0.8)); }
.cg-mapping { margin-top: 30px; padding: 14px 16px; display: flex; align-items: center; gap: 16px; font-size: 15px; color: #8b929a; }
.cg-mapping > span { flex: 1; }
/* Steam's dialog is 660 px wide; the viewer gets most of the screen (DialogContent* are Steam's stable classes) */
.cg-wide-modal { max-width: none !important; }
.cg-wide-modal .DialogContent { width: min(88vw, calc(64vh * 16 / 9 + 88px)) !important; max-width: none !important; }
.cg-wide-modal .DialogContent_InnerWidth { width: 100% !important; max-width: none !important; }
.cg-viewer { display: flex; flex-direction: column; align-items: center; gap: 14px; width: 100%; }
.cg-stage { position: relative; width: 100%; aspect-ratio: 16 / 9; background: #000;
  border-radius: 6px; overflow: hidden; display: flex; align-items: center; justify-content: center; }
.cg-stage img, .cg-stage video { width: 100%; height: 100%; object-fit: contain; display: block; transition: opacity 150ms; }
.cg-stage-note { position: absolute; color: #8b929a; font-size: 16px; }
.cg-viewer-buttons { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; max-width: 100%; }
.cg-search-row { display: flex; align-items: center; gap: 14px; padding: 8px 10px; margin: 4px 0; cursor: pointer; }
.cg-search-row img { width: 120px; height: 45px; object-fit: cover; border-radius: 3px; flex: none; }
`;

export function Styles() {
  return <style>{CSS}</style>;
}
