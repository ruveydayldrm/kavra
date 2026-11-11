"use client";

import { AlertCircle, FileImage, FileText, Loader2, MonitorPlay, Play, Presentation, RotateCw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, jobEvents, type Doc, type Job } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";
import { Badge } from "./ui/primitives";
import { Bar } from "./viz";

const ICONS = { pdf: FileText, docx: FileText, text: FileText, pptx: Presentation, image: FileImage, youtube: MonitorPlay } as const;

export function useLiveJob(doc: Doc, onDone: () => void): Job | null {
  const [job, setJob] = useState<Job | null>(doc.job);
  const active = doc.status === "queued" || doc.status === "processing";
  const jobId = doc.job?.id;
  useEffect(() => {
    if (!active || !jobId) return;
    return jobEvents(jobId, (j) => {
      setJob(j);
      if (j.status === "done" || j.status === "failed") onDone();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, jobId]);
  return active ? job : null;
}

export function DocRow({ doc, onChange }: { doc: Doc; onChange: () => void }) {
  const { t } = useI18n();
  const job = useLiveJob(doc, onChange);
  const Icon = ICONS[doc.kind] ?? FileText;
  const busy = doc.status === "queued" || doc.status === "processing";
  const stage = job?.stage as keyof typeof t.library.stage | undefined;
  const stageLabel = stage && t.library.stage[stage] ? t.library.stage[stage] : t.library.status[doc.status];
  const step = job?.stage === "questions" && job.message ? ` · ${job.message}` : "";

  async function remove() {
    if (!window.confirm(t.library.deleteConfirm)) return;
    await api.deleteDocument(doc.id);
    onChange();
  }

  return (
    <li className="group relative flex items-center gap-4 px-4 py-4 sm:px-5">
      <div className={cn("grid size-10 shrink-0 place-items-center rounded-[var(--radius-md)] bg-surface-2 text-ink-2", doc.status === "ready" && "bg-accent-soft text-accent")}>
        <Icon className="size-[18px]" />
      </div>
      <div className="min-w-0 flex-1">
        <Link href={`/library/${doc.id}`} className="block truncate font-medium text-ink after:absolute after:inset-0 hover:underline focus-visible:outline-none">
          {doc.title}
        </Link>
        {busy ? (
          <div className="mt-1.5 max-w-sm">
            <div className="mb-1 flex items-center gap-1.5 text-xs text-ink-2">
              <Loader2 className="size-3 animate-spin" />
              <span className="tabular truncate">
                {stageLabel}
                {step}
              </span>
            </div>
            <Bar value={job?.progress ?? 0.02} />
          </div>
        ) : (
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-ink-3">
            <span className="tabular">
              {doc.questions} {t.common.questions} · {doc.topics} {t.common.topics}
            </span>
            <span aria-hidden>·</span>
            <span className="uppercase">{doc.lang}</span>
          </div>
        )}
        {doc.status === "partial" && <p className="mt-1.5 max-w-lg text-xs text-amber-ink">{t.library.resumeHint}</p>}
        {doc.status === "failed" && doc.error && (
          <p className="mt-1.5 flex max-w-lg items-start gap-1 text-xs text-danger-ink">
            <AlertCircle className="mt-0.5 size-3 shrink-0" /> <span className="line-clamp-2">{doc.error}</span>
          </p>
        )}
      </div>
      <div className="relative z-10 flex items-center gap-1">
        {doc.status === "ready" && <Badge tone="accent">{t.library.status.ready}</Badge>}
        {doc.status === "partial" && <Badge tone="amber">{t.library.status.partial}</Badge>}
        {doc.status === "failed" && <Badge tone="danger">{t.library.status.failed}</Badge>}
        {(doc.status === "partial" || doc.status === "failed") && (
          <Button
            variant="ghost"
            size="icon"
            aria-label={t.library.resume}
            title={t.library.resume}
            onClick={async () => {
              await api.resume(doc.id);
              onChange();
            }}
          >
            <RotateCw />
          </Button>
        )}
        {doc.questions > 0 && (
          <Button asChild variant="ghost" size="icon" aria-label={t.doc.studyDoc} title={t.doc.studyDoc}>
            <Link href={`/study?doc=${doc.id}`}>
              <Play />
            </Link>
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon"
          aria-label={t.common.delete}
          title={t.common.delete}
          onClick={remove}
          className="opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100"
        >
          <Trash2 />
        </Button>
      </div>
    </li>
  );
}
