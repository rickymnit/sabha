import { useRubric, useRubrics } from "../../api/hooks";

/** The words the tenant's current sales rubric uses for interest levels (output_labels), if it has any. */
export function useInterestLabels(): Record<string, string> | undefined {
  const rubrics = useRubrics();
  const salesId = rubrics.data?.items.find((r) => r.type === "sales")?.current_id;
  return useRubric(salesId).data?.output_labels?.interest_level;
}
