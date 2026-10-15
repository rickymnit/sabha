import type { Dimension, VerifiedDimension } from "./types";

/**
 * The dimensions the report may show: verified, scored 1 to 5, with at least one quote. Payloads come from the
 * network, so this checks the values themselves rather than trusting the type.
 */
export function visibleDimensions(dimensions: readonly Dimension[]): VerifiedDimension[] {
  return dimensions.filter(
    (d): d is VerifiedDimension =>
      d.verified === true &&
      typeof d.score === "number" &&
      d.score >= 1 &&
      d.score <= 5 &&
      Array.isArray(d.evidence) &&
      d.evidence.length > 0,
  );
}
