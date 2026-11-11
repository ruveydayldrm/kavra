"use client";

import { motion } from "motion/react";
import { Flame } from "lucide-react";
import { useMemo, useState } from "react";
import type { HeatDay, TopicMastery } from "@/lib/api";
import { useReducedMotion } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import { cn, pct } from "@/lib/utils";

/* ───────────── Progress ring ───────────── */
export function ProgressRing({
  value,
  size = 120,
  stroke = 10,
  label,
  sublabel,
  tone = "accent",
}: {
  value: number;
  size?: number;
  stroke?: number;
  label?: React.ReactNode;
  sublabel?: React.ReactNode;
  tone?: "accent" | "amber";
}) {
  const reduced = useReducedMotion();
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(1, value));
  return (
    <div className="relative inline-grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={stroke} />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={tone === "accent" ? "var(--accent)" : "var(--amber)"}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: reduced ? c * (1 - v) : c }}
          animate={{ strokeDashoffset: c * (1 - v) }}
          transition={{ duration: reduced ? 0 : 0.9, ease: [0.22, 1, 0.36, 1] }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          {label && <div className="tabular font-display text-2xl leading-none text-ink">{label}</div>}
          {sublabel && <div className="mt-1 text-xs text-ink-3">{sublabel}</div>}
        </div>
      </div>
    </div>
  );
}

/* ───────────── GitHub-style heatmap ───────────── */
function level(n: number): number {
  if (n === 0) return 0;
  if (n < 5) return 1;
  if (n < 15) return 2;
  if (n < 30) return 3;
  return 4;
}

export function Heatmap({ days }: { days: HeatDay[] }) {
  const { t, f, locale } = useI18n();
  const [hover, setHover] = useState<HeatDay | null>(null);
  const weeks = useMemo(() => {
    if (!days.length) return [];
    const first = new Date(days[0].date + "T00:00:00");
    const pad = (first.getDay() + 6) % 7; // Monday-first
    const cells: (HeatDay | null)[] = [...Array(pad).fill(null), ...days];
    const out: (HeatDay | null)[][] = [];
    for (let i = 0; i < cells.length; i += 7) out.push(cells.slice(i, i + 7));
    return out;
  }, [days]);
  const fmt = new Intl.DateTimeFormat(locale === "tr" ? "tr-TR" : "en-US", { day: "numeric", month: "short" });
  const total = days.reduce((s, d) => s + d.count, 0);

  return (
    <div>
      <div className="overflow-x-auto pb-1 [scrollbar-width:thin]" dir="rtl">
        <div dir="ltr" className="inline-flex gap-[3px]" role="img" aria-label={`${t.today.activity}: ${total}`}>
          {weeks.map((w, wi) => (
            <div key={wi} className="flex flex-col gap-[3px]">
              {w.map((d, di) =>
                d ? (
                  <div
                    key={di}
                    onMouseEnter={() => setHover(d)}
                    onMouseLeave={() => setHover(null)}
                    className="size-[11px] rounded-[3px] ring-inset transition-transform hover:scale-125 hover:ring-1 hover:ring-ink/30"
                    style={{ background: `var(--heat-${level(d.count)})` }}
                    title={f(t.today.reviewsOn, { date: fmt.format(new Date(d.date + "T00:00:00")), n: d.count })}
                  />
                ) : (
                  <div key={di} className="size-[11px]" />
                ),
              )}
            </div>
          ))}
        </div>
      </div>
      <div className="mt-2 flex items-center justify-between text-xs text-ink-3">
        <span className="tabular min-h-4">
          {hover ? f(t.today.reviewsOn, { date: fmt.format(new Date(hover.date + "T00:00:00")), n: hover.count }) : ""}
        </span>
        <span className="flex items-center gap-1">
          {t.today.less}
          {[0, 1, 2, 3, 4].map((l) => (
            <span key={l} className="size-[10px] rounded-[3px]" style={{ background: `var(--heat-${l})` }} />
          ))}
          {t.today.more}
        </span>
      </div>
    </div>
  );
}

/* ───────────── Streak ───────────── */
export function Streak({ current, best, active }: { current: number; best: number; active: boolean }) {
  const { t, f } = useI18n();
  const reduced = useReducedMotion();
  return (
    <div className="flex items-center gap-3">
      <motion.div
        className={cn("grid size-11 place-items-center rounded-full", active ? "bg-amber-soft text-amber-ink" : "bg-surface-2 text-ink-3")}
        animate={active && !reduced ? { scale: [1, 1.08, 1] } : undefined}
        transition={{ duration: 1.2, repeat: 0 }}
      >
        <Flame className="size-5" fill={active ? "currentColor" : "none"} fillOpacity={0.25} />
      </motion.div>
      <div>
        <div className="flex items-baseline gap-1.5">
          <span className="tabular font-display text-2xl leading-none text-ink">{current}</span>
          <span className="text-sm text-ink-2">{t.today.streak}</span>
        </div>
        <div className="mt-1 text-xs text-ink-3">{f(t.today.bestStreak, { n: best })}</div>
      </div>
    </div>
  );
}

/* ───────────── Mastery map ───────────── */
export function masteryColor(m: number, seen: number): string {
  if (!seen) return "var(--heat-0)";
  if (m < 0.25) return "var(--heat-1)";
  if (m < 0.5) return "var(--heat-2)";
  if (m < 0.75) return "var(--heat-3)";
  return "var(--heat-4)";
}

export function MasteryMap({ topics, onPick }: { topics: TopicMastery[]; onPick?: (t: TopicMastery) => void }) {
  const { t, f } = useI18n();
  return (
    <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {topics.map((tp) => (
        <li key={tp.id}>
          <button
            type="button"
            onClick={() => onPick?.(tp)}
            className="group flex w-full items-center gap-3 rounded-[var(--radius-md)] border border-border bg-surface p-3 text-left transition-colors hover:border-border-strong hover:bg-surface-2"
          >
            <span
              aria-hidden
              className="relative size-9 shrink-0 overflow-hidden rounded-[8px] border border-border"
              style={{ background: "var(--heat-0)" }}
            >
              <span
                className="absolute inset-x-0 bottom-0 transition-[height] duration-700"
                style={{ height: `${Math.max(tp.seen ? 8 : 0, tp.mastery * 100)}%`, background: masteryColor(tp.mastery, tp.seen) }}
              />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-ink">{tp.title}</span>
              <span className="tabular block text-xs text-ink-3">
                {f(t.doc.seen, { seen: tp.seen, total: tp.total })}
                {tp.accuracy !== null && ` · ${pct(tp.accuracy)} ${t.today.accuracy}`}
              </span>
            </span>
            <span className="tabular text-sm font-medium text-ink-2">{pct(tp.mastery)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/* ───────────── Thin bar ───────────── */
export function Bar({ value, tone = "accent", className }: { value: number; tone?: "accent" | "amber" | "danger"; className?: string }) {
  const color = { accent: "var(--accent)", amber: "var(--amber)", danger: "var(--danger)" }[tone];
  return (
    <div className={cn("h-1.5 overflow-hidden rounded-full bg-surface-3", className)}>
      <div className="h-full rounded-full transition-[width] duration-500 ease-out" style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%`, background: color }} />
    </div>
  );
}
