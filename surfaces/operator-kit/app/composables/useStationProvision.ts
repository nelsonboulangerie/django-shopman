// Transformar ESTE dispositivo numa estação da loja — o ato de montagem do balcão.
//
// Sem ele, nada do resto acontece: um dispositivo não provisionado não tem
// antessala, e a única entrada é senha de gestor todo dia. Acontece uma vez por
// dispositivo, com o gestor logado ali, e o cookie responde por ele daí em diante.
//
// `allowed` é falso quando o servidor recusa a leitura (403): quem não gere
// operadores não vê a oferta. É de propósito que a tela dependa da resposta do
// servidor em vez de adivinhar pela permissão — a permissão mora lá.
import type { StationProvisionState, StationTerminal } from "../types/operator";
import { httpErrorMessage } from "../utils/httpError";

const ROTA = "/api/v1/backstage/operator/station/";

export function useStationProvision() {
  const terminals = ref<StationTerminal[]>([]);
  const station = ref("");
  const allowed = ref(false);
  const loaded = ref(false);
  const busy = ref(false);
  const error = ref("");

  async function load(): Promise<void> {
    try {
      const res = await $fetch<StationProvisionState>(ROTA);
      station.value = res.station ?? "";
      terminals.value = res.terminals ?? [];
      allowed.value = true;
    } catch {
      allowed.value = false;
      terminals.value = [];
    } finally {
      loaded.value = true;
    }
  }

  /** Provisiona e devolve `true` no sucesso. Quem chama decide o que fazer com a
   *  tela; recarregar é o normal, porque toda leitura muda de mundo. */
  async function provision(terminalRef: string): Promise<boolean> {
    if (busy.value || !terminalRef) return false;
    busy.value = true;
    error.value = "";
    try {
      await $fetch(ROTA, { method: "POST", body: { terminal_ref: terminalRef } });
      station.value = terminalRef;
      return true;
    } catch (err) {
      error.value = httpErrorMessage(err, "Não foi possível preparar este dispositivo.");
      return false;
    } finally {
      busy.value = false;
    }
  }

  return { terminals, station, allowed, loaded, busy, error, load, provision };
}
