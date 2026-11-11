"use client";

import { useCallback, useEffect, useEffectEvent, useState, useSyncExternalStore } from "react";

export type Query<T> = { data: T | undefined; error: Error | undefined; loading: boolean; reload: () => void };

type State<T> = { key: string; data?: T; error?: Error };

/** Minimal fetch hook: keeps previous data during reloads, exposes errors.
 *  State is only written from async callbacks; `loading` is derived. */
export function useQuery<T>(fn: () => Promise<T>, deps: unknown[] = [], pollMs?: number): Query<T> {
  const [tick, setTick] = useState(0);
  const [state, setState] = useState<State<T>>({ key: "" });
  const key = JSON.stringify([deps, tick]);
  const run = useEffectEvent(() => fn());

  useEffect(() => {
    let alive = true;
    run().then(
      (data) => alive && setState({ key, data }),
      (error: Error) => alive && setState((s) => ({ key, data: s.data, error })),
    );
    return () => {
      alive = false;
    };
  }, [key]);

  useEffect(() => {
    if (!pollMs) return;
    const id = setInterval(() => setTick((t) => t + 1), pollMs);
    return () => clearInterval(id);
  }, [pollMs]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const pending = state.key !== key;
  return { data: state.data, error: pending ? undefined : state.error, loading: pending && state.data === undefined, reload };
}

const motionQuery = "(prefers-reduced-motion: reduce)";

export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(motionQuery);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia(motionQuery).matches,
    () => false,
  );
}

/** Global keyboard shortcuts that ignore typing in inputs (unless `allowInInputs`). */
export function useHotkeys(handler: (e: KeyboardEvent) => void, allowInInputs = false) {
  const onKey = useEffectEvent((e: KeyboardEvent) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const el = e.target as HTMLElement | null;
    const typing = !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
    if (typing && !allowInInputs) return;
    handler(e);
  });
  useEffect(() => {
    const on = (e: KeyboardEvent) => onKey(e);
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);
}
