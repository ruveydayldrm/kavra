"use client";

import { motion } from "motion/react";
import { Check, X } from "lucide-react";
import type { CheckResult, PublicQuestion } from "@/lib/api";
import { useReducedMotion } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { Kbd } from "./ui/primitives";

export type Response = number | string | boolean | null;

/** Renders the answer controls for any question type.
 *  With `result` it switches to a read-only "graded" view. */
export function QuestionInput({
  q,
  value,
  onChange,
  result,
  autoFocus,
}: {
  q: PublicQuestion;
  value: Response;
  onChange: (v: Response) => void;
  result?: CheckResult | null;
  autoFocus?: boolean;
}) {
  const { t, f } = useI18n();
  const reduced = useReducedMotion();
  const graded = !!result;

  if (q.type === "mcq") {
    const correctIdx = result?.question.correct_index;
    return (
      <div role="radiogroup" aria-label={q.stem} className="grid gap-2">
        {q.options.map((opt, i) => {
          const chosen = value === i;
          const isCorrect = graded && i === correctIdx;
          const isWrongChoice = graded && chosen && i !== correctIdx;
          return (
            <motion.button
              key={i}
              type="button"
              role="radio"
              aria-checked={chosen}
              disabled={graded}
              onClick={() => onChange(i)}
              animate={isWrongChoice && !reduced ? { x: [0, -6, 6, -3, 3, 0] } : { x: 0 }}
              transition={{ duration: 0.4 }}
              className={cn(
                "group flex min-h-12 w-full items-center gap-3 rounded-[var(--radius-md)] border border-border bg-surface px-3.5 py-3 text-left text-[0.95rem] text-ink transition-[border-color,background-color,box-shadow] duration-150",
                !graded && "hover:border-border-strong hover:bg-surface-2",
                chosen && !graded && "border-accent bg-accent-soft/60 ring-2 ring-accent/20",
                isCorrect && "border-accent bg-accent-soft text-ink",
                isWrongChoice && "border-danger/50 bg-danger-soft",
                graded && !isCorrect && !isWrongChoice && "opacity-60",
              )}
            >
              <span
                className={cn(
                  "tabular grid size-6 shrink-0 place-items-center rounded-[6px] border border-border bg-bg text-xs font-medium text-ink-3",
                  chosen && !graded && "border-accent bg-accent text-accent-ink",
                  isCorrect && "border-accent bg-accent text-accent-ink",
                  isWrongChoice && "border-danger bg-danger text-white",
                )}
              >
                {isCorrect ? <Check className="size-3.5" /> : isWrongChoice ? <X className="size-3.5" /> : i + 1}
              </span>
              <span className="flex-1">{opt}</span>
            </motion.button>
          );
        })}
      </div>
    );
  }

  if (q.type === "tf") {
    const correct = result?.question.answer;
    const opts = [
      { v: true, label: t.study.true, key: "T" },
      { v: false, label: t.study.false, key: "F" },
    ];
    return (
      <div role="radiogroup" aria-label={q.stem} className="grid grid-cols-2 gap-2">
        {opts.map((o) => {
          const chosen = value === o.v;
          const isCorrect = graded && String(o.v) === correct;
          const isWrong = graded && chosen && !isCorrect;
          return (
            <motion.button
              key={o.label}
              type="button"
              role="radio"
              aria-checked={chosen}
              disabled={graded}
              onClick={() => onChange(o.v)}
              animate={isWrong && !reduced ? { x: [0, -6, 6, -3, 3, 0] } : { x: 0 }}
              transition={{ duration: 0.4 }}
              className={cn(
                "flex h-14 items-center justify-center gap-2 rounded-[var(--radius-md)] border border-border bg-surface font-medium text-ink transition-colors",
                !graded && "hover:border-border-strong hover:bg-surface-2",
                chosen && !graded && "border-accent bg-accent-soft/60 ring-2 ring-accent/20",
                isCorrect && "border-accent bg-accent-soft",
                isWrong && "border-danger/50 bg-danger-soft",
                graded && !isCorrect && !isWrong && "opacity-60",
              )}
            >
              {o.label}
              {!graded && <Kbd className="hidden sm:inline-flex">{o.key}</Kbd>}
            </motion.button>
          );
        })}
      </div>
    );
  }

  if (q.type === "cloze") {
    return (
      <div>
        <input
          autoFocus={autoFocus}
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          readOnly={graded}
          aria-label={t.study.clozePlaceholder}
          placeholder={t.study.clozePlaceholder}
          autoComplete="off"
          spellCheck={false}
          className={cn(
            "h-12 w-full rounded-[var(--radius-md)] border border-border bg-bg px-4 text-base text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25",
            graded && (result?.correct ? "border-accent bg-accent-soft" : "border-danger/50 bg-danger-soft"),
          )}
        />
        {graded && result?.near_miss && <p className="mt-2 text-sm text-amber-ink">{t.study.nearMiss}</p>}
      </div>
    );
  }

  return (
    <div>
      <textarea
        autoFocus={autoFocus}
        value={(value as string) ?? ""}
        onChange={(e) => onChange(e.target.value)}
        readOnly={graded}
        rows={5}
        aria-label={t.study.openPlaceholder}
        placeholder={t.study.openPlaceholder}
        className="w-full resize-y rounded-[var(--radius-md)] border border-border bg-bg px-4 py-3 text-base leading-relaxed text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25"
      />
      {!graded && q.key_point_count > 0 && <p className="mt-1.5 text-xs text-ink-3">{f(t.study.keyPointsHint, { n: q.key_point_count })}</p>}
    </div>
  );
}

export function isAnswered(q: PublicQuestion, v: Response): boolean {
  if (q.type === "mcq") return typeof v === "number";
  if (q.type === "tf") return typeof v === "boolean";
  return typeof v === "string" && v.trim().length > 0;
}

/** Renders a cloze stem with a visual blank. */
export function Stem({ q, className }: { q: PublicQuestion; className?: string }) {
  if (q.type !== "cloze") return <p className={className}>{q.stem}</p>;
  const parts = q.stem.split("____");
  return (
    <p className={className}>
      {parts.map((p, i) => (
        <span key={i}>
          {p}
          {i < parts.length - 1 && <span className="mx-1 inline-block w-20 translate-y-[-0.2em] border-b-2 border-dashed border-accent-line align-baseline" aria-label="___" />}
        </span>
      ))}
    </p>
  );
}
