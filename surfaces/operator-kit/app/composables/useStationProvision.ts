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
import { httpErrorCode, httpErrorMessage } from "../utils/httpError";

const ROTA = "/api/v1/backstage/operator/station/";

export function useStationProvision() {
  const terminals = ref<StationTerminal[]>([]);
  const station = ref("");
  const allowed = ref(false);
  const loaded = ref(false);
  const busy = ref(false);
  const error = ref("");
  // O balcão escolhido já tem outro dispositivo: o servidor pede a segunda
  // palavra (D-007: vários no mesmo terminal, com visibilidade, nunca recusa).
  // Guarda o ref para a confirmação não depender de a escolha continuar igual.
  const confirmFor = ref("");

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
  async function provision(terminalRef: string, options: { confirm?: boolean } = {}): Promise<boolean> {
    if (busy.value || !terminalRef) return false;
    busy.value = true;
    error.value = "";
    confirmFor.value = "";
    try {
      const body: Record<string, unknown> = { terminal_ref: terminalRef };
      if (options.confirm) body.confirm = true;
      await $fetch(ROTA, { method: "POST", body });
      station.value = terminalRef;
      return true;
    } catch (err) {
      if (httpErrorCode(err) === "station_terminal_shared") confirmFor.value = terminalRef;
      error.value = httpErrorMessage(err, "Não foi possível iniciar este dispositivo.");
      return false;
    } finally {
      busy.value = false;
    }
  }

  return { terminals, station, allowed, loaded, busy, error, confirmFor, load, provision };
}
