"use client";

import { ArrowRight, CheckCircle2, FileStack, Sparkles, Target } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, Skeleton, SectionTitle } from "@/components/ui/primitives";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { Bar, Heatmap, MasteryMap, ProgressRing, Streak } from "@/components/viz";
import { api } from "@/lib/api";
import { useQuery } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import { pct, relativeDue } from "@/lib/utils";

function useGreeting() {
  const { t } = useI18n();
  return useMemo(() => {
    const h = new Date().getHours();
    return h < 12 ? t.today.greetingMorning : h < 18 ? t.today.greetingDay : t.today.greetingEvening;
  }, [t]);
}

export default function TodayPage() {
  const { t, f, locale } = useI18n();
  const router = useRouter();
  const greeting = useGreeting();
  const [now] = useState(() => Date.now());
  const { data, error, loading, reload } = useQuery(api.overview, []);

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading || !data) return <TodaySkeleton />;

  const greet = (
    <div className="mb-8">
      <p className="eyebrow">{new Intl.DateTimeFormat(locale === "tr" ? "tr-TR" : "en-US", { weekday: "long", day: "numeric", month: "long" }).format(new Date())}</p>
      <h1 className="mt-2 font-display text-3xl text-ink sm:text-4xl">{greeting}</h1>
    </div>
  );

  if (data.totals.documents === 0) {
    return (
      <>
        {greet}
        <EmptyState
          icon={<FileStack className="size-10" strokeWidth={1.4} />}
          title={t.today.emptyTitle}
          body={t.today.emptyBody}
          action={
            <Button asChild size="lg">
              <Link href="/library">
                {t.today.emptyCta} <ArrowRight />
              </Link>
            </Button>
          }
        />
      </>
    );
  }

  const todo = data.due + data.new;
  const goal = data.reviewed_today + todo;
  const progress = goal ? data.reviewed_today / goal : 1;
  const acc = data.reviewed_today ? data.correct_today / data.reviewed_today : null;
  const rtf = new Intl.RelativeTimeFormat(locale === "tr" ? "tr" : "en", { numeric: "auto" });

  return (
    <>
      {greet}
      <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        {/* Today card */}
        <Card className="relative overflow-hidden p-6 sm:p-7">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
            <ProgressRing
              value={progress}
              size={128}
              label={`${Math.round(progress * 100)}%`}
              sublabel={`${data.reviewed_today}/${goal}`}
            />
            <div className="flex-1">
              <p className="eyebrow">{t.today.dueTitle}</p>
              {todo > 0 ? (
                <>
                  <p className="mt-2 font-display text-2xl text-ink">
                    {data.due > 0 && f(t.today.dueCount, { n: data.due })}
                    {data.due > 0 && data.new > 0 && " · "}
                    {data.new > 0 && f(t.today.newCount, { n: data.new })}
                  </p>
                  <Button size="lg" className="mt-5 w-full sm:w-auto" onClick={() => router.push("/study")}>
                    {t.today.startStudy} <ArrowRight />
                  </Button>
                </>
              ) : (
                <>
                  <p className="mt-2 flex items-center gap-2 font-display text-2xl text-ink">
                    <CheckCircle2 className="size-6 text-accent" /> {t.today.allDone}
                  </p>
                  <p className="mt-2 text-sm text-ink-2">
                    {f(t.today.allDoneHint, { when: relativeDue(data.next_due_at, now, rtf) ?? "—" })}
                  </p>
                </>
              )}
            </div>
          </div>
          <div className="mt-6 grid grid-cols-2 gap-4 border-t border-border pt-5">
            <div>
              <div className="tabular font-display text-xl text-ink">{data.reviewed_today}</div>
              <div className="text-xs text-ink-3">{t.today.doneToday}</div>
            </div>
            <div>
              <div className="tabular font-display text-xl text-ink">{pct(acc)}</div>
              <div className="text-xs text-ink-3">{t.today.accuracy}</div>
            </div>
          </div>
        </Card>

        {/* Streak + heatmap */}
        <Card className="flex flex-col gap-5 p-6">
          <Streak current={data.streak.current} best={data.streak.best} active={data.streak.studied_today} />
          <div>
            <SectionTitle hint={t.today.activityHint}>{t.today.activity}</SectionTitle>
            <Heatmap days={data.heatmap} />
          </div>
        </Card>
      </div>

      {/* Weak topics */}
      <section className="mt-10">
        <SectionTitle>
          <span className="inline-flex items-center gap-2">
            <Target className="size-4 text-danger-ink" /> {t.today.weakTitle}
          </span>
        </SectionTitle>
        {data.weak_topics.length === 0 ? (
          <p className="flex items-center gap-2 rounded-[var(--radius-md)] border border-dashed border-border-strong px-4 py-4 text-sm text-ink-2">
            <Sparkles className="size-4 shrink-0 text-amber-ink" /> {t.today.weakEmpty}
          </p>
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-[var(--radius-lg)] border border-border bg-surface">
            {data.weak_topics.map((w) => (
              <li key={w.id} className="flex items-center gap-4 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-ink">{w.title}</div>
                  <div className="truncate text-xs text-ink-3">{w.document_title}</div>
                  <Bar value={w.accuracy ?? 0} tone="danger" className="mt-2 max-w-48" />
                </div>
                <span className="tabular text-sm text-ink-2">{pct(w.accuracy)}</span>
                <Button variant="secondary" size="sm" onClick={() => router.push(`/study?topic=${w.id}`)}>
                  {t.today.practice}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Mastery map */}
      {data.mastery.length > 0 && (
        <section className="mt-10">
          <SectionTitle>{t.today.masteryTitle}</SectionTitle>
          <MasteryMap topics={data.mastery} onPick={(tp) => router.push(`/study?topic=${tp.id}`)} />
        </section>
      )}
    </>
  );
}

function TodaySkeleton() {
  return (
    <div aria-busy="true">
      <Skeleton className="mb-3 h-3 w-32" />
      <Skeleton className="mb-8 h-10 w-64" />
      <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <Skeleton className="h-64 rounded-[var(--radius-lg)]" />
        <Skeleton className="h-64 rounded-[var(--radius-lg)]" />
      </div>
      <Skeleton className="mt-10 h-5 w-40" />
      <Skeleton className="mt-3 h-40 rounded-[var(--radius-lg)]" />
    </div>
  );
}
