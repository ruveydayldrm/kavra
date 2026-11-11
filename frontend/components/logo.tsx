import { cn } from "@/lib/utils";

/** Kavra mark: three widening arcs = growing review intervals, the dot = the idea you grasp. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-7", className)} aria-hidden>
      <rect width="32" height="32" rx="9" fill="var(--accent)" />
      <g fill="none" stroke="var(--accent-ink)" strokeLinecap="round" strokeWidth="2.4">
        <path d="M10 22a4 4 0 0 1 4-4" />
        <path d="M10 22a8 8 0 0 1 8-8" opacity=".8" />
        <path d="M10 22a12.5 12.5 0 0 1 12.5-12.5" opacity=".6" />
      </g>
      <circle cx="10" cy="22" r="2.4" fill="var(--amber)" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark />
      <span className="font-display text-[1.35rem] leading-none tracking-tight text-ink">Kavra</span>
    </span>
  );
}
