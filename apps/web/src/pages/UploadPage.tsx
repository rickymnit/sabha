// /upload (docs/design/03-upload.png): drop or choose several files, see each one's progress, and send them with
// one set of settings. Files go up one at a time, straight to storage (upload.ts, golden rule 2); the list and its
// rules are upload/queue.ts. Consent (golden rule 9): with no consent reference a recording is uploaded but waits,
// unprocessed, until consent is recorded; the page says so before and after.
// Not in this version: resuming after the page is closed, so the page asks people to keep it open.

import { useReducer, useRef, useState, type DragEvent } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../api/client";
import { usePeople } from "../api/hooks";
import type { Me } from "../api/types";
import {
  Button,
  ChoiceCards,
  Icon,
  Input,
  PageHeader,
  Panel,
  ProgressBar,
  Select,
  cx,
  type ConversationType,
} from "../design";
import { useSession } from "../session/session";
import { capitalise } from "../app/format";
import { uploadRecording } from "./upload/upload";
import { ACCEPT_ATTRIBUTE, formatSize, queueReducer, summarise, summaryText, type QueueItem } from "./upload/queue";

const CONSENT_KEY = "sabha.upload.consent_ref";

/** The last consent reference used on this device, so a teacher need not type the same form number each time. */
function rememberedConsent(): string {
  try {
    return localStorage.getItem(CONSENT_KEY) ?? "";
  } catch {
    return "";
  }
}

function remember(consentRef: string) {
  try {
    localStorage.setItem(CONSENT_KEY, consentRef);
  } catch {
    // Storage blocked: nothing to remember, nothing lost.
  }
}

function FileRow({
  item,
  onRemove,
  onRetry,
  onForce,
  onSkip,
  onOpen,
}: {
  item: QueueItem;
  onRemove: () => void;
  onRetry: () => void;
  onForce: () => void;
  onSkip: () => void;
  onOpen: (id: string) => void;
}) {
  // prettier-ignore
  const { file, state } = item;
  const tone =
    state.kind === "done"
      ? "bg-success-tint text-success"
      : state.kind === "invalid" || state.kind === "failed"
        ? "bg-danger-tint text-danger"
        : state.kind === "duplicate"
          ? "bg-warning-tint text-warning-ink"
          : "bg-primary-tint text-primary";
  return (
    <li className="flex items-start gap-3.5 border-b border-track px-5 py-3.5 last:border-b-0">
      <span
        aria-hidden="true"
        className={cx("mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded", tone)}
      >
        <Icon name="recordings" />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3">
          <span className="min-w-0 truncate font-semibold text-ink">{file.name}</span>
          <span className="shrink-0 text-small text-muted">{formatSize(file.size)}</span>
        </div>
        {state.kind === "ready" && <span className="text-small text-muted">Ready to upload</span>}
        {state.kind === "uploading" && (
          <ProgressBar
            value={state.sent}
            max={state.total || 1}
            label={state.sent === 0 ? "Preparing" : "Uploading"}
            showLabel
            className="max-w-xl"
          />
        )}
        {state.kind === "done" && (
          <span className="text-small text-success">
            {state.awaitingConsent
              ? "Uploaded. Waiting for consent before it is processed."
              : "Uploaded. Sabha is processing it now."}{" "}
            <button
              type="button"
              onClick={() => onOpen(state.recordingId)}
              className="font-semibold text-primary underline hover:text-primary-hover"
            >
              Open
            </button>
          </span>
        )}
        {state.kind === "invalid" && <span className="text-small text-danger">{state.reason}</span>}
        {state.kind === "failed" && (
          <span className="text-small text-danger">
            {state.message}{" "}
            <button type="button" onClick={onRetry} className="font-semibold text-primary underline">
              Try again
            </button>
          </span>
        )}
        {state.kind === "duplicate" && (
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-small text-warning-ink">
            This file has been uploaded before.
            <button type="button" onClick={onForce} className="font-semibold text-primary underline">
              Upload it again
            </button>
            <button type="button" onClick={onSkip} className="font-semibold text-primary underline">
              Skip it
            </button>
          </span>
        )}
      </div>
      {state.kind !== "uploading" && state.kind !== "done" && (
        <Button variant="secondary" aria-label={`Remove ${file.name}`} onClick={onRemove} className="shrink-0 px-0">
          <Icon name="close" size={16} />
        </Button>
      )}
    </li>
  );
}

export function UploadPage() {
  const me = useOutletContext<Me>();
  const labels = me.tenant.labels;
  const { token } = useSession();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const people = usePeople();
  const input = useRef<HTMLInputElement>(null);
  const [items, dispatch] = useReducer(queueReducer, []);
  const [dragging, setDragging] = useState(false);
  const [running, setRunning] = useState(false);
  const [type, setType] = useState<ConversationType>(me.tenant.enabled_types[0] ?? "teaching");
  const [personId, setPersonId] = useState("");
  const [consentOnFile, setConsentOnFile] = useState(() => rememberedConsent() !== "");
  const [consentRef, setConsentRef] = useState(rememberedConsent);

  const staffSelf = me.user.role === "staff";
  const onlyPerson = people.data?.length === 1 ? people.data[0] : undefined;
  const chosenPerson = personId || onlyPerson?.id || "";
  const summary = summarise(items);
  const consent = consentOnFile ? consentRef.trim() : "";
  const consentMissing = consentOnFile && consent === "";
  const canStart = summary.ready > 0 && !running && chosenPerson !== "" && !consentMissing;
  const things = summary.ready === 1 ? labels.recording.toLowerCase() : labels.recording_plural.toLowerCase();

  const add = (files: FileList | null) => {
    if (files && files.length) dispatch({ type: "add", files: [...files] });
  };
  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    if (!running) add(event.dataTransfer.files);
  };

  const sendOne = async (item: QueueItem) => {
    dispatch({ type: "set", key: item.key, state: { kind: "uploading", sent: 0, total: item.file.size } });
    try {
      const outcome = await uploadRecording({
        file: item.file,
        type,
        personId: chosenPerson || null,
        consentRef: consent || null,
        token,
        onProgress: (sent, total) =>
          dispatch({ type: "set", key: item.key, state: { kind: "uploading", sent, total } }),
      });
      if (outcome.kind === "duplicate") {
        dispatch({ type: "set", key: item.key, state: { kind: "duplicate", confirm: outcome.confirm } });
      } else {
        const { recording_id, awaiting_consent } = outcome.result;
        dispatch({ type: "set", key: item.key, state: { kind: "done", recordingId: recording_id, awaitingConsent: awaiting_consent } }); // prettier-ignore
      }
    } catch (error) {
      const message =
        error instanceof ApiError && error.code !== "upload_failed"
          ? error.message
          : "The upload was interrupted. Check the internet connection and try again.";
      dispatch({ type: "set", key: item.key, state: { kind: "failed", message } });
    }
  };

  const start = async () => {
    if (consent) remember(consent);
    setRunning(true);
    for (const item of items.filter((i) => i.state.kind === "ready")) await sendOne(item);
    setRunning(false);
    await queryClient.invalidateQueries({ queryKey: ["recordings"] });
  };

  const force = async (item: QueueItem) => {
    if (item.state.kind !== "duplicate") return;
    const confirm = item.state.confirm;
    dispatch({ type: "set", key: item.key, state: { kind: "uploading", sent: item.file.size, total: item.file.size } });
    try {
      const result = await confirm();
      dispatch({ type: "set", key: item.key, state: { kind: "done", recordingId: result.recording_id, awaitingConsent: result.awaiting_consent } }); // prettier-ignore
      await queryClient.invalidateQueries({ queryKey: ["recordings"] });
    } catch (error) {
      dispatch({ type: "set", key: item.key, state: { kind: "failed", message: error instanceof Error ? error.message : "The upload failed." } }); // prettier-ignore
    }
  };

  const allDone = items.length > 0 && summary.done === items.length;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumbs={[{ label: capitalise(labels.recording_plural), href: "/recordings" }, { label: "Upload" }]}
        title="Upload recordings"
        description="Files go straight to secure storage in India. Keep this page open until every file says uploaded."
      />
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="flex min-w-0 flex-col gap-5">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              if (!running) setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={cx(
              "flex flex-col items-center gap-3 rounded-panel border-2 border-dashed px-6 py-10 text-center",
              dragging ? "border-primary bg-primary-tint-subtle" : "border-line-strong bg-surface",
            )}
          >
            <span
              aria-hidden="true"
              className="flex h-14 w-14 items-center justify-center rounded-panel bg-primary-tint text-primary"
            >
              <Icon name="upload" size={26} />
            </span>
            <h2 className="m-0 text-xl font-semibold">Drag recordings here</h2>
            <p className="m-0 text-muted">
              MP3, M4A, WAV, OGG, WEBM or MP4, up to {formatSize(512 * 1024 * 1024)} per file.
            </p>
            <Button disabled={running} onClick={() => input.current?.click()}>
              Choose files
            </Button>
            <input
              ref={input}
              type="file"
              multiple
              accept={ACCEPT_ATTRIBUTE}
              className="sr-only"
              tabIndex={-1}
              aria-label="Choose files"
              onChange={(e) => {
                add(e.target.files);
                e.target.value = "";
              }}
            />
            <p className="m-0 text-small text-muted-2">Each file becomes one {labels.recording.toLowerCase()}.</p>
          </div>

          {items.length > 0 && (
            <Panel
              flush
              title="Files"
              actions={<span className="text-sm text-muted">{summaryText(summary)}</span>}
              footer={
                allDone && (
                  <>
                    <span>
                      All uploaded. Each one appears in {labels.recording_plural.toLowerCase()} and updates on its own.
                    </span>
                    <Button onClick={() => navigate("/recordings")}>
                      Go to {labels.recording_plural.toLowerCase()}
                    </Button>
                  </>
                )
              }
            >
              <ul aria-label="Files" className="m-0 list-none p-0">
                {items.map((item) => (
                  <FileRow
                    key={item.key}
                    item={item}
                    onRemove={() => dispatch({ type: "remove", key: item.key })}
                    onRetry={() => dispatch({ type: "retry", key: item.key })}
                    onForce={() => void force(item)}
                    onSkip={() => dispatch({ type: "remove", key: item.key })}
                    onOpen={(id) => navigate(`/recordings/${id}`)}
                  />
                ))}
              </ul>
            </Panel>
          )}
        </div>

        <Panel as="aside" title="Settings" description="Applied to every file you upload now." className="gap-5">
          {me.tenant.enabled_types.length > 1 && (
            <ChoiceCards
              legend="Conversation type"
              value={type}
              onChange={setType}
              disabled={running}
              options={me.tenant.enabled_types.map((t) => ({ value: t, label: capitalise(t) }))}
            />
          )}
          {staffSelf && onlyPerson ? (
            <div className="flex flex-col gap-1">
              <span className="text-sm font-semibold text-ink">{capitalise(labels.person)}</span>
              <span className="text-muted">{onlyPerson.name} (you)</span>
            </div>
          ) : (
            <Select
              label={capitalise(labels.person)}
              value={chosenPerson}
              disabled={running || people.isPending}
              onChange={(e) => setPersonId(e.target.value)}
              error={
                people.isError ? `The list of ${labels.person_plural.toLowerCase()} could not be loaded.` : undefined
              }
            >
              <option value="">{people.isPending ? "Loading…" : `Choose a ${labels.person.toLowerCase()}`}</option>
              {people.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          )}

          <div className="flex flex-col gap-3 rounded-card border border-warning-border bg-warning-surface px-3.5 py-3">
            <label className="flex cursor-pointer items-start gap-2.5">
              <input
                type="checkbox"
                checked={consentOnFile}
                disabled={running}
                onChange={(e) => setConsentOnFile(e.target.checked)}
                className="m-0 mt-0.5 h-4.5 w-4.5 shrink-0 accent-primary"
              />
              <span className="flex flex-col gap-0.5">
                <span className="font-semibold">Consent is on file for these recordings</span>
                <span className="text-small text-muted">
                  Required before Sabha processes a recording. Without it, files are uploaded but wait.
                </span>
              </span>
            </label>
            {consentOnFile && (
              <Input
                label="Consent form or notice"
                placeholder="For example: Parent consent form 2026-27"
                value={consentRef}
                maxLength={200}
                disabled={running}
                onChange={(e) => setConsentRef(e.target.value)}
                error={consentMissing ? "Name the consent form or notice." : undefined}
              />
            )}
          </div>

          <div className="flex flex-col gap-2 border-t border-line-subtle pt-4">
            <Button fullWidth disabled={!canStart} onClick={() => void start()}>
              {running ? "Uploading…" : summary.ready > 0 ? `Upload ${summary.ready} ${things}` : "Upload"}
            </Button>
            <p className="m-0 text-center text-small text-muted">
              {summary.ready === 0 && !running
                ? "Add files to begin."
                : !chosenPerson
                  ? `Choose a ${labels.person.toLowerCase()} to continue.`
                  : !consentOnFile
                    ? "These will wait for consent before processing."
                    : "Sabha starts on each file as soon as it is uploaded."}
            </p>
          </div>
        </Panel>
      </div>
    </div>
  );
}
