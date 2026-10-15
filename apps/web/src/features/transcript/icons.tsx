// Small stroke icons for the player and transcript search. Decorative: callers label the buttons.

import type { ReactNode } from "react";

function Icon({ size = 18, children }: { size?: number; children: ReactNode }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  );
}

export function PlayIcon() {
  return (
    <Icon>
      <path d="M8 5.5v13l10.5-6.5z" fill="currentColor" />
    </Icon>
  );
}

export function PauseIcon() {
  return (
    <Icon>
      <path d="M8 5v14M16 5v14" strokeWidth={3} />
    </Icon>
  );
}

export function BackIcon() {
  return (
    <Icon>
      <path d="M3 12a9 9 0 1 0 3-6.7" />
      <path d="M3 4v5h5" />
    </Icon>
  );
}

export function ForwardIcon() {
  return (
    <Icon>
      <path d="M21 12a9 9 0 1 1-3-6.7" />
      <path d="M21 4v5h-5" />
    </Icon>
  );
}

export function SearchIcon() {
  return (
    <Icon size={16}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </Icon>
  );
}

export function ChevronUpIcon() {
  return (
    <Icon>
      <path d="m6 15 6-6 6 6" />
    </Icon>
  );
}

export function ChevronDownIcon() {
  return (
    <Icon>
      <path d="m6 9 6 6 6-6" />
    </Icon>
  );
}
