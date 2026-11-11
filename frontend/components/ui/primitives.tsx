import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("rounded-[var(--radius-lg)] border border-border bg-surface shadow-sm", className)} {...props} />;
}

export function Badge({ className, tone = "neutral", ...props }: ComponentProps<"span"> & { tone?: "neutral" | "accent" | "amber" | "danger" }) {
  const tones = {
    neutral: "bg-surface-2 text-ink-2 border-border",
    accent: "bg-accent-soft text-accent border-accent-line/60 dark:text-accent",
    amber: "bg-amber-soft text-amber-ink border-amber/40",
    danger: "bg-danger-soft text-danger-ink border-danger/30",
  } as const;
  return (
    <span
      className={cn("inline-flex h-6 items-center gap-1 rounded-full border px-2.5 text-xs font-medium whitespace-nowrap [&_svg]:size-3.5", tones[tone], className)}
      {...props}
    />
  );
}

export function Kbd({ className, ...props }: ComponentProps<"kbd">) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded-[5px] border border-border border-b-2 bg-surface px-1 font-mono text-[11px] leading-none text-ink-2",
        className,
      )}
      {...props}
    />
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("skeleton", className)} />;
}

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="font-display text-3xl text-ink sm:text-4xl">{title}</h1>
        {subtitle && <p className="mt-2 max-w-prose text-ink-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
    </header>
  );
}

export function SectionTitle({ children, hint, action }: { children: ReactNode; hint?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-3">
      <div className="flex items-baseline gap-2">
        <h2 className="text-sm font-semibold text-ink">{children}</h2>
        {hint && <span className="text-xs text-ink-3">{hint}</span>}
      </div>
      {action}
    </div>
  );
}
