"use client";

import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";
import { messages, type Locale, type Messages } from "./messages";
import { usePref } from "./pref";

type Ctx = { locale: Locale; t: Messages; setLocale: (l: Locale) => void; f: (s: string, vars: Record<string, string | number>) => string };

const I18nContext = createContext<Ctx | null>(null);
const LOCALES = ["tr", "en"] as const;

export function format(s: string, vars: Record<string, string | number>): string {
  return s.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? `{${k}}`));
}

export function I18nProvider({ children, initial = "tr" }: { children: ReactNode; initial?: Locale }) {
  const [locale, setLocale] = usePref<Locale>("kavra.locale", initial, LOCALES);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo(() => ({ locale, t: messages[locale], setLocale, f: format }), [locale, setLocale]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n outside I18nProvider");
  return ctx;
}
