"use client";

import { ArrowLeft, ChevronDown, Play, ShieldCheck, Timer } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { useLiveJob } from "@/components/doc-row";
import { SourceLabel, SourceSheet } from "@/components/source-sheet";
import { Button } from "@/components/ui/button";
import { Badge, Card, PageHeader, SectionTitle, Skeleton } from "@/components/ui/primitives";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { Bar, MasteryMap } from "@/components/viz";
import { api, type DocDetail, type FullQuestion, type Source } from "@/lib/api";
import { useQuery } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import { cn, pct } from "@/lib/utils";

export default function DocumentPage() {
  const { id } = useParams<{ id: string }>();
  const docId = Number(id);
  const { t } = useI18n();
  const router = useRouter();
  const doc = useQuery(() => api.document(docId), [docId]);
  const qs = useQuery(() => api.questions(docId), [docId]);
  const [source, setSource] = useState<Source | null>(null);

  if (doc.error) return <ErrorState error={doc.error} onRetry={doc.reload} />;
  if (doc.loading || !doc.data) return <Skeleton className="h-96 rounded-[var(--radius-lg)]" />;
  const d = doc.data;

  return (
    <>
      <Link href="/library" className="mb-4 inline-flex items-center gap-1.5 text-sm text-ink-3 hover:text-ink">
        <ArrowLeft className="size-4" /> {t.library.title}
      </Link>
      <PageHeader
        title={d.title}
        subtitle={
          <span className="tabular">
            {d.questions} {t.common.questions} · {d.topics} {t.common.topics} · {d.lang.toUpperCase()}
          </span>
        }
        actions={
          d.questions > 0 && (
            <>
              <Button variant="secondary" onClick={() => router.push(`/exam?doc=${d.id}`)}>
                <Timer /> {t.doc.examDoc}
              </Button>
              <Button onClick={() => router.push(`/study?doc=${d.id}`)}>
                <Play /> {t.doc.studyDoc}
              </Button>
            </>
          )
        }
      />
      <LiveStatus doc={d} onDone={() => (doc.reload(), qs.reload())} />

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1fr_300px]">
        <section>
          <SectionTitle>{t.doc.topics}</SectionTitle>
          {d.topic_list.length ? (
            <MasteryMap topics={d.topic_list} onPick={(tp) => router.push(`/study?topic=${tp.id}`)} />
          ) : (
            <Skeleton className="h-24" />
          )}
        </section>
        <PipelineCard doc={d} />
      </div>

      <section className="mt-10">
        <SectionTitle hint={qs.data ? String(qs.data.length) : undefined}>{t.doc.questionsTitle}</SectionTitle>
        {qs.error ? (
          <ErrorState error={qs.error} onRetry={qs.reload} />
        ) : !qs.data ? (
          <Skeleton className="h-40" />
        ) : qs.data.length === 0 ? (
          <EmptyState title={t.doc.noQuestions} />
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-[var(--radius-lg)] border border-border bg-surface">
            {qs.data.map((q) => (
              <QuestionRow key={q.id} q={q} onSource={() => setSource(q.source)} />
            ))}
          </ul>
        )}
      </section>
      <SourceSheet source={source} open={!!source} onOpenChange={(o) => !o && setSource(null)} />
    </>
  );
}

function LiveStatus({ doc, onDone }: { doc: DocDetail; onDone: () => void }) {
  const { t } = useI18n();
  const job = useLiveJob(doc, onDone);
  if (!job) return null;
  const stage = job.stage as keyof typeof t.library.stage;
  return (
    <Card className="mb-8 p-4">
      <div className="mb-2 flex justify-between text-sm">
        <span className="text-ink-2">{t.library.stage[stage] ?? t.library.status.processing}</span>
        <span className="tabular text-ink-3">{job.stage === "questions" ? job.message : pct(job.progress)}</span>
      </div>
      <Bar value={job.progress} />
    </Card>
  );
}

function PipelineCard({ doc }: { doc: DocDetail }) {
  const { t } = useI18n();
  const q = doc.quality;
  const rejected = Object.entries(q.rejected).sort((a, b) => b[1] - a[1]);
  const total = q.candidates || 1;
  return (
    <Card className="h-fit p-5">
      <div className="mb-4 flex items-center gap-2">
        <ShieldCheck className="size-4 text-accent" />
        <h2 className="text-sm font-semibold">{t.doc.pipeline}</h2>
      </div>
      <dl className="space-y-3 text-sm">
        <Row label={t.doc.generated} value={q.candidates} />
        <Row label={t.doc.kept} value={q.kept} accent />
        {q.repaired > 0 && <Row label={t.doc.repaired} value={q.repaired} />}
      </dl>
      <Bar value={q.kept / total} className="my-4" />
      {rejected.length > 0 && (
        <>
          <p className="eyebrow mb-2">{t.doc.rejectedBy}</p>
          <dl className="space-y-1.5 text-sm">
            {rejected.map(([stage, n]) => (
              <Row key={stage} label={t.doc.stage[stage as keyof typeof t.doc.stage] ?? stage} value={n} muted />
            ))}
          </dl>
        </>
      )}
    </Card>
  );
}

function Row({ label, value, accent, muted }: { label: string; value: number; accent?: boolean; muted?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className={cn("text-ink-2", muted && "text-ink-3")}>{label}</dt>
      <dd className={cn("tabular font-medium", accent ? "text-accent" : "text-ink", muted && "font-normal text-ink-2")}>{value}</dd>
    </div>
  );
}

function QuestionRow({ q, onSource }: { q: FullQuestion; onSource: () => void }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  return (
    <li>
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full items-start gap-3 px-4 py-3.5 text-left hover:bg-surface-2/60 sm:px-5">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap gap-1.5">
            <Badge>{t.study.type[q.type]}</Badge>
            <Badge tone={q.difficulty === "hard" ? "danger" : q.difficulty === "easy" ? "accent" : "amber"}>{t.study.difficulty[q.difficulty]}</Badge>
          </div>
          <p className="text-sm text-ink">{q.stem}</p>
        </div>
        <ChevronDown className={cn("mt-1 size-4 shrink-0 text-ink-3 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-3 px-4 pb-4 text-sm sm:px-5">
          {q.type === "mcq" && (
            <ol className="space-y-1">
              {q.options.map((o, i) => (
                <li key={i} className={cn("flex gap-2 text-ink-2", i === q.correct_index && "font-medium text-accent")}>
                  <span className="tabular w-4 text-ink-3">{i + 1}</span> {o}
                </li>
              ))}
            </ol>
          )}
          {q.type !== "mcq" && (
            <p>
              <span className="text-ink-3">{t.study.correctAnswer}: </span>
              <span className="font-medium text-ink">{q.type === "tf" ? (q.answer === "true" ? t.study.true : t.study.false) : q.answer}</span>
            </p>
          )}
          <p className="text-ink-2">{q.explanation}</p>
          <button onClick={onSource} className="flex w-full min-w-0 items-center rounded-[var(--radius-sm)] text-left hover:text-ink">
            <SourceLabel source={q.source} />
          </button>
        </div>
      )}
    </li>
  );
}
