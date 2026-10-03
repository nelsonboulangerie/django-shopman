// Postos do Gestor: o cadastro de postos de trabalho (/api/v1/backstage/workstations/).
// Permissão: `cashman.manage_operators`, a mesma de vincular um dispositivo a um posto.
// Toda escrita devolve o cadastro inteiro de volta, e a tela troca o que mostra por
// ele: não há reconciliação peça por peça.
import type { WorkstationManageState } from "../../../operator-kit/app/types/operator";
import { useOperatorResourceKey } from "./useOperatorResourceKey";

const BASE = "/api/v1/backstage/workstations";

export function useWorkstations() {
  const { data, pending, error, refresh } = useFetch<WorkstationManageState>(`${BASE}/`, {
    key: useOperatorResourceKey("workstations"),
    dedupe: "defer",
    onResponseError: operatorSessionOnError,
  });

  const busy = ref("");
  const message = ref("");
  const copy = computed(() => data.value?.copy);

  async function run(key: string, call: () => Promise<WorkstationManageState>): Promise<boolean> {
    if (busy.value) return false;
    busy.value = key;
    message.value = "";
    try {
      data.value = { ...(data.value ?? {}), ...(await call()) } as WorkstationManageState;
      return true;
    } catch (err) {
      message.value = httpErrorMessage(err, copy.value?.manage_error ?? "");
      return false;
    } finally {
      busy.value = "";
    }
  }

  function create(label: string, kind: string) {
    return run("create", () => $fetch<WorkstationManageState>(`${BASE}/`, { method: "POST", body: { label, kind } }));
  }

  function update(ref_: string, body: { label?: string; kind?: string; is_active?: boolean }) {
    return run(`update:${ref_}`, () =>
      $fetch<WorkstationManageState>(`${BASE}/${encodeURIComponent(ref_)}/`, { method: "PATCH", body }),
    );
  }

  function releaseDevice(ref_: string, deviceId: string) {
    return run(`device:${deviceId}`, () =>
      $fetch<WorkstationManageState>(
        `${BASE}/${encodeURIComponent(ref_)}/devices/${encodeURIComponent(deviceId)}/`,
        { method: "DELETE" },
      ),
    );
  }

  return { state: data, copy, pending, error, refresh, busy, message, create, update, releaseDevice };
}
