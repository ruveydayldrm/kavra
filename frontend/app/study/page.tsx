"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { NothingDue, StudySession } from "@/components/study-session";
import { Skeleton } from "@/components/ui/primitives";
import { ErrorState } from "@/components/ui/states";
import { api } from "@/lib/api";
import { useQuery } from "@/lib/hooks";

function StudyLoader() {
  const sp = useSearchParams();
  const doc = Number(sp.get("doc")) || undefined;
  const topic = Number(sp.get("topic")) || undefined;
  const { data, error, loading, reload } = useQuery(() => api.queue({ document_id: doc, topic_id: topic }), [doc, topic]);
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading || !data) return <StudySkeleton />;
  if (!data.items.length) return <NothingDue />;
  return <StudySession key={`${doc}-${topic}`} initial={data.items} />;
}

function StudySkeleton() {
  return (
    <div className="mx-auto max-w-2xl" aria-busy="true">
      <Skeleton className="mb-5 h-9" />
      <Skeleton className="h-[420px] rounded-[var(--radius-xl)]" />
    </div>
  );
}

export default function StudyPage() {
  return (
    <Suspense fallback={<StudySkeleton />}>
      <StudyLoader />
    </Suspense>
  );
}
