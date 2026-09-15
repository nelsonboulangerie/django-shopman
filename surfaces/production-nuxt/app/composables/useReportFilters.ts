import { computed, reactive, ref } from "vue";
import type { ReportFiltersQuery } from "~/presentation/reports";
import { reportDateError } from "~/presentation/reports";

export function useReportFilters(initial: ReportFiltersQuery) {
  const draft = reactive({ ...initial });
  const applied = ref<ReportFiltersQuery>({ ...initial });
  const validationError = computed(() =>
    reportDateError(draft.date_from, draft.date_to),
  );

  function apply(): boolean {
    if (validationError.value) return false;
    const sort =
      draft.report_kind === "history" || !draft.sort.startsWith("date_")
        ? draft.sort
        : "default";
    applied.value = {
      ...draft,
      operator_ref: draft.operator_ref.trim(),
      sort,
      cursor: "",
    };
    return true;
  }

  function openCursor(cursor: string): void {
    applied.value = { ...applied.value, cursor };
  }

  return { draft, applied, validationError, apply, openCursor };
}
