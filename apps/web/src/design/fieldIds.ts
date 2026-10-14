/** The `aria-describedby` value for a control rendered inside Field. */
export function describedBy(id: string, hint: unknown, error: unknown, extra?: string): string | undefined {
  const ids = [extra, hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean);
  return ids.length ? ids.join(" ") : undefined;
}
