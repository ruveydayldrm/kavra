"use client";

import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, BookOpenCheck, CheckCircle2, ChevronDown, Flag, MapPin, PartyPopper, X, XCircle } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type CheckResult, type PublicQuestion } from "@/lib/api";
import { useHotkeys, useReducedMotion } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import { cn, locLabel } from "@/lib/utils";
import { FlagDialog } from "./flag-dialog";
import { isAnswered, QuestionInput, Stem, type Response } from "./question-input";
import { SourceSheet } from "./source-sheet";
import { Button } from "./ui/button";
import { Badge, Kbd } from "./ui/primitives";
import { EmptyState } from "./ui/states";
import { Bar, ProgressRing } from "./viz";

type Phase = "answer" | "checking" | "feedback";

export function StudySession({ initial }: { initial: PublicQuestion[] }) {
  const { t, f } = useI18n();
  const reduced = useReducedMotion();
  const [queue, setQueue] = useState(initial);
  const [idx, setIdx] = useState(0);
  const [value, setValue] = useState<Response>(null);
  const [phase, setPhase] = useState<Phase>("answer");
  const [result, setResult] = useState<CheckResult | null>(null);
  const [rating, setRating] = useState<number>(3);
  const [explain, setExplain] = useState(true);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [flagOpen, setFlagOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [stats, setStats] = useState({ done: 0, correct: 0 });
  const started = useRef(0);
  const requeued = useRef(new Set<number>());

  const q = queue[idx] as PublicQuestion | undefined;
  const finished = !q;

  useEffect(() => {
    started.current = performance.now();
  }, [idx]);

  const check = useCallback(async () => {
    if (!q || phase !== "answer" || !isAnswered(q, value)) return;
    setPhase("checking");
    const duration = Math.round(performance.now() - started.current);
    try {
      const r = await api.check(q.id, value, duration);
      setResult(r);
      setRating(r.suggested_rating);
      setExplain(!r.correct);
      setPhase("feedback");
    } catch {
      setPhase("answer");
    }
  }, [q, phase, value]);

  const next = useCallback(async () => {
    if (!q || !result) return;
    const duration = Math.round(performance.now() - started.current);
    void api.review({ question_id: q.id, rating, correct: result.correct, response: value, duration_ms: duration, score: result.score });
    setStats((s) => ({ done: s.done + 1, correct: s.correct + (result.correct ? 1 : 0) }));
    if (rating === 1 && !requeued.current.has(q.id)) {
      requeued.current.add(q.id);
      setQueue((qq) => [...qq, q]); // relearn later in this session
    }
    setIdx((i) => i + 1);
    setValue(null);
    setResult(null);
    setPhase("answer");
  }, [q, result, rating, value]);

  useHotkeys(
    (e) => {
      if (!q || flagOpen || sourceOpen) return;
      const typing = (e.target as HTMLElement).tagName === "TEXTAREA" || (e.target as HTMLElement).tagName === "INPUT";
      if (e.key === "Enter") {
        if (typing && e.shiftKey) return; // newline in textarea
        e.preventDefault();
        if (phase === "answer") void check();
        else if (phase === "feedback") void next();
        return;
      }
      if (typing) return;
      if (phase === "answer") {
        if (q.type === "mcq" && /^[1-4]$/.test(e.key)) setValue(Number(e.key) - 1);
        if (q.type === "tf" && /^[tdTD]$/.test(e.key)) setValue(true);
        if (q.type === "tf" && /^[fyFY]$/.test(e.key)) setValue(false);
      }
      if (phase === "feedback") {
        if (e.key === " ") {
          e.preventDefault();
          setExplain((x) => !x);
        }
        if (e.key.toLowerCase() === "s") setSourceOpen(true);
        if (result?.correct && e.key.toLowerCase() === "h") setRating((r) => (r === 2 ? 3 : 2));
        if (result?.correct && e.key.toLowerCase() === "e") setRating((r) => (r === 4 ? 3 : 4));
      }
      if (e.key.toLowerCase() === "r") setFlagOpen(true);
    },
    true,
  );

  if (finished) {
    const acc = stats.done ? Math.round((stats.correct / stats.done) * 100) : 0;
    return (
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mx-auto max-w-md pt-6 text-center">
        <div className="mb-6 flex justify-center">
          <ProgressRing value={stats.done ? stats.correct / stats.done : 0} size={148} label={`${acc}%`} sublabel={t.today.accuracy} />
        </div>
        <h1 className="flex items-center justify-center gap-2 font-display text-3xl text-ink">
          <PartyPopper className="size-6 text-amber-ink" /> {t.study.doneTitle}
        </h1>
        <p className="mt-2 text-ink-2">{f(t.study.doneBody, { n: stats.done, acc })}</p>
        <div className="mt-8 flex flex-col justify-center gap-2 sm:flex-row">
          <Button asChild variant="secondary">
            <Link href="/">{t.study.backToday}</Link>
          </Button>
          <Button asChild>
            <Link href="/exam">{t.nav.exam}</Link>
          </Button>
        </div>
      </motion.div>
    );
  }

  const progress = idx / queue.length;
  const flipped = phase === "feedback";
  const verdict = result ? (result.correct ? (result.score < 1 ? "partly" : "correct") : "wrong") : null;

  return (
    <div className="mx-auto max-w-2xl">
      {/* Session header */}
      <div className="mb-5 flex items-center gap-3">
        <Link href="/" aria-label={t.common.close} className="grid size-9 place-items-center rounded-[var(--radius-md)] text-ink-3 hover:bg-surface-2 hover:text-ink">
          <X className="size-5" />
        </Link>
        <Bar value={progress} className="h-2 flex-1" />
        <span className="tabular w-14 text-right text-sm text-ink-3">
          {idx + 1} {t.study.of} {queue.length}
        </span>
      </div>

      {/* Card with flip */}
      <div className="[perspective:1600px]">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={`${q.id}-${idx}`}
            initial={reduced ? { opacity: 0 } : { opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduced ? { opacity: 0 } : { opacity: 0, y: -10 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            <motion.div
              className="grid [transform-style:preserve-3d]"
              animate={{ rotateY: flipped && !reduced ? 180 : 0 }}
              transition={{ duration: reduced ? 0 : 0.55, ease: [0.22, 1, 0.36, 1] }}
            >
              {/* FRONT */}
              <section
                aria-hidden={flipped}
                className={cn(
                  "col-start-1 row-start-1 rounded-[var(--radius-xl)] border border-border bg-surface p-5 shadow-md [backface-visibility:hidden] sm:p-7",
                  flipped && reduced && "invisible",
                )}
              >
                <CardMeta q={q} />
                <Stem q={q} className="mb-6 font-display text-[1.35rem] leading-snug text-ink sm:text-2xl" />
                <QuestionInput q={q} value={value} onChange={setValue} autoFocus />
                <div className="mt-6 flex items-center justify-between gap-3">
                  <span className="hidden items-center gap-1.5 text-xs text-ink-3 sm:flex">
                    {q.type === "mcq" && (
                      <>
                        <Kbd>1</Kbd>–<Kbd>4</Kbd>
                      </>
                    )}
                    <Kbd>Enter</Kbd>
                  </span>
                  <Button size="lg" className="w-full sm:w-auto" onClick={check} disabled={!isAnswered(q, value) || phase === "checking"} tabIndex={flipped ? -1 : 0}>
                    {t.study.check}
                  </Button>
                </div>
              </section>

              {/* BACK */}
              <section
                aria-hidden={!flipped}
                aria-live="polite"
                className={cn(
                  "col-start-1 row-start-1 rounded-[var(--radius-xl)] border bg-surface p-5 shadow-md [backface-visibility:hidden] sm:p-7",
                  !reduced && "[transform:rotateY(180deg)]",
                  !flipped && reduced && "invisible",
                  verdict === "wrong" ? "border-danger/40" : "border-accent-line",
                )}
              >
                {result && (
                  <>
                    <Verdict verdict={verdict!} />
                    <Stem q={q} className="mb-4 text-base text-ink-2" />
                    <QuestionInput q={q} value={value} onChange={() => {}} result={result} />
                    {q.type !== "mcq" && q.type !== "open" && !result.correct && (
                      <p className="mt-3 text-sm">
                        <span className="text-ink-3">{t.study.correctAnswer}: </span>
                        <span className="font-medium text-ink">
                          {q.type === "tf" ? (result.question.answer === "true" ? t.study.true : t.study.false) : result.question.answer}
                        </span>
                      </p>
                    )}
                    {q.type === "open" && <KeyPoints result={result} />}

                    <div className="mt-5 border-t border-border pt-4">
                      <button
                        onClick={() => setExplain((x) => !x)}
                        aria-expanded={explain}
                        className="flex w-full items-center justify-between text-sm font-medium text-ink"
                      >
                        <span className="flex items-center gap-2">
                          <BookOpenCheck className="size-4 text-accent" /> {t.study.explanation}
                        </span>
                        <span className="flex items-center gap-2 text-ink-3">
                          <Kbd className="hidden sm:inline-flex">Space</Kbd>
                          <ChevronDown className={cn("size-4 transition-transform", explain && "rotate-180")} />
                        </span>
                      </button>
                      <AnimatePresence initial={false}>
                        {explain && (
                          <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            transition={{ duration: reduced ? 0 : 0.2 }}
                            className="overflow-hidden"
                          >
                            <p className="pt-3 text-[0.95rem] leading-relaxed text-ink-2">{result.question.explanation}</p>
                            <button
                              onClick={() => setSourceOpen(true)}
                              className="mt-3 flex w-full items-start gap-2 rounded-[var(--radius-md)] border border-border bg-surface-2/60 p-3 text-left transition-colors hover:border-border-strong"
                            >
                              <MapPin className="mt-0.5 size-4 shrink-0 text-amber-ink" />
                              <span className="min-w-0 flex-1">
                                <span className="line-clamp-2 text-sm italic text-ink">“{result.question.source.quote}”</span>
                                <span className="mt-1 flex items-center justify-between gap-2 text-xs text-ink-3">
                                  <span className="tabular truncate">
                                    {result.question.source.document.title} · {locLabel(result.question.source.loc, t.loc)}
                                  </span>
                                  <span className="flex shrink-0 items-center gap-1 font-medium text-accent">
                                    {t.study.goToSource} <Kbd className="hidden sm:inline-flex">S</Kbd>
                                  </span>
                                </span>
                              </span>
                            </button>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>

                    <div className="mt-5 flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
                      <RatingPicker correct={result.correct} rating={rating} onChange={setRating} />
                      <Button size="lg" onClick={next} className="w-full sm:w-auto" tabIndex={flipped ? 0 : -1}>
                        {t.study.next} <ArrowRight />
                      </Button>
                    </div>
                  </>
                )}
              </section>
            </motion.div>
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="mt-4 flex justify-center">
        <button onClick={() => setFlagOpen(true)} className="inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] px-2 py-1 text-xs text-ink-3 hover:text-danger-ink">
          <Flag className="size-3.5" /> {t.study.report} <Kbd className="hidden sm:inline-flex">R</Kbd>
        </button>
      </div>

      <SourceSheet source={result?.question.source ?? null} open={sourceOpen} onOpenChange={setSourceOpen} />
      <FlagDialog
        questionId={q.id}
        open={flagOpen}
        onOpenChange={setFlagOpen}
        onFlagged={() => {
          setToast(t.study.flagged);
          setTimeout(() => setToast(null), 2800);
          setQueue((qq) => qq.filter((x, i) => i < idx || x.id !== q.id));
          setValue(null);
          setResult(null);
          setPhase("answer");
        }}
      />
      <AnimatePresence>
        {toast && (
          <motion.div
            role="status"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            className="fixed inset-x-4 bottom-6 z-50 mx-auto max-w-sm rounded-[var(--radius-md)] bg-ink px-4 py-3 text-center text-sm text-bg shadow-lg"
          >
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function CardMeta({ q }: { q: PublicQuestion }) {
  const { t } = useI18n();
  return (
    <div className="mb-4 flex flex-wrap items-center gap-1.5">
      {q.is_new ? <Badge tone="amber">{t.study.new}</Badge> : <Badge tone="accent">{t.study.review}</Badge>}
      <Badge>{t.study.type[q.type]}</Badge>
      <Badge>{t.study.difficulty[q.difficulty]}</Badge>
      {q.topic && <span className="ml-auto max-w-[45%] truncate text-xs text-ink-3">{q.topic}</span>}
    </div>
  );
}

function Verdict({ verdict }: { verdict: "correct" | "partly" | "wrong" }) {
  const { t } = useI18n();
  const reduced = useReducedMotion();
  const good = verdict !== "wrong";
  return (
    <div className="mb-4 flex items-center gap-2.5">
      <motion.span
        initial={reduced ? false : { scale: 0.4, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 500, damping: 18, delay: reduced ? 0 : 0.35 }}
        className={cn("grid size-8 place-items-center rounded-full", good ? "bg-accent text-accent-ink" : "bg-danger text-white")}
      >
        {good ? <CheckCircle2 className="size-5" /> : <XCircle className="size-5" />}
      </motion.span>
      <span className={cn("font-display text-xl", good ? "text-accent" : "text-danger-ink")}>
        {verdict === "correct" ? t.study.correct : verdict === "partly" ? t.study.partly : t.study.wrong}
      </span>
    </div>
  );
}

function KeyPoints({ result }: { result: CheckResult }) {
  const { t } = useI18n();
  const kps = result.key_points ?? result.question.key_points;
  const covered = new Set(result.covered ?? []);
  return (
    <div className="mt-4 space-y-3">
      {[
        { title: t.study.missing, items: kps.filter((_, i) => !covered.has(i)), ok: false },
        { title: t.study.covered, items: kps.filter((_, i) => covered.has(i)), ok: true },
      ]
        .filter((g) => g.items.length)
        .map((g) => (
          <div key={g.title}>
            <p className="eyebrow mb-1.5">{g.title}</p>
            <ul className="space-y-1.5">
              {g.items.map((k) => (
                <li key={k} className="flex gap-2 text-sm">
                  {g.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-accent" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-danger-ink" />}
                  <span className={g.ok ? "text-ink-2" : "text-ink"}>{k}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
    </div>
  );
}

function RatingPicker({ correct, rating, onChange }: { correct: boolean; rating: number; onChange: (r: number) => void }) {
  const { t } = useI18n();
  if (!correct) {
    return <span className="text-xs text-ink-3">{t.study.rateAgain} · FSRS</span>;
  }
  const opts = [
    { r: 2, label: t.study.rateHard, key: "H" },
    { r: 3, label: t.study.rateGood, key: "" },
    { r: 4, label: t.study.rateEasy, key: "E" },
  ];
  return (
    <div role="radiogroup" aria-label={t.study.rateHint} className="inline-flex rounded-[var(--radius-md)] border border-border bg-surface-2 p-0.5">
      {opts.map((o) => (
        <button
          key={o.r}
          role="radio"
          aria-checked={rating === o.r}
          onClick={() => onChange(o.r)}
          className={cn("flex h-8 items-center gap-1.5 rounded-[7px] px-3 text-sm text-ink-2 hover:text-ink", rating === o.r && "bg-surface text-ink shadow-sm")}
        >
          {o.label}
          {o.key && <span className="hidden font-mono text-[10px] text-ink-3 sm:inline">{o.key}</span>}
        </button>
      ))}
    </div>
  );
}

export function NothingDue() {
  const { t } = useI18n();
  return (
    <EmptyState
      icon={<CheckCircle2 className="size-10" strokeWidth={1.4} />}
      title={t.study.nothingDue}
      body={t.study.nothingDueHint}
      action={
        <div className="flex gap-2">
          <Button asChild variant="secondary">
            <Link href="/library">{t.nav.library}</Link>
          </Button>
          <Button asChild>
            <Link href="/exam">{t.nav.exam}</Link>
          </Button>
        </div>
      }
    />
  );
}
