// Light or dark colours. The device's setting decides until the person picks one with the toggle in the top bar;
// their pick is remembered in this browser (localStorage "sabha.theme"). public/theme-init.js applies it before the
// first paint; this module keeps <html data-theme> in step afterwards, including when the device setting changes.

import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const KEY = "sabha.theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

function saved(): Theme | null {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null; // storage blocked
  }
}

function deviceTheme(): Theme {
  return typeof window.matchMedia === "function" && window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

/** The theme in use: the person's pick, else the device's. */
export function currentTheme(): Theme {
  return saved() ?? deviceTheme();
}

function apply(theme: Theme) {
  document.documentElement.dataset.theme = theme;
}

export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(currentTheme);

  useEffect(() => {
    apply(theme);
  }, [theme]);

  // Follow the device while the person has not picked one.
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia(DARK_QUERY);
    const onChange = () => {
      if (saved() === null) setTheme(deviceTheme());
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  const toggle = useCallback(() => {
    setTheme((now) => {
      const next: Theme = now === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(KEY, next);
      } catch {
        // storage blocked: the pick lasts until the page reloads
      }
      return next;
    });
  }, []);

  return { theme, toggle };
}
