// Small shared state for the side panel and the game pages, with a React hook.
import { useEffect, useState } from "react";
import type { DepsState, GameRecord, Settings } from "./backend";

export interface LogLine { t: number; text: string; level: "info" | "warn" | "error" }

export interface PluginState {
  settings: Settings | null;
  games: Record<string, GameRecord>;
  upscaler: boolean;
  deps: DepsState;
  busy: string | null;           // what "Update library" is doing right now
  libResult: string | null;      // how the last library update ended
  artBusy: string | null;        // what the artwork check is doing right now
  artResult: string | null;      // how the last artwork check ended
  lastScan: number | null;
  attention: { title: string; root: string; reason: string }[];
  artQueue: number;              // images waiting to be upscaled
  artDone: number;
  log: LogLine[];
}

let state: PluginState = {
  settings: null, games: {}, upscaler: false, deps: { status: "missing", error: "" }, busy: null, libResult: null, artBusy: null, artResult: null, lastScan: null, attention: [], artQueue: 0, artDone: 0, log: [],
};
const listeners = new Set<() => void>();

export function getPluginState(): PluginState {
  return state;
}

export function update(patch: Partial<PluginState>) {
  state = { ...state, ...patch };
  listeners.forEach((l) => l());
}

export function log(text: string, level: LogLine["level"] = "info") {
  const line = { t: Date.now(), text, level };
  (level === "error" ? console.error : console.log)("[Custom Games]", text);
  update({ log: [line, ...state.log].slice(0, 40) });
}

export function usePluginState(): PluginState {
  const [, set] = useState(0);
  useEffect(() => {
    const l = () => set((n) => n + 1);
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  }, []);
  return state;
}

export function gameFor(appid: number): GameRecord | null {
  const g = state.games[String(appid >>> 0)];
  return g && g.steam_appid ? g : null;
}
