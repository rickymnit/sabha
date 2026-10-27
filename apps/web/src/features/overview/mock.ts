// Mock overview numbers for the /dev/overview demo and tests (P6.4b). Illustrative values only, not measurements.

import type { Labels } from "../report/types";
import type { TypeNames } from "./metrics";
import type { OverviewStats } from "./types";

export const mockTypeNames: TypeNames = {
  teaching: "Teaching",
  reception: "Reception",
  counselling: "Counselling",
  meeting: "Meetings",
  sales: "Sales",
};

export const mockLabels: Labels = {
  person: "teacher",
  person_plural: "teachers",
  recording: "lesson",
  recording_plural: "lessons",
  unit: "campus",
  manager: "head of department",
};

export function mockOverview(): OverviewStats {
  return {
    from: "2026-10-05T18:30:00.000Z",
    to: "2026-10-12T18:30:00.000Z",
    recordings_analysed: 214,
    audio_hours: 162.4,
    silence_hours: 41.2,
    silence_n: 1,
    median_overall_by_type: [
      { type: "teaching", median: 3.5, n: 128 },
      { type: "reception", median: 3.9, n: 46 },
      { type: "sales", median: 3.1, n: 0 },
    ],
    coaching: [
      {
        rubric_id: "teaching.school.v1.0",
        dimension_key: "recap",
        dimension_name: "Recap and closure",
        type: "teaching",
        median: 2.9,
        n: 128,
      },
      {
        rubric_id: "teaching.school.v1.0",
        dimension_key: "cfu",
        dimension_name: "Checks for understanding",
        type: "teaching",
        median: 2.6,
        n: 128,
      },
      {
        rubric_id: "reception.school.v1.0",
        dimension_key: "resolution",
        dimension_name: "Resolution confirmed",
        type: "reception",
        median: 3.2,
        n: 46,
      },
      {
        rubric_id: "sales.company.v1.0",
        dimension_key: "objections",
        dimension_name: "Objection handling",
        type: "sales",
        median: 1.5,
        n: 0,
      },
    ],
  };
}

export function emptyOverview(): OverviewStats {
  return {
    ...mockOverview(),
    recordings_analysed: 0,
    audio_hours: 0,
    silence_hours: 0,
    silence_n: 1,
    median_overall_by_type: [],
    coaching: [],
  };
}
