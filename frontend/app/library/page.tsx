"use client";

import { Library } from "lucide-react";
import { DocRow } from "@/components/doc-row";
import { PageHeader, Skeleton } from "@/components/ui/primitives";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { UploadPanel } from "@/components/upload";
import { api } from "@/lib/api";
import { useQuery } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";

export default function LibraryPage() {
  const { t } = useI18n();
  const { data, error, loading, reload } = useQuery(api.documents, []);

  return (
    <>
      <PageHeader title={t.library.title} subtitle={t.library.subtitle} />
      <UploadPanel onAdded={reload} />
      <section className="mt-8" aria-live="polite">
        {error ? (
          <ErrorState error={error} onRetry={reload} />
        ) : loading || !data ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-[72px] rounded-[var(--radius-lg)]" />
            ))}
          </div>
        ) : data.length === 0 ? (
          <EmptyState icon={<Library className="size-9" strokeWidth={1.4} />} title={t.library.empty} body={t.library.emptyHint} />
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-[var(--radius-lg)] border border-border bg-surface shadow-sm">
            {data.map((d) => (
              <DocRow key={`${d.id}-${d.status}-${d.job?.id}`} doc={d} onChange={reload} />
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
