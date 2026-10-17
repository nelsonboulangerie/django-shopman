import { useOperatorResourceKey } from "./useOperatorResourceKey";
import type { OperationChecklistResponse } from "~/types/operationChecklists";

const BASE = "/api/v1/backstage/operation-checklists";

export interface TaskEvidenceInput extends Record<string, unknown> {
  evidence_text?: string;
  evidence_number?: string | null;
  evidence_data?: Record<string, unknown>;
  notes?: string;
}

export function useOperationChecklists() {
  const { data, pending, error, refresh } =
    useFetch<OperationChecklistResponse>(`${BASE}/`, {
      key: useOperatorResourceKey("operation-checklists"),
      dedupe: "defer",
      onResponseError: operatorSessionOnError,
    });
  const busy = ref("");
  const message = ref("");
  const board = computed(() => data.value?.checklists ?? null);

  async function mutate(
    key: string,
    url: string,
    body: Record<string, unknown> = {},
  ): Promise<boolean> {
    if (busy.value) return false;
    busy.value = key;
    message.value = "";
    try {
      data.value = await $fetch<OperationChecklistResponse>(url, {
        method: "POST",
        body,
      });
      return true;
    } catch (err) {
      message.value = httpErrorMessage(
        err,
        "Não foi possível atualizar o checklist.",
      );
      return false;
    } finally {
      busy.value = "";
    }
  }

  function start(templateRef: string, shiftRef = "") {
    return mutate("start", `${BASE}/start/`, {
      template_ref: templateRef,
      shift_ref: shiftRef.trim(),
      business_date: board.value?.business_date,
    });
  }

  function completeTask(
    runId: number,
    taskId: number,
    evidence: TaskEvidenceInput,
  ) {
    return mutate(
      `task:${taskId}`,
      `${BASE}/${runId}/tasks/${taskId}/complete/`,
      evidence,
    );
  }

  function superviseTask(runId: number, taskId: number) {
    return mutate(
      `supervise:${taskId}`,
      `${BASE}/${runId}/tasks/${taskId}/supervise/`,
    );
  }

  function completeRun(runId: number) {
    return mutate(`run:${runId}`, `${BASE}/${runId}/complete/`);
  }

  return {
    board,
    pending,
    error,
    refresh,
    busy,
    message,
    start,
    completeTask,
    superviseTask,
    completeRun,
  };
}
