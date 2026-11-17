import { useOperatorResourceKey } from "./useOperatorResourceKey";
// A loja no iFood, ao vivo (módulo Merchant): cada seção é uma leitura própria e
// falha sozinha. Toda leitura PERGUNTA AO iFOOD — por isso não há poll automático:
// a tela relê ao abrir, no botão "Consultar o iFood" e logo depois de cada gesto
// (o toggle do canal grava pela fila, e o iFood aplica em alguns segundos).
import type {
  IFoodInterruptions,
  IFoodMerchantDetail,
  IFoodMerchants,
  IFoodOff,
  IFoodOpeningHours,
} from "~/types/ifoodMerchant";
import {
  httpError,
  httpErrorMessage,
} from "../../../operator-kit/app/utils/httpError";

const BASE = "/api/v1/backstage/ifood";
/** Depois de um gesto, relê as pausas nestes instantes (ms): a fila + o iFood levam segundos. */
export const AFTER_GESTURE_MS = [3_000, 8_000, 15_000];

export function useIFoodMerchant() {
  const read = <T>(path: string, name: string) =>
    useFetch<T | IFoodOff>(`${BASE}/${path}/`, {
      key: useOperatorResourceKey(`ifood-merchant-${name}`),
      server: false,
    });
  const merchants = read<IFoodMerchants>("merchants", "list");
  const merchant = read<IFoodMerchantDetail>("merchant", "detail");
  const interruptions = read<IFoodInterruptions>("interruptions", "pauses");
  const hours = read<IFoodOpeningHours>("opening-hours", "hours");

  const pending = computed(
    () =>
      merchants.pending.value ||
      merchant.pending.value ||
      interruptions.pending.value ||
      hours.pending.value,
  );
  const enabled = computed(() => {
    const value = merchants.data.value;
    return value ? value.enabled : null;
  });

  async function refreshAll() {
    await Promise.all([
      merchants.refresh(),
      merchant.refresh(),
      interruptions.refresh(),
      hours.refresh(),
    ]);
  }

  let timers: ReturnType<typeof setTimeout>[] = [];
  /** O toggle grava pela fila: relê pausas e status algumas vezes logo depois. */
  function followGesture() {
    timers.forEach(clearTimeout);
    timers = AFTER_GESTURE_MS.map((ms) =>
      setTimeout(() => {
        void interruptions.refresh();
        void merchant.refresh();
      }, ms),
    );
  }
  onBeforeUnmount(() => timers.forEach(clearTimeout));

  const removing = ref("");
  const removeError = ref("");
  async function removePause(id: string): Promise<boolean> {
    if (removing.value) return false;
    removing.value = id;
    removeError.value = "";
    try {
      const fresh = await $fetch<IFoodInterruptions>(
        `${BASE}/interruptions/${encodeURIComponent(id)}/`,
        { method: "DELETE" },
      );
      interruptions.data.value = fresh;
      void merchant.refresh();
      return true;
    } catch (failure) {
      removeError.value = httpErrorMessage(
        failure,
        "Não foi possível remover a pausa no iFood.",
      );
      if (httpError(failure).status === 409) void interruptions.refresh();
      return false;
    } finally {
      removing.value = "";
    }
  }

  const writing = ref(false);
  const writeError = ref("");
  /** Grava agora o horário da casa no iFood (só gerente) e mostra a releitura. */
  async function writeHours(): Promise<boolean> {
    if (writing.value) return false;
    writing.value = true;
    writeError.value = "";
    try {
      hours.data.value = await $fetch<IFoodOpeningHours>(
        `${BASE}/opening-hours/write/`,
        { method: "POST" },
      );
      return true;
    } catch (failure) {
      writeError.value = httpErrorMessage(
        failure,
        "Não foi possível gravar o horário no iFood.",
      );
      return false;
    } finally {
      writing.value = false;
    }
  }

  return {
    writeHours,
    writing,
    writeError,
    merchants: merchants.data,
    merchant: merchant.data,
    interruptions: interruptions.data,
    hours: hours.data,
    pending,
    enabled,
    refreshAll,
    followGesture,
    removePause,
    removing,
    removeError,
  };
}
