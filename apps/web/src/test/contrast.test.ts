// Colour contrast (P6.8), which jsdom cannot measure for the axe check (test/a11y.test.tsx): the WCAG 2.1 ratio of
// every text colour on the backgrounds the app sets it on, from the design tokens themselves (src/theme.css), in both
// the light and the dark theme.
// Body text needs 4.5:1 (AA); the pairs are the ones the components use.

import { describe, expect, it } from "vitest";

import themeCss from "../theme.css?raw";

type Theme = "light" | "dark";

/** The colour tokens of one theme, from src/theme.css: "ink" -> [18, 21, 33]. */
function palette(theme: Theme): Map<string, number[]> {
  const css = themeCss;
  const selector = theme === "light" ? ":root {" : ':root[data-theme="dark"] {';
  const block = css.slice(css.indexOf(selector), css.indexOf("}", css.indexOf(selector)));
  return new Map(
    [...block.matchAll(/--c-([\w-]+):\s*(\d+) (\d+) (\d+);/g)].map((m) => [m[1]!, [+m[2]!, +m[3]!, +m[4]!]]),
  );
}

const PALETTES = { light: palette("light"), dark: palette("dark") };

function rgb(theme: Theme, token: string): number[] {
  const value = PALETTES[theme].get(token);
  if (!value) throw new Error(`no colour token ${token} in the ${theme} theme`);
  return value;
}

function luminance(color: number[]): number {
  const [r, g, b] = color.map((c) => c / 255);
  const linear = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * linear(r!) + 0.7152 * linear(g!) + 0.0722 * linear(b!);
}

function contrast(theme: Theme, foreground: string, background: string): number {
  const [light, dark] = [luminance(rgb(theme, foreground)), luminance(rgb(theme, background))].sort((a, b) => b - a);
  return (light! + 0.05) / (dark! + 0.05);
}

const PLAIN_BACKGROUNDS = ["surface", "surface-subtle", "surface-faint", "page"];
const PAIRS: [string, string][] = [
  ...["ink", "ink-2", "muted", "muted-2", "primary", "primary-hover", "danger", "success", "warning-ink"].flatMap(
    (text) => PLAIN_BACKGROUNDS.map((bg): [string, string] => [text, bg]),
  ),
  ["primary-hover", "primary-tint"], // the current menu item
  ["primary", "primary-tint-subtle"],
  ["on-primary", "primary"], // buttons, the sign-in brand panel
  ["primary-tint", "primary"], // the sign-in panel's points
  ["danger", "danger-tint"], // errors, low score chips
  ["success", "success-tint"],
  ["warning-ink", "warning-tint"], // the Reviews badge, mid score chips
  ["warning-ink", "warning-surface"], // notes such as "Your session ended"
  ["warning-ink", "warning-tint-subtle"],
  ["surface", "ink"], // toasts
];

describe.each(["light", "dark"] as const)("colour contrast, %s theme", (theme) => {
  it.each(PAIRS)("%s text on %s meets WCAG AA (4.5:1)", (text, background) => {
    expect(contrast(theme, text, background)).toBeGreaterThanOrEqual(4.5);
  });

  it("has every token the other theme has", () => {
    expect([...PALETTES[theme].keys()].sort()).toEqual([...PALETTES.light.keys()].sort());
  });
});

it("computes the WCAG ratio", () => {
  expect(contrast("light", "ink", "ink")).toBeCloseTo(1);
  expect(contrast("light", "surface", "ink")).toBeGreaterThan(15); // near-black on white
});
