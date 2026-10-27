// The header search (UI v2, docs/design/v2/01-overview.png): people and recordings by name, from what the signed-in
// person may see (GET /v1/search). Names only, by the owner's choice: what was said is not searched, so the
// placeholder does not promise it. Ctrl K (Cmd K on a Mac) focuses it; arrows move through the results, Enter opens
// one, Escape closes the list. ARIA combobox pattern with a listbox.

import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useSearch } from "../api/hooks";
import type { Me } from "../api/types";
import { Avatar, Icon, cx } from "../design";
import { capitalise } from "./format";

interface Option {
  key: string;
  to: string;
  title: string;
  detail: string;
}

// navigator.platform is deprecated: prefer User-Agent Client Hints (Chromium), fall back to the user-agent string.
const platform =
  typeof navigator === "undefined"
    ? ""
    : ((navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData?.platform ??
      navigator.userAgent);
const isMac = /Mac|iPhone|iPad/i.test(platform);

export function HeaderSearch({ me }: { me: Me }) {
  const labels = me.tenant.labels;
  const navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const search = useSearch(query);
  const units = new Map(me.tenant.units.map((u) => [u.id, u.name]));

  // Wait for a short pause in typing before asking the API.
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(text), 200);
    return () => window.clearTimeout(timer);
  }, [text]);

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        input.current?.focus();
        input.current?.select();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const people: Option[] = (search.data?.people ?? []).map((p) => ({
    key: `p-${p.id}`,
    to: `/recordings?person=${encodeURIComponent(p.id)}`,
    title: p.name,
    detail: (p.unit_id && units.get(p.unit_id)) || capitalise(labels.person),
  }));
  const recordings: Option[] = (search.data?.recordings ?? []).map((r) => ({
    key: `r-${r.id}`,
    to: `/recordings/${r.id}`,
    title: r.title,
    detail: [r.person?.name, r.unit_id ? units.get(r.unit_id) : undefined].filter(Boolean).join(", "),
  }));
  const options = [...people, ...recordings];
  const ready = query.trim().length >= 2 && search.isSuccess;
  const showList = open && text.trim().length >= 2 && ready;

  const choose = (option: Option) => {
    setOpen(false);
    setText("");
    input.current?.blur();
    navigate(option.to);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      if (options.length) {
        const step = event.key === "ArrowDown" ? 1 : -1;
        setActive((i) => (i + step + options.length) % options.length);
      }
    } else if (event.key === "Enter" && showList && options[active]) {
      event.preventDefault();
      choose(options[active]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  const group = (title: string, items: Option[], offset: number) =>
    items.length > 0 && (
      <li role="presentation">
        <p className="m-0 px-3 pb-1 pt-2.5 text-caption font-semibold text-muted">{title}</p>
        <ul role="group" aria-label={title} className="m-0 list-none p-0">
          {items.map((option, i) => (
            <li
              key={option.key}
              id={`${listId}-${offset + i}`}
              role="option"
              aria-selected={active === offset + i}
              // mousedown, not click: the input's blur would close the list before a click lands
              onMouseDown={(event) => {
                event.preventDefault();
                choose(option);
              }}
              onMouseEnter={() => setActive(offset + i)}
              className={cx(
                "flex min-h-touch cursor-pointer items-center gap-2.5 px-3 py-1.5",
                active === offset + i && "bg-primary-tint",
              )}
            >
              <Avatar name={option.title} size={28} />
              <span className="flex min-w-0 flex-col">
                <span className="truncate text-sm font-semibold text-ink">{option.title}</span>
                {option.detail && <span className="truncate text-caption text-muted">{option.detail}</span>}
              </span>
            </li>
          ))}
        </ul>
      </li>
    );

  return (
    <div className="relative w-full max-w-[420px]">
      <label className="flex min-h-touch items-center gap-2 rounded border border-line bg-surface-subtle px-3 focus-within:border-primary focus-within:bg-surface">
        <Icon name="search" size={16} className="shrink-0 text-muted-2" />
        <span className="sr-only">
          Search {labels.person_plural} and {labels.recording_plural}
        </span>
        <input
          ref={input}
          type="search"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={showList && options[active] ? `${listId}-${active}` : undefined}
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setActive(0);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={onKeyDown}
          placeholder={`Search ${labels.person_plural.toLowerCase()} and ${labels.recording_plural.toLowerCase()}`}
          className="min-w-0 flex-1 border-0 bg-transparent text-sm text-ink placeholder:text-muted-2 focus-visible:outline-none"
        />
        <kbd
          aria-hidden="true"
          className="hidden shrink-0 rounded-sm border border-line bg-surface px-1.5 font-sans text-caption text-muted md:inline"
        >
          {isMac ? "⌘ K" : "Ctrl K"}
        </kbd>
      </label>
      <ul
        id={listId}
        role="listbox"
        aria-label="Search results"
        hidden={!showList}
        className="absolute inset-x-0 top-full z-30 m-0 mt-1 max-h-[420px] list-none overflow-auto rounded-card border border-line bg-surface p-0 pb-1.5 shadow-lg"
      >
        {group(capitalise(labels.person_plural), people, 0)}
        {group(capitalise(labels.recording_plural), recordings, people.length)}
        {options.length === 0 && (
          <li role="presentation" className="px-3 py-3 text-sm text-muted">
            No {labels.person_plural.toLowerCase()} or {labels.recording_plural.toLowerCase()} match “{query.trim()}”
          </li>
        )}
      </ul>
    </div>
  );
}
