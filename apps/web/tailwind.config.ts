import type { Config } from "tailwindcss";

// Every value here comes from docs/design/tokens.md (UI v2 since 2026-10-27). Colours, font sizes and radii replace
// Tailwind's defaults (not extend them) so only design tokens are available.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      inherit: "inherit",
      ink: { DEFAULT: "#121521", 2: "#3D414C", raised: "#262B3E" },
      muted: { DEFAULT: "#5F6677", 2: "#686F7F" },
      subtle: "#686F7F",
      line: {
        DEFAULT: "#E4E7EC",
        strong: "#B8BDC7",
        input: "#D7D8DC",
        subtle: "#ECEEF2",
      },
      track: "#EEF0F3",
      fill: { DEFAULT: "#F1F2F5", 2: "#E9EBEF" },
      surface: { DEFAULT: "#FFFFFF", subtle: "#F6F7F9", faint: "#FAFBFC" },
      page: "#F6F7F9",
      primary: {
        DEFAULT: "#3346D3",
        hover: "#2536B0",
        tint: "#EEF0FC",
        "tint-subtle": "#F5F5FD",
        "tint-strong": "#DDE2F8",
        border: "#B9C1F0",
        disabled: "#C9CEF2",
        "disabled-ink": "#2F3A86",
      },
      "brand-accent": "#F2A33A",
      success: { DEFAULT: "#0B6343", bar: "#1F9A6B", tint: "#DDF1E6" },
      warning: {
        DEFAULT: "#7A4A00",
        ink: "#7A4A00",
        bar: "#E8A23F",
        tint: "#FCEBCF",
        "tint-subtle": "#FEF6E9",
        surface: "#FEFAF1",
        border: "#ECD9B8",
      },
      danger: { DEFAULT: "#A12B12", bar: "#DB532E", tint: "#FBE2DB" },
      type: {
        teaching: "#3346D3",
        reception: "#F2A33A",
        counselling: "#1E7A55",
        meeting: "#7A4DB8",
        sales: "#0F7C8C",
      },
      // Who spoke when: the analysed staff member and everyone else (SpeakerStrip, report timeline).
      speaker: { staff: "#3346D3", other: "#F2A33A" },
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
        seg: "0 0 0 1px #E4E7EC",
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
