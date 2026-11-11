"use client";

import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  side = "center",
  closeLabel = "Close",
  className,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  side?: "center" | "right";
  closeLabel?: string;
  className?: string;
}) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-[oklch(0.2_0.02_70/0.35)] backdrop-blur-[2px] data-[state=open]:animate-[fade-in_150ms_ease-out]" />
        <D.Content
          className={cn(
            "fixed z-50 flex flex-col border border-border bg-surface shadow-lg focus:outline-none",
            side === "center"
              ? "inset-x-3 bottom-3 max-h-[85dvh] rounded-[var(--radius-xl)] sm:inset-x-auto sm:bottom-auto sm:left-1/2 sm:top-1/2 sm:w-[min(32rem,calc(100vw-2rem))] sm:-translate-x-1/2 sm:-translate-y-1/2 data-[state=open]:animate-[pop-in_180ms_var(--ease-out-soft)]"
              : "inset-x-0 bottom-0 max-h-[88dvh] rounded-t-[var(--radius-xl)] sm:inset-y-0 sm:left-auto sm:right-0 sm:max-h-none sm:w-[min(36rem,100vw)] sm:rounded-none sm:rounded-l-[var(--radius-xl)] data-[state=open]:animate-[slide-in_220ms_var(--ease-out-soft)]",
            className,
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
            <div>
              <D.Title className="text-base font-semibold text-ink">{title}</D.Title>
              {description ? (
                <D.Description className="mt-1 text-sm text-ink-2">{description}</D.Description>
              ) : (
                <D.Description className="sr-only">{title}</D.Description>
              )}
            </div>
            <D.Close aria-label={closeLabel} className="-mr-1 rounded-[var(--radius-sm)] p-1 text-ink-3 hover:bg-surface-2 hover:text-ink">
              <X className="size-4" />
            </D.Close>
          </div>
          <div className="overflow-y-auto px-5 py-4">{children}</div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
