"use client";

import { BarChart3, BookOpen, Home, Keyboard, Layers, Monitor, Moon, Settings, Sun, Timer } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { useHotkeys } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import { useTheme, type ThemePref } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { Logo, LogoMark } from "./logo";
import { ShortcutsDialog } from "./shortcuts";

const NAV = [
  { href: "/", key: "today", icon: Home },
  { href: "/library", key: "library", icon: BookOpen },
  { href: "/study", key: "study", icon: Layers },
  { href: "/exam", key: "exam", icon: Timer },
  { href: "/insights", key: "insights", icon: BarChart3 },
] as const;

function isActive(path: string, href: string) {
  return href === "/" ? path === "/" : path.startsWith(href);
}

export function ThemeSwitch({ compact = false }: { compact?: boolean }) {
  const { theme, setTheme } = useTheme();
  const { t } = useI18n();
  const opts: { v: ThemePref; icon: typeof Sun; label: string }[] = [
    { v: "light", icon: Sun, label: t.common.light },
    { v: "dark", icon: Moon, label: t.common.dark },
    { v: "system", icon: Monitor, label: t.common.system },
  ];
  return (
    <div role="radiogroup" aria-label={t.common.theme} className="inline-flex rounded-[var(--radius-md)] border border-border bg-surface-2 p-0.5">
      {opts.map(({ v, icon: Icon, label }) => (
        <button
          key={v}
          role="radio"
          aria-checked={theme === v}
          aria-label={label}
          title={label}
          onClick={() => setTheme(v)}
          className={cn(
            "inline-flex h-7 items-center gap-1.5 rounded-[7px] px-2 text-xs text-ink-3 transition-colors hover:text-ink",
            theme === v && "bg-surface text-ink shadow-sm",
          )}
        >
          <Icon className="size-3.5" />
          {!compact && <span>{label}</span>}
        </button>
      ))}
    </div>
  );
}

export function LangSwitch() {
  const { locale, setLocale, t } = useI18n();
  return (
    <div role="radiogroup" aria-label={t.common.language} className="inline-flex rounded-[var(--radius-md)] border border-border bg-surface-2 p-0.5">
      {(["tr", "en"] as const).map((l) => (
        <button
          key={l}
          role="radio"
          aria-checked={locale === l}
          onClick={() => setLocale(l)}
          className={cn("h-7 rounded-[7px] px-2.5 text-xs font-medium uppercase text-ink-3 hover:text-ink", locale === l && "bg-surface text-ink shadow-sm")}
        >
          {l}
        </button>
      ))}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const { t } = useI18n();
  const [help, setHelp] = useState(false);
  useHotkeys((e) => {
    if (e.key === "?") {
      e.preventDefault();
      setHelp((h) => !h);
    }
  });
  const focusMode = path.startsWith("/study") || /^\/exam\/\d+/.test(path);

  return (
    <div className="min-h-dvh">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-border bg-bg/80 px-3 py-5 backdrop-blur lg:flex">
        <Link href="/" className="mb-8 px-2">
          <Logo />
        </Link>
        <nav aria-label={t.nav.main} className="flex flex-col gap-0.5">
          {NAV.map(({ href, key, icon: Icon }) => {
            const active = isActive(path, href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex h-9 items-center gap-3 rounded-[var(--radius-md)] px-2.5 text-sm text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink",
                  active && "bg-surface text-ink shadow-sm ring-1 ring-border",
                )}
              >
                <Icon className={cn("size-4", active && "text-accent")} />
                {t.nav[key]}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto flex flex-col gap-3 px-1">
          <Link
            href="/settings"
            aria-current={path.startsWith("/settings") ? "page" : undefined}
            className={cn("flex h-9 items-center gap-3 rounded-[var(--radius-md)] px-1.5 text-sm text-ink-2 hover:text-ink", path.startsWith("/settings") && "text-ink")}
          >
            <Settings className="size-4" />
            {t.nav.settings}
          </Link>
          <button onClick={() => setHelp(true)} className="flex h-9 items-center gap-3 rounded-[var(--radius-md)] px-1.5 text-sm text-ink-2 hover:text-ink">
            <Keyboard className="size-4" />
            {t.common.shortcuts}
            <span className="ml-auto rounded border border-border px-1.5 font-mono text-[11px] text-ink-3">?</span>
          </button>
          <div className="flex items-center justify-between gap-2">
            <ThemeSwitch compact />
            <LangSwitch />
          </div>
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-bg/85 px-4 backdrop-blur lg:hidden">
        <Link href="/" aria-label="Kavra">
          <span className="inline-flex items-center gap-2">
            <LogoMark className="size-7" />
            <span className="font-display text-lg text-ink">Kavra</span>
          </span>
        </Link>
        <Link href="/settings" aria-label={t.nav.settings} className="grid size-9 place-items-center rounded-[var(--radius-md)] text-ink-2 hover:bg-surface-2">
          <Settings className="size-[18px]" />
        </Link>
      </header>

      <main id="main" className={cn("lg:pl-60", !focusMode && "pb-24 lg:pb-0")}>
        <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 sm:py-10 lg:px-10">{children}</div>
      </main>

      {/* Mobile tab bar */}
      {!focusMode && (
        <nav
          aria-label={t.nav.main}
          className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-border bg-bg/90 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
        >
          {NAV.map(({ href, key, icon: Icon }) => {
            const active = isActive(path, href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn("flex h-16 flex-col items-center justify-center gap-1 text-[11px] text-ink-3", active && "text-accent")}
              >
                <Icon className="size-5" strokeWidth={active ? 2.2 : 1.8} />
                {t.nav[key]}
              </Link>
            );
          })}
        </nav>
      )}

      <ShortcutsDialog open={help} onOpenChange={setHelp} />
    </div>
  );
}
