"use client";

import { Timer } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ExamReportView, ExamRunner } from "@/components/exam-runner";
import { Button } from "@/components/ui/button";
import { Card, PageHeader, SectionTitle, Skeleton } from "@/components/ui/primitives";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { api, type Exam, type ExamReport } from "@/lib/api";
import { useQuery } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import { cn, pct } from "@/lib/utils";

const COUNTS = [10, 20, 40];
const MINUTES = [10, 20, 45];

function ExamSetup({ onStart }: { onStart: (e: Exam) => void }) {
  const { t, locale } = useI18n();
  const sp = useSearchParams();
  const preDoc = Number(sp.get("doc")) || null;
  const docs = useQuery(api.documents, []);
  const history = useQuery(api.exams, []);
  const [count, setCount] = useState(20);
  const [minutes, setMinutes] = useState(20);
  const [selected, setSelected] = useState<number[]>(preDoc ? [preDoc] : []);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (docs.error) return <ErrorState error={docs.error} onRetry={docs.reload} />;
  if (!docs.data) return <Skeleton className="h-80 rounded-[var(--radius-lg)]" />;
  const ready = docs.data.filter((d) => d.questions > 0);
  if (!ready.length)
    return (
      <EmptyState
        icon={<Timer className="size-9" strokeWidth={1.4} />}
        title={t.exam.noQuestions}
        action={
          <Button asChild>
            <Link href="/library">{t.nav.library}</Link>
          </Button>
        }
      />
    );

  async function start() {
    setBusy(true);
    setErr(null);
    try {
      onStart(await api.newExam({ count, minutes, document_ids: selected.length ? selected : undefined }));
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  }

  const dateFmt = new Intl.DateTimeFormat(locale === "tr" ? "tr-TR" : "en-US", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

  return (
    <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1fr_280px]">
      <Card className="p-5 sm:p-6">
        <Choice label={t.exam.count} options={COUNTS} value={count} onChange={setCount} suffix={t.common.questions} />
        <Choice label={t.exam.duration} options={MINUTES} value={minutes} onChange={setMinutes} suffix={t.common.minutes} />
        <fieldset className="mt-6">
          <legend className="eyebrow mb-2">{t.exam.materials}</legend>
          <div className="flex flex-wrap gap-2">
            <Pill active={!selected.length} onClick={() => setSelected([])}>
              {t.exam.all}
            </Pill>
            {ready.map((d) => (
              <Pill key={d.id} active={selected.includes(d.id)} onClick={() => setSelected((s) => (s.includes(d.id) ? s.filter((x) => x !== d.id) : [...s, d.id]))}>
                <span className="max-w-[16rem] truncate">{d.title}</span>
                <span className="tabular text-ink-3">{d.questions}</span>
              </Pill>
            ))}
          </div>
        </fieldset>
        {err && <p className="mt-4 text-sm text-danger-ink">{err}</p>}
        <Button size="lg" className="mt-8 w-full sm:w-auto" onClick={start} disabled={busy}>
          <Timer /> {t.exam.start}
        </Button>
      </Card>
      <aside>
        <SectionTitle>{t.exam.history}</SectionTitle>
        {!history.data?.length ? (
          <p className="text-sm text-ink-3">—</p>
        ) : (
          <ul className="divide-y divide-border rounded-[var(--radius-lg)] border border-border bg-surface">
            {history.data.slice(0, 8).map((h) => (
              <li key={h.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                <span className="tabular text-ink-2">{dateFmt.format(new Date(h.started_at * 1000))}</span>
                <span className="tabular font-medium text-ink">{h.ratio === null ? "—" : pct(h.ratio)}</span>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}

function Choice({ label, options, value, onChange, suffix }: { label: string; options: number[]; value: number; onChange: (n: number) => void; suffix: string }) {
  return (
    <fieldset className="mt-6 first:mt-0">
      <legend className="eyebrow mb-2">{label}</legend>
      <div role="radiogroup" className="grid grid-cols-3 gap-2">
        {options.map((o) => (
          <button
            key={o}
            role="radio"
            aria-checked={value === o}
            onClick={() => onChange(o)}
            className={cn(
              "flex h-16 flex-col items-center justify-center rounded-[var(--radius-md)] border border-border bg-surface transition-colors hover:border-border-strong",
              value === o && "border-accent bg-accent-soft/60 ring-2 ring-accent/20",
            )}
          >
            <span className="tabular font-display text-xl text-ink">{o}</span>
            <span className="text-xs text-ink-3">{suffix}</span>
          </button>
        ))}
      </div>
    </fieldset>
  );
}

function Pill({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={cn("inline-flex h-8 items-center gap-2 rounded-full border border-border bg-surface px-3 text-sm text-ink-2 hover:border-border-strong", active && "border-accent bg-accent-soft text-ink")}
    >
      {children}
    </button>
  );
}

function ExamFlow() {
  const { t } = useI18n();
  const [exam, setExam] = useState<Exam | null>(null);
  const [report, setReport] = useState<ExamReport | null>(null);
  if (report) return <ExamReportView report={report} onNew={() => (setReport(null), setExam(null))} />;
  if (exam) return <ExamRunner exam={exam} onDone={setReport} />;
  return (
    <>
      <PageHeader title={t.exam.title} subtitle={t.exam.subtitle} />
      <ExamSetup onStart={setExam} />
    </>
  );
}

export default function ExamPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 rounded-[var(--radius-lg)]" />}>
      <ExamFlow />
    </Suspense>
  );
}
