"use client";

import { ExternalLink, MapPin, PlayCircle } from "lucide-react";
import type { Source } from "@/lib/api";
import { fileUrl } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { locLabel, splitHighlight } from "@/lib/utils";
import { Button } from "./ui/button";
import { Dialog } from "./ui/dialog";

export function SourceLabel({ source }: { source: Source }) {
  const { t } = useI18n();
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5 text-xs text-ink-3">
      <MapPin className="size-3.5 shrink-0" />
      <span className="truncate">{source.document.title}</span>
      <span aria-hidden>·</span>
      <span className="tabular shrink-0">{locLabel(source.loc, t.loc)}</span>
    </span>
  );
}

export function SourceSheet({ source, open, onOpenChange }: { source: Source | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const { t } = useI18n();
  if (!source) return null;
  const parts = source.context ? splitHighlight(source.context, source.quote) : null;
  const href = fileUrl(source.url);
  const isVideo = source.loc.kind === "time";

  return (
    <Dialog open={open} onOpenChange={onOpenChange} side="right" title={t.study.sourceTitle} description={<SourceLabel source={source} />} closeLabel={t.common.close}>
      <figure>
        <blockquote className="rounded-[var(--radius-md)] border-l-[3px] border-amber bg-amber-soft/60 px-4 py-3 font-display text-lg leading-relaxed text-ink">
          “{source.quote}”
        </blockquote>
        {source.context && (
          <div className="mt-5">
            <p className="mb-2 text-xs font-semibold text-ink-3">{source.document.title}</p>
            <p className="whitespace-pre-line text-sm leading-relaxed text-ink-2">
              {parts ? (
                <>
                  {parts[0]}
                  <mark className="src">{parts[1]}</mark>
                  {parts[2]}
                </>
              ) : (
                source.context
              )}
            </p>
          </div>
        )}
      </figure>
      {href && (
        <div className="sticky bottom-0 -mx-5 -mb-4 mt-6 border-t border-border bg-surface px-5 py-3">
          <Button asChild variant="secondary" className="w-full">
            <a href={href} target="_blank" rel="noreferrer">
              {isVideo ? <PlayCircle /> : <ExternalLink />}
              {isVideo ? t.study.watchAt : t.study.openOriginal}
            </a>
          </Button>
        </div>
      )}
    </Dialog>
  );
}
