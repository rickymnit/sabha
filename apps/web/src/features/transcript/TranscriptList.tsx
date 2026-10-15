// Virtualised transcript: time, role and text per line (Analysis.dc.html:247-264). Only the lines in view (plus a
// few either side) are in the DOM, so a 3-hour recording's thousands of lines stay fast. The line being played is
// highlighted and kept in view; clicking a line, or Enter/Space on it, seeks the audio to its start.

import { defaultRangeExtractor, measureElement, useVirtualizer, type Range } from "@tanstack/react-virtual";
import {
  memo,
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import { Button, Input, cx } from "../../design";
import { ChevronDownIcon, ChevronUpIcon, SearchIcon } from "./icons";
import { findMatches, formatClock, lineAt, segmentText, type Match } from "./text";
import type { RoleLabels, Utterance } from "./types";

export interface TranscriptListProps {
  utterances: readonly Utterance[];
  /** Role keys to labels from the tenant's labels dictionary; roles missing here show their speaker label. */
  roles: RoleLabels;
  /** Playback position in milliseconds (original timeline); null when nothing has played yet. */
  currentMs: number | null;
  /** Called with a line's start_ms when the line is clicked or activated from the keyboard. */
  onSeek: (ms: number) => void;
  /** Accessible name of the list of lines. */
  label?: string;
  /** Height of the scrolling area (any CSS length). Default min(70vh, 640px). */
  height?: string;
  className?: string;
}

/** Most lines are one row of text: 10px + 20px + 10px padding (Analysis.dc.html:258) plus a little. */
const ESTIMATED_ROW_PX = 44;
const PAGE_LINES = 10;

const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

/** Hidden or not-yet-laid-out rows measure 0; keep the estimate instead of caching a zero height. */
const measureRow: typeof measureElement = (element, entry, instance) =>
  measureElement(element, entry, instance) || ESTIMATED_ROW_PX;

interface LineMatch {
  start: number;
  end: number;
  /** Position in the full list of matches. */
  index: number;
}

export function TranscriptList({
  utterances,
  roles,
  currentMs,
  onSeek,
  label = "Transcript lines",
  height = "min(70vh, 640px)",
  className,
}: TranscriptListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const onSeekRef = useRef(onSeek);
  useEffect(() => {
    onSeekRef.current = onSeek;
  });

  const [following, setFollowing] = useState(true);
  const [focusIndex, setFocusIndex] = useState(0);
  const [focusInside, setFocusInside] = useState(false);
  const pendingFocusRef = useRef(false);

  const currentIndex = currentMs === null ? -1 : lineAt(utterances, currentMs);
  // One line is in the tab order: the focused one while focus is in the list, otherwise the playing one.
  const tabLine = Math.min(utterances.length - 1, focusInside || currentIndex < 0 ? focusIndex : currentIndex);

  // Search.
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const matches = useMemo(() => findMatches(utterances, deferredQuery), [utterances, deferredQuery]);
  const [activeMatch, setActiveMatch] = useState(0);
  const active = matches.length ? Math.min(activeMatch, matches.length - 1) : -1;
  const matchesByLine = useMemo(() => {
    const byLine = new Map<number, LineMatch[]>();
    matches.forEach((m: Match, index) => {
      const list = byLine.get(m.line) ?? [];
      list.push({ start: m.start, end: m.end, index });
      byLine.set(m.line, list);
    });
    return byLine;
  }, [matches]);

  const rangeExtractor = useCallback(
    (range: Range) => {
      const indexes = defaultRangeExtractor(range);
      // Keep the tabbable line mounted so keyboard users can always Tab into the list.
      if (tabLine >= 0 && !indexes.includes(tabLine)) indexes.push(tabLine);
      return indexes;
    },
    [tabLine],
  );

  // useVirtualizer returns a mutable instance; nothing here memoises values derived from it.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: utterances.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ESTIMATED_ROW_PX,
    overscan: 6,
    rangeExtractor,
    measureElement: measureRow,
  });

  const scrollToLine = useCallback(
    (index: number, align: "center" | "auto") => {
      virtualizer.scrollToIndex(index, { align, behavior: prefersReducedMotion() ? "auto" : "smooth" });
    },
    [virtualizer],
  );

  // Keep the playing line in view while following.
  useEffect(() => {
    if (!following || currentIndex < 0) return;
    const scroller = scrollRef.current;
    const item = virtualizer.measurementsCache[currentIndex];
    if (!scroller || !item) return;
    const top = scroller.scrollTop;
    if (item.start >= top && item.end <= top + scroller.clientHeight) return;
    scrollToLine(currentIndex, "center");
  }, [currentIndex, following, virtualizer, scrollToLine]);

  // Move focus to a line chosen with the keyboard once it is mounted.
  useEffect(() => {
    if (!pendingFocusRef.current) return;
    pendingFocusRef.current = false;
    scrollRef.current?.querySelector<HTMLElement>(`[data-line="${focusIndex}"]`)?.focus({ preventScroll: true });
  }, [focusIndex]);

  const goToMatch = (index: number) => {
    const match = matches[index];
    if (!match) return;
    setActiveMatch(index);
    setFollowing(false);
    scrollToLine(match.line, "center");
  };

  // Show the first hit as the query changes.
  useEffect(() => {
    const first = matches[0];
    if (first) virtualizer.scrollToIndex(first.line, { align: "center" });
  }, [matches, virtualizer]);

  const activate = useCallback(
    (index: number) => {
      const utterance = utterances[index];
      if (!utterance) return;
      // A click that ends a text selection is for copying a quote, not for seeking.
      const selection = window.getSelection();
      if (selection && !selection.isCollapsed && scrollRef.current?.contains(selection.anchorNode)) return;
      setFocusIndex(index);
      setFollowing(true);
      onSeekRef.current(utterance.start_ms);
    },
    [utterances],
  );

  const onLineKeyDown = useCallback(
    (index: number, event: KeyboardEvent<HTMLElement>) => {
      let next: number;
      switch (event.key) {
        case "Enter":
        case " ":
          event.preventDefault();
          activate(index);
          return;
        case "ArrowDown":
          next = index + 1;
          break;
        case "ArrowUp":
          next = index - 1;
          break;
        case "PageDown":
          next = index + PAGE_LINES;
          break;
        case "PageUp":
          next = index - PAGE_LINES;
          break;
        case "Home":
          next = 0;
          break;
        case "End":
          next = utterances.length - 1;
          break;
        default:
          return;
      }
      event.preventDefault();
      const target = Math.max(0, Math.min(utterances.length - 1, next));
      pendingFocusRef.current = true;
      setFollowing(false);
      setFocusIndex(target);
      virtualizer.scrollToIndex(target, { align: "auto" });
    },
    [activate, utterances.length, virtualizer],
  );

  const stopFollowing = () => {
    if (following) setFollowing(false);
  };

  const hasHours = (utterances[utterances.length - 1]?.end_ms ?? 0) >= 3_600_000;
  const items = virtualizer.getVirtualItems();
  const trimmedQuery = deferredQuery.trim();

  return (
    <div className={cx("flex min-w-0 flex-col", className)}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line-subtle px-5 py-3">
        <Input
          type="search"
          label="Search the transcript"
          hideLabel
          placeholder="Search the transcript"
          leadingIcon={<SearchIcon />}
          value={query}
          onChange={(e) => {
            setQuery(e.currentTarget.value);
            setActiveMatch(0);
            if (e.currentTarget.value.trim()) setFollowing(false);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && matches.length) {
              e.preventDefault();
              goToMatch((active + (e.shiftKey ? matches.length - 1 : 1)) % matches.length);
            } else if (e.key === "Escape" && query) {
              e.preventDefault();
              setQuery("");
            }
          }}
          className="min-w-[200px] max-w-sm flex-1"
        />
        <span aria-live="polite" className="min-w-[88px] text-sm text-muted">
          {trimmedQuery ? (matches.length ? `${active + 1} of ${matches.length}` : "No matches") : ""}
        </span>
        <div className="flex gap-1">
          <Button
            variant="secondary"
            aria-label="Previous match"
            disabled={matches.length === 0}
            onClick={() => goToMatch((active - 1 + matches.length) % matches.length)}
            className="px-0"
          >
            <ChevronUpIcon />
          </Button>
          <Button
            variant="secondary"
            aria-label="Next match"
            disabled={matches.length === 0}
            onClick={() => goToMatch((active + 1) % matches.length)}
            className="px-0"
          >
            <ChevronDownIcon />
          </Button>
        </div>
        {!following && currentIndex >= 0 && (
          <Button
            variant="ghost"
            onClick={() => {
              setFollowing(true);
              scrollToLine(currentIndex, "center");
            }}
          >
            Back to the playing line
          </Button>
        )}
        <p className="m-0 ml-auto text-caption text-muted">
          <span className="underline decoration-muted-2 decoration-dotted underline-offset-4">Dotted underline</span>:
          words the speech recogniser was unsure of
        </p>
      </div>
      <div
        ref={scrollRef}
        data-transcript-scroller=""
        className="relative overflow-y-auto overscroll-contain"
        style={{ height }}
        onWheel={stopFollowing}
        onTouchMove={stopFollowing}
        onMouseDown={(e) => {
          if (e.target === e.currentTarget) stopFollowing(); // dragging the scrollbar
        }}
        onFocus={() => setFocusInside(true)}
        onBlur={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget)) setFocusInside(false);
        }}
      >
        <div role="list" aria-label={label} className="relative w-full" style={{ height: virtualizer.getTotalSize() }}>
          {items.map((item) => {
            const utterance = utterances[item.index] as Utterance;
            return (
              <div
                key={item.key}
                role="listitem"
                aria-setsize={utterances.length}
                aria-posinset={item.index + 1}
                data-index={item.index}
                ref={virtualizer.measureElement}
                className="absolute left-0 top-0 w-full"
                style={{ transform: `translateY(${item.start}px)` }}
              >
                <Line
                  index={item.index}
                  utterance={utterance}
                  roleInfo={roles[utterance.role]}
                  current={item.index === currentIndex}
                  tabbable={item.index === tabLine}
                  wideTime={hasHours}
                  matches={matchesByLine.get(item.index)}
                  activeMatch={active}
                  onActivate={activate}
                  onKeyDown={onLineKeyDown}
                />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

interface LineProps {
  index: number;
  utterance: Utterance;
  roleInfo: RoleLabels[string] | undefined;
  current: boolean;
  tabbable: boolean;
  wideTime: boolean;
  matches: LineMatch[] | undefined;
  activeMatch: number;
  onActivate: (index: number) => void;
  onKeyDown: (index: number, event: KeyboardEvent<HTMLElement>) => void;
}

const Line = memo(function Line({
  index,
  utterance,
  roleInfo,
  current,
  tabbable,
  wideTime,
  matches,
  activeMatch,
  onActivate,
  onKeyDown,
}: LineProps) {
  const lineMatches = matches ?? [];
  const segments = segmentText(utterance.text, utterance.low_confidence_spans, lineMatches);
  const roleClass = !roleInfo ? "text-muted" : roleInfo.analysed ? "text-primary" : "text-warning";

  return (
    <div
      role="button"
      tabIndex={tabbable ? 0 : -1}
      aria-current={current ? "true" : undefined}
      data-line={index}
      onClick={() => onActivate(index)}
      onKeyDown={(e) => onKeyDown(index, e)}
      className={cx(
        // Current line: Analysis.dc.html:255 (warning-surface background, 3px reception-amber bar).
        // On narrow screens the text wraps under the time and role instead of squeezing beside them.
        "flex cursor-pointer flex-wrap gap-x-4 gap-y-0.5 border-l-[3px] px-5 py-2.5 focus-visible:outline-offset-[-2px] sm:flex-nowrap",
        current ? "border-type-reception bg-warning-surface" : "border-transparent hover:bg-surface-subtle",
      )}
    >
      <span className={cx("shrink-0 pt-px text-small text-muted", wideTime ? "w-14" : "w-11")}>
        <span className="sr-only">Play from </span>
        {formatClock(utterance.start_ms)}
      </span>
      <span className={cx("w-24 shrink-0 text-sm font-semibold", roleClass)}>
        {roleInfo?.label ?? utterance.speaker_label}
      </span>
      <span className="min-w-0 max-w-[80ch] basis-full text-ink sm:flex-1 sm:basis-0">
        {segments.map((segment, i) => {
          let node: ReactNode = segment.text;
          if (segment.lowConfidence) {
            node = (
              <span
                className="underline decoration-muted-2 decoration-dotted underline-offset-4"
                title="The speech recogniser was unsure of these words"
              >
                {node}
              </span>
            );
          }
          if (segment.match !== undefined) {
            const isActive = lineMatches[segment.match]?.index === activeMatch;
            node = (
              <mark
                data-active-match={isActive ? "" : undefined}
                className={cx("rounded-xs", isActive ? "bg-primary text-surface" : "bg-primary-tint-strong text-ink")}
              >
                {node}
              </mark>
            );
          }
          return <span key={i}>{node}</span>;
        })}
      </span>
    </div>
  );
});
