// Remembers, for the sign-in page, that the session ended on its own (the API answered 401) rather than by signing
// out, so it can say so instead of appearing without explanation. Per tab; storage may be unavailable.

const KEY = "sabha.session_ended";

export function markSessionEnded(): void {
  try {
    sessionStorage.setItem(KEY, "1");
  } catch {
    // nothing to remember it in: the sign-in page simply shows no note
  }
}

/** Whether the session ended on its own; reading it clears it, so the note shows once. */
export function takeSessionEnded(): boolean {
  try {
    const ended = sessionStorage.getItem(KEY) === "1";
    sessionStorage.removeItem(KEY);
    return ended;
  } catch {
    return false;
  }
}
