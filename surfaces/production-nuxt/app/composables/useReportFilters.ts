import { computed, reactive, ref } from "vue";
import {
  reportDateError,
  type ReportFiltersQuery,
  type ReportKind,
} from "~/presentation/reports";

export function useReportFilters(initial: ReportFiltersQuery) {
  const draft = reactive({ ...initial });
  const applied = ref<ReportFiltersQuery>({ ...initial });
  const validationError = computed(() =>
    reportDateError(draft.date_from, draft.date_to),
  );
  const isDirty = computed(() =>
    Object.entries(draft).some(
      ([key, value]) =>
        key !== "cursor" &&
        value !== applied.value[key as keyof ReportFiltersQuery],
    ),
  );

  function normalizeDraft(): void {
    if (draft.report_kind !== "history" && draft.sort.startsWith("date_")) {
      draft.sort = "default";
    }
  }

  function selectKind(kind: ReportKind): void {
    draft.report_kind = kind;
    normalizeDraft();
  }

  function apply(): boolean {
    if (validationError.value) return false;
    normalizeDraft();
    draft.operator_ref = draft.operator_ref.trim();
    applied.value = {
      ...draft,
      cursor: "",
    };
    return true;
  }

  function openCursor(cursor: string): void {
    applied.value = { ...applied.value, cursor };
  }

  return {
    draft,
    applied,
    validationError,
    isDirty,
    selectKind,
    apply,
    openCursor,
  };
}
