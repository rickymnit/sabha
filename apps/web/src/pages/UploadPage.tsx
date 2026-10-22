// /upload (P6.3, first version): one file at a time. Type and person come from the tenant (enabled types, the
// people the signed-in person may upload for); the consent reference is recorded with it (golden rule 9: without
// one the recording waits at UPLOADED). The flow itself is pages/upload/upload.ts.

import { useState, type FormEvent } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../api/client";
import { usePeople } from "../api/hooks";
import type { Me } from "../api/types";
import { Button, Card, Input, PageHeader, ProgressBar, Select } from "../design";
import { useSession } from "../session/session";
import { capitalise } from "../app/format";
import { uploadRecording, type UploadOutcome } from "./upload/upload";

type Stage =
  | { kind: "idle" }
  | { kind: "uploading"; sent: number; total: number }
  | { kind: "duplicate"; outcome: Extract<UploadOutcome, { kind: "duplicate" }> }
  | { kind: "error"; message: string; requestId?: string };

export function UploadPage() {
  const me = useOutletContext<Me>();
  const labels = me.tenant.labels;
  const { token } = useSession();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const people = usePeople();
  const [file, setFile] = useState<File | null>(null);
  const [type, setType] = useState<string>(me.tenant.enabled_types[0] ?? "teaching");
  const [personId, setPersonId] = useState<string>("");
  const [consentRef, setConsentRef] = useState("");
  const [stage, setStage] = useState<Stage>({ kind: "idle" });
  const onlyPerson = people.data?.length === 1 ? people.data[0] : undefined;
  const chosenPerson = personId || onlyPerson?.id || "";

  const finish = async (recordingId: string) => {
    await queryClient.invalidateQueries({ queryKey: ["recordings"] });
    navigate(`/recordings/${recordingId}`);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) return;
    setStage({ kind: "uploading", sent: 0, total: file.size });
    try {
      const outcome = await uploadRecording({
        file,
        type,
        personId: chosenPerson || null,
        consentRef: consentRef.trim() || null,
        token,
        onProgress: (sent, total) => setStage({ kind: "uploading", sent, total }),
      });
      if (outcome.kind === "duplicate") setStage({ kind: "duplicate", outcome });
      else await finish(outcome.result.recording_id);
    } catch (error) {
      setStage({
        kind: "error",
        message: error instanceof Error ? error.message : "The upload failed.",
        requestId: error instanceof ApiError ? error.requestId : undefined,
      });
    }
  };

  const confirmDuplicate = async () => {
    if (stage.kind !== "duplicate") return;
    try {
      const result = await stage.outcome.confirm();
      await finish(result.recording_id);
    } catch (error) {
      setStage({ kind: "error", message: error instanceof Error ? error.message : "The upload failed." });
    }
  };

  const busy = stage.kind === "uploading";
  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <PageHeader
        title={`Upload a ${labels.recording.toLowerCase()}`}
        description="MP3, M4A, WAV, WebM, OGG or MP4, up to 512 MB in this version."
      />
      <Card as="section" className="gap-4 p-5">
        <form className="flex flex-col gap-4" onSubmit={(e) => void submit(e)}>
          <Input
            label="Audio or video file"
            type="file"
            accept=".mp3,.m4a,.wav,.webm,.ogg,.mp4,audio/*,video/mp4"
            required
            disabled={busy}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <Select label="Type" value={type} disabled={busy} onChange={(e) => setType(e.target.value)}>
            {me.tenant.enabled_types.map((t) => (
              <option key={t} value={t}>
                {capitalise(t)}
              </option>
            ))}
          </Select>
          <Select
            label={capitalise(labels.person)}
            value={chosenPerson}
            disabled={busy || people.isPending}
            onChange={(e) => setPersonId(e.target.value)}
            hint={people.isError ? people.error.message : undefined}
          >
            <option value="">{people.isPending ? "Loading…" : `Choose a ${labels.person.toLowerCase()}`}</option>
            {people.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
          <Input
            label="Consent reference"
            hint="The consent form or notice this recording was made under. Without it the recording waits until consent is recorded."
            value={consentRef}
            maxLength={200}
            disabled={busy}
            onChange={(e) => setConsentRef(e.target.value)}
          />
          {stage.kind === "uploading" && (
            <ProgressBar value={stage.sent} max={stage.total} label={`Uploading ${file?.name ?? ""}`} showLabel />
          )}
          <div aria-live="polite">
            {stage.kind === "error" && (
              <p role="alert" className="text-sm text-danger">
                {stage.message}
                {stage.requestId ? ` (request ${stage.requestId})` : ""}
              </p>
            )}
            {stage.kind === "duplicate" && (
              <div className="flex flex-col gap-2">
                <p className="text-sm text-ink">This file is already uploaded in your organisation.</p>
                <Button variant="secondary" onClick={() => void confirmDuplicate()}>
                  Upload it anyway
                </Button>
              </div>
            )}
          </div>
          <Button type="submit" disabled={!file || busy || !chosenPerson}>
            {busy ? "Uploading…" : "Upload"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
