// Vincular ESTE dispositivo a um posto de trabalho: o ato de montagem, uma vez por máquina.
//
// Sem ele, nada do resto acontece: um dispositivo que não é posto não tem antessala,
// e a única entrada é senha de gestor todo dia. Acontece uma vez por dispositivo, com
// o gestor logado ali, e o cookie responde por ele daí em diante, em TODOS os apps
// (o cookie vale no domínio inteiro: o posto é um só).
//
// `surface` é o id do app (`surfaces/registry.json`) e só escolhe quais postos este
// app oferece; omitido, vem da identidade do app (`operatorPwa.app`).
//
// `allowed` é falso quando o servidor recusa a leitura (403): quem não gere
// operadores não vê a oferta. É de propósito que a tela dependa da resposta do
// servidor em vez de adivinhar pela permissão: a permissão mora lá.
import type { StationProvisionState, WorkstationCard, WorkstationOption } from "../types/operator";
import type { WorkstationCopy } from "../presentation/workstation";
import { httpErrorCode, httpErrorMessage } from "../utils/httpError";

const ROTA = "/api/v1/backstage/operator/station/";

function currentSurface(): string {
  const pwa = useRuntimeConfig().public?.operatorPwa as { app?: string } | undefined;
  return pwa?.app ?? "";
}

export function useStationProvision(surface?: string) {
  const app = surface ?? currentSurface();
  const workstations = ref<WorkstationOption[]>([]);
  const station = ref("");
  const workstation = ref<WorkstationCard | null>(null);
  const copy = ref<Partial<WorkstationCopy>>({});
  const allowed = ref(false);
  const loaded = ref(false);
  const busy = ref(false);
  const error = ref("");
  // O caixa escolhido já tem outro dispositivo: o servidor pede a segunda palavra
  // (D-007: vários no mesmo caixa dividem gaveta e turno, com visibilidade, nunca
  // recusa). Guarda o ref para a confirmação não depender de a escolha continuar igual.
  const confirmFor = ref("");

  async function load(): Promise<void> {
    try {
      const res = await $fetch<StationProvisionState>(ROTA, app ? { query: { surface: app } } : {});
      station.value = res.station ?? "";
      workstation.value = res.workstation ?? null;
      workstations.value = res.workstations ?? [];
      copy.value = res.copy ?? {};
      allowed.value = true;
    } catch {
      allowed.value = false;
      workstations.value = [];
    } finally {
      loaded.value = true;
    }
  }

  /** Vincula e devolve `true` no sucesso. Quem chama decide o que fazer com a tela;
   *  recarregar é o normal, porque toda leitura muda de mundo. */
  async function provision(workstationRef: string, options: { confirm?: boolean } = {}): Promise<boolean> {
    if (busy.value || !workstationRef) return false;
    busy.value = true;
    error.value = "";
    confirmFor.value = "";
    try {
      const body: Record<string, unknown> = { workstation_ref: workstationRef };
      if (options.confirm) body.confirm = true;
      await $fetch(ROTA, { method: "POST", body });
      station.value = workstationRef;
      return true;
    } catch (err) {
      if (httpErrorCode(err) === "station_cash_desk_shared") confirmFor.value = workstationRef;
      error.value = httpErrorMessage(err, copy.value.setup_error ?? "");
      return false;
    } finally {
      busy.value = false;
    }
  }

  return { workstations, station, workstation, copy, allowed, loaded, busy, error, confirmFor, load, provision };
}
