import type { Config } from "tailwindcss";

/** A colour token: a CSS variable holding "R G B", set for light and dark in src/theme.css, so opacity
 *  modifiers (bg-ink/40) still work. */
const v = (name: string) => `rgb(var(--c-${name}) / <alpha-value>)`;

// Every value here comes from docs/design/tokens.md (UI v2 since 2026-10-27); the dark set is in src/theme.css. Colours, font sizes and radii replace
// Tailwind's defaults (not extend them) so only design tokens are available.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      inherit: "inherit",
      ink: { DEFAULT: v("ink"), 2: v("ink-2"), raised: v("ink-raised") },
      muted: { DEFAULT: v("muted"), 2: v("muted-2") },
      subtle: v("subtle"),
      line: {
        DEFAULT: v("line"),
        strong: v("line-strong"),
        input: v("line-input"),
        subtle: v("line-subtle"),
      },
      track: v("track"),
      fill: { DEFAULT: v("fill"), 2: v("fill-2") },
      surface: { DEFAULT: v("surface"), subtle: v("surface-subtle"), faint: v("surface-faint") },
      page: v("page"),
      primary: {
        DEFAULT: v("primary"),
        hover: v("primary-hover"),
        tint: v("primary-tint"),
        "tint-subtle": v("primary-tint-subtle"),
        "tint-strong": v("primary-tint-strong"),
        border: v("primary-border"),
        disabled: v("primary-disabled"),
        "disabled-ink": v("primary-disabled-ink"),
      },
      "brand-accent": v("brand-accent"),
      // Text and icons on a primary background: white in light, deep ink on the lighter dark-mode primary.
      "on-primary": v("on-primary"),
      // The dimmed layer behind a dialog (used with an opacity, bg-scrim/40).
      scrim: v("scrim"),
      success: { DEFAULT: v("success"), bar: v("success-bar"), tint: v("success-tint") },
      warning: {
        DEFAULT: v("warning"),
        ink: v("warning-ink"),
        bar: v("warning-bar"),
        tint: v("warning-tint"),
        "tint-subtle": v("warning-tint-subtle"),
        surface: v("warning-surface"),
        border: v("warning-border"),
      },
      danger: { DEFAULT: v("danger"), bar: v("danger-bar"), tint: v("danger-tint") },
      type: {
        teaching: v("type-teaching"),
        reception: v("type-reception"),
        counselling: v("type-counselling"),
        meeting: v("type-meeting"),
        sales: v("type-sales"),
        support: v("type-support"),
      },
      // Who spoke when: the analysed staff member and everyone else (SpeakerStrip, report timeline).
      speaker: { staff: v("speaker-staff"), other: v("speaker-other") },
    },
    fontFamily: {
      sans: ["Geist", "'Segoe UI'", "system-ui", "sans-serif"],
    },
    fontSize: {
      "2xs": "11px",
      xs: "11.5px",
      caption: "12px",
      small: "12.5px",
      sm: "13px",
      table: "13.5px",
      base: ["14px", { lineHeight: "1.45" }],
      md: "15px",
      lg: "16px",
      brand: ["17px", { letterSpacing: "-0.01em" }],
      xl: "18px",
      "2xl": "20px",
      "3xl": ["24px", { letterSpacing: "-0.015em" }],
      title: ["26px", { lineHeight: "1.2", letterSpacing: "-0.015em" }],
      metric: ["28px", { letterSpacing: "-0.02em" }],
      hero: ["44px", { lineHeight: "1", letterSpacing: "-0.03em" }],
    },
    borderRadius: {
      none: "0",
      xs: "2px",
      sm: "3px",
      md: "6px",
      seg: "7px",
      DEFAULT: "8px",
      "seg-outer": "9px",
      card: "10px",
      panel: "12px",
      full: "999px",
    },
    extend: {
      spacing: {
        "4.5": "18px",
        sidebar: "232px",
      },
      minHeight: {
        touch: "44px",
      },
      minWidth: {
        touch: "44px",
      },
      boxShadow: {
        seg: "0 0 0 1px rgb(var(--c-line))",
      },
      // Motion is not in the designs; these are ours. Components apply them only under `motion-safe:`, so
      // people who ask for reduced motion get none.
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "100% 0" },
          "100%": { backgroundPosition: "-100% 0" },
        },
        "toast-in": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        shimmer: "shimmer 1.6s ease-in-out infinite",
        "toast-in": "toast-in 160ms ease-out",
      },
    },
  },
  plugins: [],
} satisfies Config;
