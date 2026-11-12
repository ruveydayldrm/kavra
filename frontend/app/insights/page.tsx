"use client";

import { useRouter } from "next/navigation";
import { Card, PageHeader, SectionTitle, Skeleton } from "@/components/ui/primitives";
import { ErrorState } from "@/components/ui/states";
import { Bar, Heatmap, MasteryMap } from "@/components/viz";
import { api } from "@/lib/api";
import { useQuery } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import { pct } from "@/lib/utils";

export default function InsightsPage() {
  const { t } = useI18n();
  const router = useRouter();
  const ov = useQuery(api.overview, []);
  const q = useQuery(api.quality, []);

  if (ov.error) return <ErrorState error={ov.error} onRetry={ov.reload} />;
  if (q.error) return <ErrorState error={q.error} onRetry={q.reload} />;

  return (
    <>
      <PageHeader title={t.insights.title} subtitle={t.insights.subtitle} />
      {!ov.data || !q.data ? (
        <div className="grid gap-4 sm:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24 rounded-[var(--radius-lg)]" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label={t.insights.acceptance} value={pct(q.data.acceptance_rate)} hint={`${q.data.kept}/${q.data.candidates}`} />
            <Stat label={t.insights.flagRate} value={pct(q.data.flag_rate, 1)} hint={`${q.data.flagged}`} />
            <Stat label={t.insights.calls} value={String(q.data.llm_calls)} hint={`${t.insights.cache}: ${q.data.cache_hits}`} />
            <Stat label={t.insights.cost} value="$0.00" hint="free tiers" accent />
          </div>

          <section className="mt-10 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card className="p-5">
              <SectionTitle>{t.doc.rejectedBy}</SectionTitle>
              {Object.keys(q.data.rejected).length === 0 ? (
                <p className="text-sm text-ink-3">—</p>
              ) : (
                <ul className="space-y-3">
                  {Object.entries(q.data.rejected)
                    .sort((a, b) => b[1] - a[1])
                    .map(([stage, n]) => (
                      <li key={stage}>
                        <div className="mb-1 flex justify-between text-sm">
                          <span className="text-ink-2">{t.doc.stage[stage as keyof typeof t.doc.stage] ?? stage}</span>
                          <span className="tabular text-ink">{n}</span>
                        </div>
                        <Bar value={n / Math.max(1, q.data!.candidates)} tone="danger" />
                      </li>
                    ))}
                </ul>
              )}
            </Card>
            <Card className="p-5">
              <SectionTitle>{t.insights.providers}</SectionTitle>
              {q.data.providers.length === 0 ? (
                <p className="text-sm text-ink-3">—</p>
              ) : (
                <ul className="divide-y divide-border text-sm">
                  {q.data.providers.map((p) => (
                    <li key={`${p.provider}${p.model}${p.role}`} className="flex items-center justify-between gap-3 py-2">
                      <span className="min-w-0">
                        <span className="block truncate font-mono text-xs text-ink">
                          {p.provider}:{p.model}
                        </span>
                        <span className="text-xs text-ink-3">{t.insights.role[p.role as "generator" | "auditor"] ?? p.role}</span>
                      </span>
                      <span className="tabular shrink-0 text-ink-2">
                        {p.ok}/{p.n}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </section>

          <section className="mt-10">
            <SectionTitle hint={t.today.activityHint}>{t.today.activity}</SectionTitle>
            <Card className="p-5">
              <Heatmap days={ov.data.heatmap} />
            </Card>
          </section>

          {ov.data.mastery.length > 0 && (
            <section className="mt-10">
              <SectionTitle>{t.today.masteryTitle}</SectionTitle>
              <MasteryMap topics={ov.data.mastery} onPick={(tp) => router.push(`/study?topic=${tp.id}`)} />
            </section>
          )}
        </>
      )}
    </>
  );
}

function Stat({ label, value, hint, accent }: { label: string; value: string; hint?: string; accent?: boolean }) {
  return (
    <Card className="p-4">
      <p className="eyebrow">{label}</p>
      <p className={`tabular mt-2 font-display text-3xl ${accent ? "text-accent" : "text-ink"}`}>{value}</p>
      {hint && <p className="tabular mt-1 text-xs text-ink-3">{hint}</p>}
    </Card>
  );
}
