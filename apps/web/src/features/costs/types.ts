// Expected and actual cost in rupees (sabha_api/services/costs.py). Only Sabha's AI services are priced
// (speech-to-text and the LLM); a part without a published price or history is null, never guessed.

export interface CostEstimate {
  duration_ms: number;
  asr_inr: number | null;
  llm_inr: number | null;
  /** null unless both parts are known. */
  total_inr: number | null;
  /** Share of the recording expected to be speech, sent to speech-to-text. */
  speech_share: number;
  /** Earlier recordings of this type the LLM part and speech share come from. */
  history_n: number;
  usd_inr_rate: number | null;
  made_at: string;
}

export interface CostSources {
  asr_model: string | null;
  asr_inr_per_minute: number | null;
  asr_price_source: string | null;
  usd_inr_rate: number | null;
  usd_inr_source: string | null;
}

export interface EstimateResponse {
  estimate: CostEstimate;
  inr_per_minute: number | null;
  sources: CostSources;
}

export interface ActualCost {
  asr_audio_minutes: number | null;
  asr_inr: number | null;
  llm_calls: number;
  llm_unpriced_calls: number;
  llm_usd: number | null;
  llm_inr: number | null;
  total_inr: number | null;
  inr_per_minute: number | null;
  /** The recording is finished; until then the actual cost may still grow. */
  final: boolean;
}

export interface CostResponse {
  recording_id: string;
  duration_ms: number | null;
  estimate: CostEstimate | null;
  actual: ActualCost;
  sources: CostSources;
}
