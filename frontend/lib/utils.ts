import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Locator } from "./api";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmtTime(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}` : `${m}:${String(r).padStart(2, "0")}`;
}

export function pct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

type LocLabels = { page: string; line: string; slide: string; para: string; image: string };

export function locLabel(loc: Locator, l: LocLabels): string {
  switch (loc.kind) {
    case "page": {
      const pages = loc.page_end && loc.page_end !== loc.page ? `${loc.page}–${loc.page_end}` : `${loc.page}`;
      const lines = loc.line_start === loc.line_end ? `${loc.line_start}` : `${loc.line_start}–${loc.line_end}`;
      return `${l.page} ${pages} · ${l.line} ${lines}`;
    }
    case "slide":
      return `${l.slide} ${loc.slide}${loc.slide_end ? `–${loc.slide_end}` : ""}`;
    case "para":
      return `${l.para} ${loc.para}${loc.para_end ? `–${loc.para_end}` : ""}`;
    case "image":
      return `${l.image} · ${l.line} ${loc.line_start}–${loc.line_end}`;
    case "time":
      return `${fmtTime(loc.start ?? 0)} – ${fmtTime(loc.end ?? 0)}`;
  }
}

/** Highlight `quote` inside `context` (case-insensitive, whitespace tolerant). */
export function splitHighlight(context: string, quote: string): [string, string, string] | null {
  const idx = context.indexOf(quote);
  if (idx >= 0) return [context.slice(0, idx), quote, context.slice(idx + quote.length)];
  const lower = context.toLocaleLowerCase("tr");
  const q = quote.toLocaleLowerCase("tr").trim();
  const i2 = lower.indexOf(q);
  if (i2 >= 0) return [context.slice(0, i2), context.slice(i2, i2 + q.length), context.slice(i2 + q.length)];
  return null;
}

export function relativeDue(ts: number | null, now: number, rtf: Intl.RelativeTimeFormat): string | null {
  if (!ts) return null;
  const diff = ts - now / 1000;
  const abs = Math.abs(diff);
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86400), "day");
}
