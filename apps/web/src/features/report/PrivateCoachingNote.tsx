// Shown to managers, reviewers, owners and admins where a report's coaching would be: coaching is private to the
// person analysed (founder's rule, 2026-11-12). They still see the scores, evidence and summary.

export function PrivateCoachingNote({ firstName }: { firstName: string }) {
  return (
    <p
      data-testid="coaching-private"
      className="m-0 flex items-start gap-2 rounded-card bg-surface-faint px-3.5 py-2.5 text-small text-muted"
    >
      <svg aria-hidden="true" viewBox="0 0 16 16" className="mt-px h-4 w-4 shrink-0" fill="none" stroke="currentColor">
        <rect x="3" y="7" width="10" height="7" rx="1.5" strokeWidth="1.5" />
        <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" strokeWidth="1.5" />
      </svg>
      <span>
        {firstName}’s coaching tips are private to {firstName}. You see the scores, the evidence and the summary.
      </span>
    </p>
  );
}
