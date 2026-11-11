"use client";

import { createContext, useContext, useEffect, type ReactNode } from "react";
import { usePref, useSystemDark } from "./pref";

export type ThemePref = "light" | "dark" | "system";
type Ctx = { theme: ThemePref; resolved: "light" | "dark"; setTheme: (t: ThemePref) => void };

const ThemeContext = createContext<Ctx | null>(null);
const THEMES = ["light", "dark", "system"] as const;

/** Inline script run before paint so the page never flashes the wrong theme. */
export const themeScript = `(function(){try{var t=localStorage.getItem('kavra.theme')||'system';var d=t==='dark'||(t==='system'&&matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.classList.toggle('dark',d);}catch(e){}})();`;

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = usePref<ThemePref>("kavra.theme", "system", THEMES);
  const systemDark = useSystemDark();
  const resolved = theme === "system" ? (systemDark ? "dark" : "light") : theme;

  useEffect(() => {
    document.documentElement.classList.toggle("dark", resolved === "dark");
  }, [resolved]);

  return <ThemeContext.Provider value={{ theme, resolved, setTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Ctx {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme outside ThemeProvider");
  return ctx;
}
