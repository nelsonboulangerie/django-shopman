import { toast } from "vue-sonner";

import type { PosSettingsResponse } from "~/types/settings";

/**
 * PDV › Ajustes: a leitura das abas Impressoras, Maquininhas, Envio à cozinha e
 * Atalhos de venda (`GET /api/v1/backstage/pos/settings/`) e uma gravação por vez
 * (`POST`, `{section, ...}`), que devolve a leitura nova. Client-side: a permissão
 * é do operador identificado na estação.
 */
export function usePosSettings() {
  const apiPath = useApiPath();
  const action = usePosAction();
  const { data, pending, error, refresh } = useFetch<PosSettingsResponse>(
    () => apiPath("/api/v1/backstage/pos/settings/"),
    { key: "pos-settings", credentials: "include", server: false, lazy: true },
  );
  const saving = ref("");

  async function save(section: string, body: Record<string, unknown>, done: string): Promise<boolean> {
    saving.value = section;
    try {
      data.value = await action.call<PosSettingsResponse>("/api/v1/backstage/pos/settings/", {
        body: { section, ...body },
      });
      toast.success(done);
      return true;
    } catch (err) {
      toast.error(httpErrorMessage(err, "Não deu para gravar. Confira e tente de novo."));
      return false;
    } finally {
      saving.value = "";
    }
  }

  return { data, pending, error, refresh, saving, save };
}
