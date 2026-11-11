"use client";

import { CheckCircle2, CircleSlash, Lock, ShieldAlert } from "lucide-react";
import { LangSwitch, ThemeSwitch } from "@/components/app-shell";
import { Badge, Card, PageHeader, SectionTitle, Skeleton } from "@/components/ui/primitives";
import { ErrorState } from "@/components/ui/states";
import { api } from "@/lib/api";
import { useQuery } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";

export default function SettingsPage() {
  const { t } = useI18n();
  const h = useQuery(api.health, []);

  return (
    <>
      <PageHeader title={t.settings.title} />
      <section>
        <SectionTitle>{t.settings.appearance}</SectionTitle>
        <Card className="divide-y divide-border">
          <div className="flex items-center justify-between gap-4 p-4">
            <span className="text-sm text-ink-2">{t.common.theme}</span>
            <ThemeSwitch />
          </div>
          <div className="flex items-center justify-between gap-4 p-4">
            <span className="text-sm text-ink-2">{t.common.language}</span>
            <LangSwitch />
          </div>
        </Card>
      </section>

      <section className="mt-10">
        <SectionTitle hint={t.settings.providersHint}>{t.settings.providers}</SectionTitle>
        {h.error ? (
          <ErrorState error={h.error} onRetry={h.reload} />
        ) : !h.data ? (
          <Skeleton className="h-40 rounded-[var(--radius-lg)]" />
        ) : (
          <Card className="divide-y divide-border">
            <div className="flex items-start gap-3 p-4">
              <Lock className="mt-0.5 size-4 text-accent" />
              <div className="flex-1">
                <p className="text-sm font-medium text-ink">{t.settings.localMode}</p>
                <p className="text-sm text-ink-2">{h.data.local_mode ? t.settings.localOn : t.settings.localOff}</p>
              </div>
              <Badge tone={h.data.local_mode ? "accent" : "neutral"}>{h.data.local_mode ? "ON" : "OFF"}</Badge>
            </div>
            {Object.entries(h.data.chains).map(([role, chain]) => (
              <div key={role} className="p-4">
                <p className="eyebrow mb-2">{t.insights.role[role as "generator" | "auditor"] ?? role}</p>
                <ol className="space-y-1.5">
                  {chain.map((spec, i) => (
                    <li key={spec} className="flex items-center gap-2 text-sm">
                      <span className="tabular w-4 text-xs text-ink-3">{i + 1}</span>
                      <code className="font-mono text-xs text-ink">{spec}</code>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
            <div className="flex flex-wrap gap-2 p-4">
              {(["gemini", "groq"] as const).map((k) => (
                <Badge key={k} tone={h.data!.keys[k] ? "accent" : "neutral"}>
                  {h.data!.keys[k] ? <CheckCircle2 /> : <CircleSlash />} {k}: {h.data!.keys[k] ? t.settings.keySet : t.settings.keyMissing}
                </Badge>
              ))}
            </div>
          </Card>
        )}
      </section>

      <section className="mt-10">
        <SectionTitle>{t.settings.privacy}</SectionTitle>
        <Card className="flex gap-3 border-amber/40 bg-amber-soft/50 p-4">
          <ShieldAlert className="mt-0.5 size-5 shrink-0 text-amber-ink" />
          <p className="text-sm text-ink-2">{t.settings.privacyBody}</p>
        </Card>
      </section>
    </>
  );
}
