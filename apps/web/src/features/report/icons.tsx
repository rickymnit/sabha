// Small icons for the report page (Analysis.dc.html:215, :230). Decorative: callers label the controls.

export function SmallPauseIcon() {
  return (
    <svg aria-hidden="true" focusable="false" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
      <path d="M6 4h4v16H6zM14 4h4v16h-4z" />
    </svg>
  );
}

export function SmallPlayIcon() {
  return (
    <svg aria-hidden="true" focusable="false" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
      <path d="M7 4l13 8-13 8z" />
    </svg>
  );
}

/** "Go to" a transcript line when there is no audio to play. */
export function SmallGoIcon() {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

export function CheckIcon() {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  );
}
