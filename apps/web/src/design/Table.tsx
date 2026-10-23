import { useId, type ReactNode } from "react";

import { cx } from "./cx";

export interface TableColumn<Row> {
  key: string;
  header: ReactNode;
  /** Keep the header for screen readers but hide it on screen (a "Download" link column, Plans.dc.html:211). */
  hideHeader?: boolean;
  align?: "left" | "right";
  render: (row: Row) => ReactNode;
  /** Extra classes for this column's body cells. */
  className?: string;
  /** Hide the whole column on phones (below Tailwind's `md`, 768px) so the table fits without scrolling. */
  hideOnPhone?: boolean;
}

type Naming =
  | { /** Caption describing the table. */ caption: ReactNode; captionHidden?: boolean; "aria-label"?: never }
  | { "aria-label": string; caption?: never; captionHidden?: never };

export type TableProps<Row> = Naming & {
  columns: TableColumn<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
  /** Below this width the table scrolls sideways instead of squeezing (Main.dc.html:162-163). */
  minWidth?: number;
  /** Shown in a single full-width row when there are no rows. */
  empty?: ReactNode;
  /** Extra classes for each body row, for example a hover tint when the row links somewhere. */
  rowClassName?: string;
  className?: string;
};

// Main.dc.html:164-178: 12.5px / 500 muted headers over a line-subtle rule, 13.5px body, track row dividers,
// cells padded 12px with 20px at the row ends.
const edge = (i: number, count: number) => cx(i === 0 ? "pl-5" : "pl-3", i === count - 1 ? "pr-5" : "pr-3");

/** Data table in a horizontally scrolling, keyboard-focusable region. Header cells are <th scope="col">. */
export function Table<Row>({
  columns,
  rows,
  rowKey,
  minWidth = 820,
  empty,
  rowClassName,
  className,
  caption,
  captionHidden = false,
  "aria-label": ariaLabel,
}: TableProps<Row>) {
  const captionId = useId();
  return (
    // tabIndex lets keyboard users scroll the region when the table is wider than the screen. `relative` keeps
    // absolutely positioned descendants (sr-only text) inside the scroller instead of widening the page.
    <div
      role="region"
      tabIndex={0}
      aria-labelledby={caption ? captionId : undefined}
      aria-label={caption ? undefined : ariaLabel}
      className={cx("relative overflow-x-auto", className)}
    >
      <table className="w-full border-collapse text-table" style={{ minWidth }} aria-label={ariaLabel}>
        {caption && (
          <caption
            id={captionId}
            className={captionHidden ? "sr-only" : "px-5 pb-2 pt-3 text-left text-sm font-semibold text-ink"}
          >
            {caption}
          </caption>
        )}
        <thead>
          <tr className="text-small text-muted">
            {columns.map((col, i) => (
              <th
                key={col.key}
                scope="col"
                className={cx(
                  "border-b border-line-subtle py-2.5 font-medium",
                  edge(i, columns.length),
                  col.align === "right" ? "text-right" : "text-left",
                  col.hideOnPhone && "hidden md:table-cell",
                )}
              >
                {col.hideHeader ? <span className="sr-only">{col.header}</span> : col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && empty !== undefined ? (
            <tr>
              <td colSpan={columns.length} className="px-5 py-3">
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={rowKey(row)} className={rowClassName}>
                {columns.map((col, i) => (
                  <td
                    key={col.key}
                    className={cx(
                      "border-b border-track py-3 text-ink-2",
                      edge(i, columns.length),
                      col.align === "right" && "text-right",
                      col.hideOnPhone && "hidden md:table-cell",
                      col.className,
                    )}
                  >
                    {col.render(row)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
