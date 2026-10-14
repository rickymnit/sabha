/** Joins class names, skipping falsy values. Full class names only, so Tailwind can see them. */
export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}
