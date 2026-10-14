import type { ReactNode } from "react";

import { cx } from "./cx";

export interface Breadcrumb {
  label: ReactNode;
  /** Omit for the current page (the last crumb). */
  href?: string;
}

export interface PageHeaderProps {
  title: ReactNode;
  /** Heading element; h1 for the page title, h2 when showing the pattern inside another page. */
  titleAs?: "h1" | "h2";
  /** Subtitle under the title (Main.dc.html:89). */
  description?: ReactNode;
  /** Trail above the title (Upload.dc.html:79). */
  breadcrumbs?: Breadcrumb[];
  /** Accessible name of the breadcrumb nav. */
  breadcrumbLabel?: string;
  /** Extra content under the title, for example the report's details list (Analysis.dc.html:85-90). */
  meta?: ReactNode;
  /** Buttons and fields on the right (Main.dc.html:91-104). */
  actions?: ReactNode;
  className?: string;
}

/** Page title block: 26px / 700 h1 with subtitle, breadcrumbs and actions (Main.dc.html:86-105). */
export function PageHeader({
  title,
  titleAs: Title = "h1",
  description,
  breadcrumbs,
  breadcrumbLabel = "Breadcrumb",
  meta,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <header className={cx("flex flex-wrap items-end justify-between gap-4", className)}>
      <div className="flex min-w-0 flex-col gap-1">
        {breadcrumbs && breadcrumbs.length > 0 && (
          <nav aria-label={breadcrumbLabel} className="mb-1 text-sm text-muted">
            <ol className="m-0 flex flex-wrap gap-2 p-0">
              {breadcrumbs.map((crumb, i) => (
                <li key={i} className="flex gap-2">
                  {i > 0 && <span aria-hidden="true">/</span>}
                  {crumb.href ? (
                    <a href={crumb.href} className="no-underline hover:underline">
                      {crumb.label}
                    </a>
                  ) : (
                    <span aria-current={i === breadcrumbs.length - 1 ? "page" : undefined}>{crumb.label}</span>
                  )}
                </li>
              ))}
            </ol>
          </nav>
        )}
        <Title className="m-0 text-title font-bold">{title}</Title>
        {description && <p className="m-0 max-w-[72ch] text-muted">{description}</p>}
        {meta}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2.5">{actions}</div>}
    </header>
  );
}
