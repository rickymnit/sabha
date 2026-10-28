// Rupee amounts for the cost display, Indian digit grouping: "₹0.49", "₹14.20", "₹1,240.50".

const INR = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2,
                                             maximumFractionDigits: 2 }); // prettier-ignore

export function formatInr(amount: number): string {
  return INR.format(amount);
}

/** "+₹1.20 (+14%)", "−₹0.80 (−9%)": actual minus expected, and as a share of the expected. */
export function formatDifference(actual: number, expected: number): string {
  const diff = actual - expected;
  const sign = diff > 0 ? "+" : diff < 0 ? "−" : "";
  const pct = expected > 0 ? ` (${sign}${Math.abs(Math.round((diff / expected) * 100))}%)` : "";
  return `${sign}${formatInr(Math.abs(diff))}${pct}`;
}

/** The length of an audio or video file as the browser reads it, or null when it cannot be read in time. */
export function measureDuration(file: File, timeoutMs = 10_000): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const media = document.createElement(file.type.startsWith("video") ? "video" : "audio");
    const done = (ms: number | null) => {
      window.clearTimeout(timer);
      media.removeAttribute("src");
      URL.revokeObjectURL(url);
      resolve(ms);
    };
    const timer = window.setTimeout(() => done(null), timeoutMs);
    media.preload = "metadata";
    media.onloadedmetadata = () => done(Number.isFinite(media.duration) ? Math.round(media.duration * 1000) : null);
    media.onerror = () => done(null);
    media.src = url;
  });
}
