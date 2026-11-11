"use client";

import { AlertTriangle, WifiOff } from "lucide-react";
import type { ReactNode } from "react";
import { ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { Button } from "./button";

export function EmptyState({
  icon,
  title,
  body,
  action,
  className,
}: {
  icon?: ReactNode;
  title: ReactNode;
  body?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center rounded-[var(--radius-xl)] border border-dashed border-border-strong px-6 py-14 text-center", className)}>
      {icon && <div className="mb-5 text-accent">{icon}</div>}
      <h3 className="font-display text-xl text-ink">{title}</h3>
      {body && <p className="mt-2 max-w-md text-sm text-ink-2">{body}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry, className }: { error: Error; onRetry?: () => void; className?: string }) {
  const { t } = useI18n();
  const offline = error instanceof ApiError && error.status === 0;
  return (
    <div role="alert" className={cn("flex flex-col items-center gap-3 rounded-[var(--radius-lg)] border border-danger/30 bg-danger-soft px-6 py-10 text-center", className)}>
      {offline ? <WifiOff className="size-6 text-danger-ink" /> : <AlertTriangle className="size-6 text-danger-ink" />}
      <div>
        <p className="font-medium text-ink">{offline ? t.common.offline : t.common.error}</p>
        {!offline && <p className="mt-1 text-sm text-ink-2">{error.message}</p>}
      </div>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          {t.common.retry}
        </Button>
      )}
    </div>
  );
}
