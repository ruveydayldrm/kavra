"use client";

import { motion } from "motion/react";
import { ArrowLeft, ArrowRight, Bookmark, CheckCircle2, Clock, MinusCircle, XCircle } from "lucide-react";
import { useCallback, useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import { api, type Exam, type ExamReport } from "@/lib/api";
import { useHotkeys } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import { cn, fmtTime, pct } from "@/lib/utils";
import { isAnswered, QuestionInput, Stem, type Response } from "./question-input";
import { SourceLabel, SourceSheet } from "./source-sheet";
import { Button } from "./ui/button";
import { Badge, Card, SectionTitle } from "./ui/primitives";
import { Bar, ProgressRing } from "./viz";
import type { Source } from "@/lib/api";

export function ExamRunner({ exam, onDone }: { exam: Exam; onDone: (r: ExamReport) => void }) {
  const { t, f } = useI18n();
  const [i, setI] = useState(0);
  const [answers, setAnswers] = useState<Record<number, Response>>({});
  const [marked, setMarked] = useState<Set<number>>(new Set());
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [endAt] = useState(() => Date.now() + exam.minutes * 60_000);
  const submitted = useRef(false);
  const q = exam.questions[i];
  const remaining = Math.max(0, (endAt - now) / 1000);
  const answeredCount = exam.questions.filter((x) => isAnswered(x, answers[x.id] ?? null)).length;

  const submit = useCallback(async () => {
    if (submitted.current) return;
    submitted.current = true;
    setBusy(true);
    const payload: Record<string, unknown> = {};
    for (const x of exam.questions) if (isAnswered(x, answers[x.id] ?? null)) payload[String(x.id)] = answers[x.id];
    try {
      onDone(await api.submitExam(exam.id, payload));
    } catch {
      submitted.current = false;
      setBusy(false);
    }
  }, [answers, exam, onDone]);

  const onTick = useEffectEvent(() => {
    const t = Date.now();
    setNow(t);
    if (t >= endAt) void submit();
  });
  useEffect(() => {
    const id = setInterval(() => onTick(), 1000);
    return () => clearInterval(id);
  }, []);

  useHotkeys(
    (e) => {
      if (q.type === "mcq" && /^[1-4]$/.test(e.key)) setAnswers((a) => ({ ...a, [q.id]: Number(e.key) - 1 }));
      if (q.type === "tf" && /^[tdTD]$/.test(e.key)) setAnswers((a) => ({ ...a, [q.id]: true }));
      if (q.type === "tf" && /^[fyFY]$/.test(e.key)) setAnswers((a) => ({ ...a, [q.id]: false }));
      if (e.key === "ArrowRight" || e.key === "Enter") setI((x) => Math.min(exam.questions.length - 1, x + 1));
      if (e.key === "ArrowLeft") setI((x) => Math.max(0, x - 1));
    },
  );

  function finish() {
    const empty = exam.questions.length - answeredCount;
    if (empty > 0 && !window.confirm(f(t.exam.confirmFinish, { n: empty }))) return;
    void submit();
  }

  const low = remaining < 60;
  return (
    <div className="mx-auto max-w-3xl">
      <div className="sticky top-14 z-20 -mx-4 mb-5 flex items-center gap-3 border-b border-border bg-bg/90 px-4 py-3 backdrop-blur sm:top-0 lg:-mx-10 lg:px-10">
        <div className={cn("tabular flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-medium", low ? "border-danger/40 bg-danger-soft text-danger-ink" : "border-border bg-surface text-ink")} role="timer" aria-label={t.exam.remaining}>
          <Clock className="size-4" /> {fmtTime(remaining)}
        </div>
        <Bar value={answeredCount / exam.questions.length} className="flex-1" />
        <span className="tabular text-sm text-ink-3">
          {answeredCount}/{exam.questions.length}
        </span>
        <Button size="sm" onClick={finish} disabled={busy}>
          {t.exam.finish}
        </Button>
      </div>

      <nav aria-label={t.exam.title} className="mb-5 flex flex-wrap gap-1.5">
        {exam.questions.map((x, n) => (
          <button
            key={x.id}
            onClick={() => setI(n)}
            aria-current={n === i ? "step" : undefined}
            aria-label={f(t.exam.questionN, { n: n + 1 })}
            className={cn(
              "tabular relative grid size-8 place-items-center rounded-[7px] border text-xs font-medium transition-colors",
              n === i ? "border-ink bg-ink text-bg" : isAnswered(x, answers[x.id] ?? null) ? "border-accent-line bg-accent-soft text-accent" : "border-border bg-surface text-ink-3 hover:border-border-strong",
            )}
          >
            {n + 1}
            {marked.has(x.id) && <span className="absolute -right-0.5 -top-0.5 size-2 rounded-full bg-amber" />}
          </button>
        ))}
      </nav>

      <motion.div key={q.id} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.18 }}>
        <Card className="p-5 sm:p-7">
          <div className="mb-4 flex items-center justify-between gap-2">
            <span className="eyebrow">{f(t.exam.questionN, { n: i + 1 })}</span>
            <button
              onClick={() => setMarked((m) => (m.has(q.id) ? new Set([...m].filter((x) => x !== q.id)) : new Set(m).add(q.id)))}
              aria-pressed={marked.has(q.id)}
              className={cn("inline-flex items-center gap-1 text-xs text-ink-3 hover:text-ink", marked.has(q.id) && "text-amber-ink")}
            >
              <Bookmark className="size-3.5" fill={marked.has(q.id) ? "currentColor" : "none"} /> {t.exam.flagForReview}
            </button>
          </div>
          <Stem q={q} className="mb-6 font-display text-xl leading-snug text-ink sm:text-2xl" />
          <QuestionInput q={q} value={answers[q.id] ?? null} onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))} />
        </Card>
      </motion.div>

      <div className="mt-4 flex justify-between">
        <Button variant="ghost" onClick={() => setI((x) => Math.max(0, x - 1))} disabled={i === 0}>
          <ArrowLeft /> {t.common.back}
        </Button>
        {i < exam.questions.length - 1 ? (
          <Button variant="secondary" onClick={() => setI((x) => x + 1)}>
            {t.study.next} <ArrowRight />
          </Button>
        ) : (
          <Button onClick={finish} disabled={busy}>
            {t.exam.finish}
          </Button>
        )}
      </div>
    </div>
  );
}

export function ExamReportView({ report, onNew }: { report: ExamReport; onNew: () => void }) {
  const { t } = useI18n();
  const [source, setSource] = useState<Source | null>(null);
  const [filter, setFilter] = useState<"all" | "wrong">("wrong");
  const items = useMemo(() => (filter === "wrong" ? report.items.filter((x) => !x.correct) : report.items), [filter, report]);

  return (
    <div className="mx-auto max-w-3xl">
      <Card className="flex flex-col items-center gap-6 p-6 sm:flex-row sm:p-8">
        <ProgressRing value={report.ratio} size={140} label={pct(report.ratio)} sublabel={`${report.score}/${report.total}`} />
        <div className="flex-1 text-center sm:text-left">
          <p className="eyebrow">{t.exam.reportTitle}</p>
          <h1 className="mt-1 font-display text-3xl text-ink">
            {report.score} / {report.total}
          </h1>
          <p className="tabular mt-1 text-sm text-ink-3">
            {t.exam.elapsed}: {fmtTime(report.elapsed_s)} / {report.minutes} {t.common.minutes}
          </p>
          <Button className="mt-4" onClick={onNew}>
            {t.exam.newExam}
          </Button>
        </div>
      </Card>

      <section className="mt-8">
        <SectionTitle>{t.exam.byTopic}</SectionTitle>
        <ul className="space-y-3 rounded-[var(--radius-lg)] border border-border bg-surface p-4">
          {report.topics.map((tp) => (
            <li key={tp.topic}>
              <div className="mb-1 flex justify-between gap-3 text-sm">
                <span className="truncate text-ink">{tp.topic}</span>
                <span className="tabular shrink-0 text-ink-2">
                  {tp.score}/{tp.total} · {pct(tp.ratio)}
                </span>
              </div>
              <Bar value={tp.ratio} tone={tp.ratio < 0.5 ? "danger" : tp.ratio < 0.75 ? "amber" : "accent"} />
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-8">
        <SectionTitle
          action={
            <div className="inline-flex rounded-[var(--radius-md)] border border-border bg-surface-2 p-0.5 text-xs">
              {(["wrong", "all"] as const).map((v) => (
                <button key={v} onClick={() => setFilter(v)} aria-pressed={filter === v} className={cn("h-7 rounded-[7px] px-2.5 text-ink-3", filter === v && "bg-surface text-ink shadow-sm")}>
                  {v === "wrong" ? t.study.wrong : t.exam.all}
                </button>
              ))}
            </div>
          }
        >
          {t.exam.review}
        </SectionTitle>
        <ul className="space-y-3">
          {items.map((it) => {
            const q = it.question;
            return (
              <li key={it.question_id}>
                <Card className="p-4 sm:p-5">
                  <div className="mb-2 flex items-center gap-2">
                    {it.skipped ? <MinusCircle className="size-4 text-ink-3" /> : it.correct ? <CheckCircle2 className="size-4 text-accent" /> : <XCircle className="size-4 text-danger-ink" />}
                    <Badge>{t.study.type[q.type]}</Badge>
                    {q.topic && <span className="truncate text-xs text-ink-3">{q.topic}</span>}
                  </div>
                  <Stem q={q} className="text-[0.95rem] text-ink" />
                  <dl className="mt-3 grid gap-1 text-sm">
                    <div className="flex gap-2">
                      <dt className="text-ink-3">{t.exam.yourAnswer}:</dt>
                      <dd className={cn(it.correct ? "text-accent" : "text-danger-ink")}>{renderAnswer(q, it.response, t)}</dd>
                    </div>
                    {!it.correct && (
                      <div className="flex gap-2">
                        <dt className="text-ink-3">{t.study.correctAnswer}:</dt>
                        <dd className="font-medium text-ink">{q.type === "mcq" ? q.options[q.correct_index] : q.type === "tf" ? (q.answer === "true" ? t.study.true : t.study.false) : q.answer}</dd>
                      </div>
                    )}
                  </dl>
                  <p className="mt-3 text-sm text-ink-2">{q.explanation}</p>
                  <button onClick={() => setSource(q.source)} className="mt-2 flex max-w-full hover:text-ink">
                    <SourceLabel source={q.source} />
                  </button>
                </Card>
              </li>
            );
          })}
        </ul>
      </section>
      <SourceSheet source={source} open={!!source} onOpenChange={(o) => !o && setSource(null)} />
    </div>
  );
}

function renderAnswer(q: ExamReport["items"][number]["question"], r: unknown, t: ReturnType<typeof useI18n>["t"]): string {
  if (r === null || r === undefined || r === "") return t.exam.skipped;
  if (q.type === "mcq") return q.options[Number(r)] ?? String(r);
  if (q.type === "tf") return r === true || r === "true" ? t.study.true : t.study.false;
  return String(r);
}
