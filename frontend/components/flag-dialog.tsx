"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";
import { Dialog } from "./ui/dialog";

const REASONS = ["wrong_answer", "ambiguous", "not_in_source", "typo", "other"] as const;

export function FlagDialog({ questionId, open, onOpenChange, onFlagged }: { questionId: number; open: boolean; onOpenChange: (o: boolean) => void; onFlagged: () => void }) {
  const { t } = useI18n();
  const [reason, setReason] = useState<(typeof REASONS)[number]>("wrong_answer");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      await api.flag(questionId, reason, note);
      onFlagged();
      onOpenChange(false);
      setNote("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={t.flag.title} description={t.flag.why} closeLabel={t.common.close}>
      <fieldset className="grid gap-1.5">
        <legend className="sr-only">{t.flag.title}</legend>
        {REASONS.map((r) => (
          <label
            key={r}
            className={cn(
              "flex cursor-pointer items-center gap-3 rounded-[var(--radius-md)] border border-border px-3 py-2.5 text-sm hover:bg-surface-2",
              reason === r && "border-accent bg-accent-soft/50",
            )}
          >
            <input type="radio" name="reason" value={r} checked={reason === r} onChange={() => setReason(r)} className="accent-[var(--accent)]" />
            {t.flag.reasons[r]}
          </label>
        ))}
      </fieldset>
      <label className="mt-4 block">
        <span className="mb-1.5 block text-xs text-ink-3">{t.flag.note}</span>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          className="w-full rounded-[var(--radius-md)] border border-border bg-bg px-3 py-2 text-sm focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25"
        />
      </label>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={() => onOpenChange(false)}>
          {t.common.cancel}
        </Button>
        <Button variant="danger" onClick={submit} disabled={busy}>
          {t.flag.submit}
        </Button>
      </div>
    </Dialog>
  );
}
