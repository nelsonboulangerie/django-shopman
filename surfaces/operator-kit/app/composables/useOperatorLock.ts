// A trava do operador, leitura e escrita. Lê o estado da antessala, lista quem
// pode destravar ESTA superfície, destrava por PIN ou crachá, e trava. Todo I/O
// passa pelo proxy do Django (CSRF resolvido lá). A permissão da superfície vai
// junto para o seletor e o destrave ficarem restritos a quem pode usar este app.
//
// Destravar é `login()` de verdade no servidor, e travar é `logout()`: a pessoa
// identificada VIRA a sessão. A estação sobrevive aos dois porque não mora na
// sessão — mora no cookie de confiança de dispositivo.
import type {
  OperatorCard,
  OperatorEligibleResponse,
  OperatorSession,
} from "../types/operator";
import {
  buildUnlockPayload,
  isLocked,
  type UnlockInput,
} from "../presentation/operatorLock";
import { httpErrorMessage } from "../utils/httpError";
import { useStationLock } from "./useStationLock";

export function useOperatorLock(perm: string) {
  const { data, refresh } = useFetch<OperatorSession>(
    "/api/v1/backstage/operator/session/",
    {
      key: "operator-session",
      server: true,
    },
  );

  // O cadeado visto pelo servidor (403 `station_locked`) entra no `locked` junto
  // com a sessão: a sessão pode estar velha, e enquanto ela mente a tela segue
  // montada com toda leitura negada. Estado puro no kit; aqui ele é composto.
  const station = useStationLock();

  const session = computed<OperatorSession | null>(() => data.value ?? null);
  // Este dispositivo pode PEDIR identificação? Sim quando a antessala respondeu — ou
  // seja, quando ele é uma estação reconhecida, ou já tem alguém logado. Quando
  // não é nenhum dos dois o endpoint responde 403 (`data` nulo) e a única saída
  // é a tela de senha.
  //
  // Era `authenticated`, e media outra coisa: se existia sessão de DISPOSITIVO
  // (`device_user`). Como não há mais conta de máquina, a pergunta que a tela
  // realmente faz é esta — e o nome antigo mandaria pedir senha num balcão que
  // só precisa de PIN.
  const canIdentify = computed(() => session.value !== null);
  const stationRef = computed(() => session.value?.station ?? "");
  const locked = computed(() => isLocked(session.value) || station.denied.value);

  /** Ergue a bandeira do servidor e relê a sessão para reconciliar. */
  function flagIfStationLocked(error: unknown): boolean {
    if (!station.flagIfStationLocked(error)) return false;
    refresh();
    return true;
  }
  const operator = computed<OperatorCard | null>(
    () => session.value?.operator ?? null,
  );
  // O operador foi resetado pelo gerente (PIN temporário) → força a troca.
  const mustChange = computed(() => Boolean(session.value?.pin_must_change));

  const eligible = ref<OperatorCard[]>([]);
  async function loadEligible(): Promise<void> {
    try {
      const res = await $fetch<OperatorEligibleResponse>(
        "/api/v1/backstage/operator/eligible/",
        {
          query: { perm },
        },
      );
      eligible.value = res.operators ?? [];
    } catch {
      eligible.value = [];
    }
  }

  const busy = ref(false);

  async function unlock(input: Omit<UnlockInput, "perm">): Promise<boolean> {
    if (busy.value) return false;
    busy.value = true;
    try {
      await $fetch("/api/v1/backstage/operator/unlock/", {
        method: "POST",
        body: buildUnlockPayload({ ...input, perm }),
      });
      station.clear();
      await refresh();
      // Os fetches que rodaram TRANCADOS falharam (403) e ficariam com o erro grudado na
      // tela até o próximo poll (≤15s) — destravou, recarrega tudo já (paridade POS/Produção).
      await refreshNuxtData();
      return true;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Identificação inválida. Tente de novo."));
      return false;
    } finally {
      busy.value = false;
    }
  }

  async function lock(): Promise<void> {
    try {
      await $fetch("/api/v1/backstage/operator/lock/", {
        method: "POST",
        body: {},
      });
      await refresh();
    } catch {
      // best-effort: a failed lock leaves the operator active; surfaced on next action.
    }
  }

  const changeError = ref("");
  // Trocar o próprio PIN provando o atual. `operatorId` identifica o alvo na lock
  // screen (fluxo forçado, onde o "atual" é o PIN temporário); ausente = operador ativo.
  async function changePin(input: {
    operatorId?: number;
    currentPin: string;
    newPin: string;
  }): Promise<boolean> {
    if (busy.value) return false;
    busy.value = true;
    changeError.value = "";
    try {
      await $fetch("/api/v1/backstage/operator/pin/change/", {
        method: "POST",
        body: {
          operator_id: input.operatorId,
          current_pin: input.currentPin,
          new_pin: input.newPin,
        },
      });
      await refresh();
      return true;
    } catch (err) {
      changeError.value = httpErrorMessage(err, "Não foi possível trocar o PIN.");
      return false;
    } finally {
      busy.value = false;
    }
  }

  return {
    session,
    canIdentify,
    stationRef,
    locked,
    flagIfStationLocked,
    operator,
    mustChange,
    eligible,
    loadEligible,
    unlock,
    lock,
    changePin,
    changeError,
    refresh,
    busy,
  };
}
