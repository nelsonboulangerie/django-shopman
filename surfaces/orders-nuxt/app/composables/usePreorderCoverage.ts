import type {
  PreorderCoverageProjection,
  PreorderCoverageResponse,
} from "~/types/orders";
import { coalesceRefresh } from "../utils/coalesceRefresh";

/**
 * A leitura da agenda com cobertura da lista de Encomendas (WP-G10).
 *
 * Rota própria (`GET orders/preorder-coverage/`), fora do quadro: a cobertura só muda
 * quando uma encomenda é aceita, remarcada ou sai, ou quando a Produção planeja,
 * altera ou cancela um lote. Daí os dois gatilhos:
 *
 *   - `signature` (as encomendas da lista, refs e datas) mudou: relê na hora. Quem
 *     avisa é a própria fila, que já chega por SSE;
 *   - poll calmo: nenhum evento de produção chega ao Gestor, então o lote novo só
 *     aparece na próxima volta do relógio (ADR-016: o poll é o fallback, e aqui é o
 *     único caminho). A aba que volta a ficar visível relê na hora.
 *
 * Sem encomenda na lista (`signature` vazio) nada é lido: não há cabeçalho de dia para
 * dizer a cobertura.
 *
 * A falha não derruba a lista: a cobertura some (melhor calar do que dizer "a produção
 * cobre" com dado velho) e `failed` oferece o "Tentar de novo". Enquanto falha, o poll
 * continua tentando sozinho. Só lê: nenhuma gravação sai daqui.
 */
export const PREORDER_COVERAGE_PATH =
  "/api/v1/backstage/orders/preorder-coverage/";
export const PREORDER_COVERAGE_POLL_MS = 60_000;
const READ_TIMEOUT_MS = 8000;

export function usePreorderCoverage(signature: Ref<string>) {
  const coverage = shallowRef<PreorderCoverageProjection | null>(null);
  const failed = ref(false);
  const reading = ref(false);
  // A resposta que chega depois de a lista esvaziar é descartada.
  let generation = 0;

  async function read(): Promise<void> {
    if (!signature.value) return;
    const mine = generation;
    reading.value = true;
    try {
      const response = await $fetch<PreorderCoverageResponse>(
        PREORDER_COVERAGE_PATH,
        { timeout: READ_TIMEOUT_MS },
      );
      if (mine !== generation) return;
      // Resposta sem a agenda não é "nenhum dia": é leitura que não veio.
      if (!Array.isArray(response?.coverage?.days))
        throw new Error("preorder coverage: resposta sem a agenda");
      coverage.value = response.coverage;
      failed.value = false;
    } catch {
      if (mine !== generation) return;
      coverage.value = null;
      failed.value = true;
    } finally {
      if (mine === generation) reading.value = false;
    }
  }
  // Uma leitura por vez; a rajada de eventos da fila vira uma releitura só.
  const refresh = coalesceRefresh(read);

  function clear() {
    generation += 1;
    coverage.value = null;
    failed.value = false;
    reading.value = false;
  }

  watch(
    signature,
    (now) => {
      if (now) void refresh();
      else clear();
    },
    { immediate: true },
  );

  let timer: ReturnType<typeof setInterval> | null = null;
  const visible = () => document.visibilityState === "visible";
  const onVisible = () => {
    if (visible()) void refresh();
  };
  onMounted(() => {
    timer = setInterval(() => {
      if (visible()) void refresh();
    }, PREORDER_COVERAGE_POLL_MS);
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
  });
  onBeforeUnmount(() => {
    if (timer) clearInterval(timer);
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onVisible);
  });

  return {
    /** A agenda lida; `null` antes da primeira leitura, sem encomenda ou na falha. */
    coverage,
    /** A última leitura falhou: a lista segue sem a cobertura e oferece tentar de novo. */
    failed,
    /** Uma leitura está em curso (o "Tentar de novo" gira). */
    reading,
    /** Relê agora: o "Tentar de novo" da lista. */
    retry: refresh,
  };
}
