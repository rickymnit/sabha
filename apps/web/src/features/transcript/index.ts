// Transcript view for /recordings/:id (P6.5): synced audio player and virtualised transcript.
// Demo with mock data: /dev/transcript in development.

export { AudioPlayer, type AudioPlayerHandle, type AudioPlayerProps } from "./AudioPlayer";
export { TranscriptList, type TranscriptListProps } from "./TranscriptList";
export { findMatches, formatClock, formatSpoken, lineAt, segmentText, toUtf16Range, type Match } from "./text";
export type { LowConfidenceSpan, PlaybackUrl, RoleLabels, Transcript, Utterance } from "./types";
