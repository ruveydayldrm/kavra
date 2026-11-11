"use client";

import { useCallback, useSyncExternalStore } from "react";

/** A localStorage-backed preference readable during render without hydration mismatch. */
export function usePref<T extends string>(key: string, fallback: T, allowed: readonly T[]): [T, (v: T) => void] {
  const subscribe = useCallback(
    (cb: () => void) => {
      const on = (e: Event) => {
        if (e instanceof StorageEvent ? e.key === key : (e as CustomEvent).detail === key) cb();
      };
      window.addEventListener("storage", on);
      window.addEventListener("kavra-pref", on);
      return () => {
        window.removeEventListener("storage", on);
        window.removeEventListener("kavra-pref", on);
      };
    },
    [key],
  );
  const read = useCallback((): T => {
    try {
      const v = localStorage.getItem(key);
      return v && (allowed as readonly string[]).includes(v) ? (v as T) : fallback;
    } catch {
      return fallback;
    }
  }, [key, fallback, allowed]);
  const value = useSyncExternalStore(subscribe, read, () => fallback);
  const set = useCallback(
    (v: T) => {
      try {
        localStorage.setItem(key, v);
      } catch {}
      window.dispatchEvent(new CustomEvent("kavra-pref", { detail: key }));
    },
    [key],
  );
  return [value, set];
}

const darkQuery = "(prefers-color-scheme: dark)";

export function useSystemDark(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(darkQuery);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia(darkQuery).matches,
    () => false,
  );
}
