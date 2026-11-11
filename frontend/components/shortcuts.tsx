"use client";

import { useI18n } from "@/lib/i18n";
import { Dialog } from "./ui/dialog";
import { Kbd } from "./ui/primitives";

export function ShortcutsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { t } = useI18n();
  const rows: [string[], string][] = [
    [["1", "2", "3", "4"], t.shortcuts.choose],
    [["T", "F"], t.shortcuts.tf],
    [["Enter"], t.shortcuts.check],
    [["Space"], t.shortcuts.explain],
    [["S"], t.shortcuts.source],
    [["H", "E"], t.shortcuts.rate],
    [["R"], t.shortcuts.flag],
    [["?"], t.shortcuts.help],
  ];
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={t.shortcuts.title} closeLabel={t.common.close}>
      <dl className="divide-y divide-border">
        {rows.map(([keys, label]) => (
          <div key={label} className="flex items-center justify-between gap-4 py-2.5">
            <dt className="text-sm text-ink-2">{label}</dt>
            <dd className="flex gap-1">
              {keys.map((k) => (
                <Kbd key={k}>{k}</Kbd>
              ))}
            </dd>
          </div>
        ))}
      </dl>
    </Dialog>
  );
}
