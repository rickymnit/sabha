// Expected against actual cost of one recording (GET /v1/recordings/{id}/cost), in rupees. Expected is what the
// upload page showed, kept on the recording; actual is the speech-to-text audio sent at the published price and the
// LLM calls' recorded cost. Only Sabha's AI services are counted. A part without a price is shown as such.

import { useRecordingCost } from "../../api/hooks";
import { Panel, cx } from "../../design";
import { formatDifference, formatInr } from "./money";

const money = (value: number | null | undefined, missing = "—") => (value == null ? missing : formatInr(value));

export function CostCard({ recordingId }: { recordingId: string }) {
  const cost = useRecordingCost(recordingId);
  if (!cost.data) return null;
  const { estimate, actual, sources, duration_ms } = cost.data;
  const minutes = duration_ms ? duration_ms / 60_000 : null;
  const rows: [string, number | null | undefined, number | null | undefined][] = [
    ["Speech-to-text", estimate?.asr_inr, actual.asr_inr],
    ["AI scoring (LLM)", estimate?.llm_inr, actual.llm_inr],
    ["Total", estimate?.total_inr, actual.total_inr],
  ];
  const expectedPerMin =
    estimate?.total_inr != null && estimate.duration_ms ? estimate.total_inr / (estimate.duration_ms / 60_000) : null;
  return (
    <Panel
      title="Cost of this recording"
      description="Sabha's AI services only (speech-to-text and the LLM); our own servers are not included."
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] text-table">
          <thead>
            <tr className="text-left text-small text-muted">
              <th scope="col" className="py-1.5 font-medium" />
              <th scope="col" className="py-1.5 text-right font-medium">
                Expected at upload
              </th>
              <th scope="col" className="py-1.5 text-right font-medium">
                Actual{actual.final ? "" : " so far"}
              </th>
              <th scope="col" className="py-1.5 text-right font-medium">
                Difference
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([name, expected, real]) => (
              <tr key={name} className={cx("border-t border-line-subtle", name === "Total" && "font-semibold")}>
                <th scope="row" className="py-2 text-left font-[inherit] text-ink">
                  {name}
                </th>
                <td className="py-2 text-right tabular-nums">{money(expected)}</td>
                <td className="py-2 text-right tabular-nums">{money(real, actual.final ? "—" : "pending")}</td>
                <td className="py-2 text-right tabular-nums text-muted">
                  {expected != null && real != null ? formatDifference(real, expected) : "—"}
                </td>
              </tr>
            ))}
            <tr className="border-t border-line-subtle text-muted">
              <th scope="row" className="py-2 text-left font-normal">
                Per minute of recording
              </th>
              <td className="py-2 text-right tabular-nums">{money(expectedPerMin)}</td>
              <td className="py-2 text-right tabular-nums">{money(actual.inr_per_minute)}</td>
              <td className="py-2" />
            </tr>
          </tbody>
        </table>
      </div>
      <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-caption text-muted">
        {!estimate && (
          <li>No estimate was kept: this was uploaded before costs were shown, or its length could not be read.</li>
        )}
        {actual.final && actual.asr_audio_minutes == null && (
          <li>Speech-to-text cost was not recorded: this was transcribed before costs were tracked.</li>
        )}
        {estimate && (
          <li>
            Expected from a {Math.round((estimate.duration_ms / 60_000) * 10) / 10}-minute file,{" "}
            {Math.round(estimate.speech_share * 100)}% of it speech
            {estimate.history_n
              ? `, and the LLM cost of ${estimate.history_n} earlier recordings of this type.`
              : " (no earlier recordings of this type yet)."}
          </li>
        )}
        {actual.asr_audio_minutes != null && minutes != null && (
          <li>
            {actual.asr_audio_minutes} min of audio was sent to speech-to-text (speech only, of{" "}
            {Math.round(minutes * 10) / 10} min recorded).
          </li>
        )}
        {actual.llm_calls > 0 && (
          <li>
            {actual.llm_calls} LLM calls
            {actual.llm_usd != null ? `, $${actual.llm_usd.toFixed(4)}` : ""}
            {actual.llm_unpriced_calls ? `; ${actual.llm_unpriced_calls} without a published price` : ""}.
          </li>
        )}
        {sources.asr_inr_per_minute != null && (
          <li>
            Speech-to-text {formatInr(sources.asr_inr_per_minute)}/min ({sources.asr_model}): {sources.asr_price_source}
          </li>
        )}
        <li>
          {sources.usd_inr_rate != null
            ? `$1 = ${formatInr(sources.usd_inr_rate)}${sources.usd_inr_source ? ` (${sources.usd_inr_source})` : ""}`
            : "No dollar-to-rupee rate is set (USD_INR_RATE), so the LLM cost is not shown in rupees."}
        </li>
      </ul>
    </Panel>
  );
}
