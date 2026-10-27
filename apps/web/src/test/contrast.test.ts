// Colour contrast (P6.8), which jsdom cannot measure for the axe check (test/a11y.test.tsx): the WCAG 2.1 ratio of
// every text colour on the backgrounds the app sets it on, from the design tokens themselves (tailwind.config.ts).
// Body text needs 4.5:1 (AA); the pairs are the ones the components use.

import { describe, expect, it } from "vitest";

import config from "../../tailwind.config";

type Palette = Record<string, string | Record<string, string>>;
const colors = config.theme.colors as unknown as Palette;

/** A token's hex value: "ink" -> ink.DEFAULT, "muted-2" -> muted["2"], "warning-ink" -> warning.ink. */
function hex(token: string): string {
  const direct = colors[token];
  if (typeof direct === "string") return direct;
  if (direct) return direct.DEFAULT as string;
  for (let cut = token.lastIndexOf("-"); cut > 0; cut = token.lastIndexOf("-", cut - 1)) {
    const group = colors[token.slice(0, cut)];
    const value = typeof group === "object" ? group[token.slice(cut + 1)] : undefined;
    if (value) return value;
  }
  throw new Error(`no colour token ${token}`);
}

function luminance(color: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16) / 255);
  const linear = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * linear(r!) + 0.7152 * linear(g!) + 0.0722 * linear(b!);
}

function contrast(foreground: string, background: string): number {
  const [light, dark] = [luminance(hex(foreground)), luminance(hex(background))].sort((a, b) => b - a);
  return (light! + 0.05) / (dark! + 0.05);
}

const PLAIN_BACKGROUNDS = ["surface", "surface-subtle", "surface-faint", "page"];
const PAIRS: [string, string][] = [
  ...["ink", "ink-2", "muted", "muted-2", "primary", "primary-hover", "danger", "success", "warning-ink"].flatMap(
    (text) => PLAIN_BACKGROUNDS.map((bg): [string, string] => [text, bg]),
  ),
  ["primary-hover", "primary-tint"], // the current menu item
  ["primary", "primary-tint-subtle"],
  ["surface", "primary"], // buttons, the sign-in brand panel
  ["primary-tint", "primary"], // the sign-in panel's points
  ["danger", "danger-tint"], // errors, low score chips
  ["success", "success-tint"],
  ["warning-ink", "warning-tint"], // the Reviews badge, mid score chips
  ["warning-ink", "warning-surface"], // notes such as "Your session ended"
  ["warning-ink", "warning-tint-subtle"],
  ["surface", "ink"], // toasts
];

describe("colour contrast", () => {
  it.each(PAIRS)("%s text on %s meets WCAG AA (4.5:1)", (text, background) => {
    expect(contrast(text, background)).toBeGreaterThanOrEqual(4.5);
  });

  it("computes the WCAG ratio", () => {
    expect(contrast("ink", "ink")).toBeCloseTo(1);
    expect(contrast("surface", "ink")).toBeGreaterThan(15); // near-black on white
  });
});
