// UI language: English, or Russian when the Steam client itself runs in Russian.
import { language } from "./steam";

export function isRussian(): boolean {
  return language().toLowerCase().startsWith("ru");
}

/** The text in the UI language. */
export function t(en: string, ru: string): string {
  return isRussian() ? ru : en;
}
