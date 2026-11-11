"use client";

import { Link2, Loader2, UploadCloud } from "lucide-react";
import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";

const ACCEPT = ".pdf,.pptx,.docx,.png,.jpg,.jpeg,.webp,.txt,.md";

export function UploadPanel({ onAdded }: { onAdded: () => void }) {
  const { t } = useI18n();
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState("");
  const [err, setErr] = useState<string | null>(null);

  async function send(files: FileList | File[]) {
    setErr(null);
    setBusy(true);
    try {
      for (const file of Array.from(files)) {
        const ext = "." + (file.name.split(".").pop() ?? "").toLowerCase();
        if (!ACCEPT.split(",").includes(ext)) {
          setErr(`${file.name}: ${t.library.unsupported}`);
          continue;
        }
        await api.upload(file);
      }
      onAdded();
    } catch (e) {
      setErr(e instanceof ApiError && e.status === 0 ? t.common.offline : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function addUrl(e: FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setErr(null);
    setBusy(true);
    try {
      await api.youtube(url.trim());
      setUrl("");
      onAdded();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDrag(false);
    if (e.dataTransfer.files.length) void send(e.dataTransfer.files);
  }

  return (
    <div className="rounded-[var(--radius-xl)] border border-border bg-surface p-2 shadow-sm">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        className={cn(
          "flex flex-col items-center justify-center gap-3 rounded-[var(--radius-lg)] border border-dashed border-border-strong bg-surface-2/60 px-6 py-10 text-center transition-colors",
          drag && "border-accent bg-accent-soft",
        )}
      >
        <div className={cn("grid size-12 place-items-center rounded-full bg-surface text-accent shadow-sm transition-transform", drag && "scale-110")}>
          {busy ? <Loader2 className="size-5 animate-spin" /> : <UploadCloud className="size-5" />}
        </div>
        <div>
          <p className="font-medium text-ink">{busy ? t.library.uploading : t.library.dropTitle}</p>
          <p className="mt-1 text-xs text-ink-3">{t.library.dropHint}</p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => input.current?.click()} disabled={busy}>
          {t.library.browse}
        </Button>
        <input
          ref={input}
          type="file"
          accept={ACCEPT}
          multiple
          className="sr-only"
          aria-label={t.library.browse}
          onChange={(e) => e.target.files && send(e.target.files)}
        />
      </div>
      <form onSubmit={addUrl} className="mt-2 flex items-center gap-2 px-1 pb-1">
        <span className="hidden text-xs text-ink-3 sm:inline">{t.library.or}</span>
        <label className="relative flex-1">
          <span className="sr-only">{t.library.youtubePlaceholder}</span>
          <Link2 className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" />
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder={t.library.youtubePlaceholder}
            inputMode="url"
            className="h-10 w-full rounded-[var(--radius-md)] border border-border bg-bg pl-9 pr-3 text-sm text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25"
          />
        </label>
        <Button type="submit" disabled={busy || !url.trim()}>
          {t.library.add}
        </Button>
      </form>
      {err && (
        <p role="alert" className="mx-1 mb-1 mt-2 rounded-[var(--radius-sm)] bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {err}
        </p>
      )}
    </div>
  );
}
