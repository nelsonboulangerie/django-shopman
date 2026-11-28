import { httpError } from "../../../operator-kit/app/utils/httpError";
import type { OperationChecklistResponse } from "~/types/operationChecklists";

const BASE = "/api/v1/backstage/operation-checklists";

/** A leitura é de quem está operando: o cache nunca serve a rotina de outra pessoa. */
function operatorKey(resource: string): string {
  const { data } = useNuxtData<{ operator?: { id: number } }>("operator-session");
  return `pos:${data.value?.operator?.id ?? "unidentified"}:${resource}`;
}

export interface TaskEvidenceInput extends Record<string, unknown> {
  evidence_text?: string;
  evidence_number?: string | null;
  evidence_data?: Record<string, unknown>;
  notes?: string;
}

export function useOperationChecklists() {
  const { data, pending, error, refresh } =
    useFetch<OperationChecklistResponse>(`${BASE}/`, {
      key: operatorKey("operation-checklists"),
      dedupe: "defer",
      onResponseError: operatorSessionOnError,
    });
  const busy = ref("");
  const message = ref("");
  // A recusa que tem campo (a evidência que faltou) fica com a TAREFA, embaixo do
  // campo, e não no topo da página, fora da vista (GES-23).
  const taskErrors = ref<Record<number, { field: string; message: string }>>({});
  const board = computed(() => data.value?.checklists ?? null);

  async function mutate(
    key: string,
    url: string,
    body: Record<string, unknown> = {},
    taskId?: number,
  ): Promise<boolean> {
    if (busy.value) return false;
    busy.value = key;
    message.value = "";
    if (taskId !== undefined) {
      taskErrors.value = Object.fromEntries(
        Object.entries(taskErrors.value).filter(([id]) => Number(id) !== taskId),
      );
    }
    try {
      data.value = await $fetch<OperationChecklistResponse>(url, {
        method: "POST",
        body,
      });
      return true;
    } catch (err) {
      const text = httpErrorMessage(
        err,
        "A rotina não foi atualizada. Tente de novo.",
      );
      const field = (httpError(err).data as { field?: unknown } | null)?.field;
      if (taskId !== undefined && typeof field === "string" && field) {
        taskErrors.value = {
          ...taskErrors.value,
          [taskId]: { field, message: text },
        };
      } else {
        message.value = text;
      }
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
      taskId,
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
    taskErrors,
    start,
    completeTask,
    superviseTask,
    completeRun,
  };
}
