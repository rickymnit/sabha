// The pipeline stages in plain words (sabha_workers.tasks STAGES), for the processing details and the retry bar.

export const STAGE_NAMES: Record<string, string> = {
  preprocess: "Preparing the audio",
  diarize: "Telling the speakers apart",
  transcribe: "Writing the transcript",
  analyze: "Scoring",
};
