import type { ComputedRef } from "vue";

import type { StationDeviceAgent, TwoZoneQueueProjection } from "~/types/orders";
import { danfeAutoPrintRefs } from "~/presentation/danfe";
import {
  localDeviceAgentErrorMessage,
  printWithLocalDeviceAgent,
} from "../../../operator-kit/app/utils/localDeviceAgent";

interface DanfePrintResponse {
  payload_b64: string;
  title: string;
  reprint: boolean;
}

/**
 * A DANFE da sacola: o servidor compõe, esta estação relaia ao agente dela.
 *
 * O mesmo desenho da DANFE do PDV (`POSDanfeEscposView` → agente do balcão),
 * com a impressora da ESTAÇÃO onde o Gestor está aberto (`device_agent` da
 * leitura do quadro). Duas formas de sair:
 *
 * - **sozinha** — o quadro releu (despacho, ou SSE da nota autorizada) e o
 *   servidor marcou `danfe_auto_print`. Só estação com impressora tenta, e o
 *   servidor garante que sai uma vez só mesmo com duas estações abertas;
 * - **a mão** — o botão do card, que sai REIMPRESSÃO a partir da segunda.
 *
 * O despacho nunca espera por isto (expedição sem NFC-e só avisa): a DANFE
 * é consequência da leitura do quadro, não etapa do gesto de despachar.
 */
export function useDanfePrint(
  queue: ComputedRef<TwoZoneQueueProjection | null>,
  deviceAgent: ComputedRef<StationDeviceAgent | null>,
  refresh: () => unknown,
) {
  // Por pedido, não global: a automática de um pedido não pode engolir o
  // botão que o operador acabou de tocar em outro.
  const printing = ref<Set<string>>(new Set());
  const isPrinting = (ref_: string) => printing.value.has(ref_);
  const attempted = new Set<string>();

  const canPrint = computed(() => Boolean(deviceAgent.value?.can_print && deviceAgent.value.agent_url));
  const unavailableReason = computed(
    () => deviceAgent.value?.reason || "Esta estação não tem impressora configurada. Configure em Terminais do PDV, no gestor.",
  );

  async function printDanfe(ref_: string, options: { auto?: boolean } = {}): Promise<boolean> {
    const auto = options.auto === true;
    const agent = deviceAgent.value;
    if (!canPrint.value || !agent) {
      if (!auto) useSonner.error(`A DANFE não sai nesta estação: ${unavailableReason.value}`);
      return false;
    }
    if (printing.value.has(ref_)) return false;
    printing.value = new Set(printing.value).add(ref_);
    try {
      let job: DanfePrintResponse;
      try {
        job = await $fetch<DanfePrintResponse>(
          `/api/v1/backstage/orders/${encodeURIComponent(ref_)}/danfe-escpos/`,
          { method: "POST", body: { auto } },
        );
      } catch (error) {
        // A automática recusada (409) é a outra estação que já imprimiu, ou a
        // janela que fechou: nada a dizer. A manual recusada tem frase do servidor.
        if (auto && httpError(error).status === 409) return false;
        useSonner.error(httpErrorMessage(error, `O servidor não montou a DANFE do pedido ${ref_}.`));
        return false;
      }
      try {
        await printWithLocalDeviceAgent(agent, job.payload_b64, job.title);
      } catch (error) {
        useSonner.error(
          `A DANFE do pedido ${ref_} não saiu: ${localDeviceAgentErrorMessage(error)} Reimprima pelo card.`,
        );
        return false;
      }
      useSonner.success(
        job.reprint ? `DANFE do pedido ${ref_} reimpressa.` : `DANFE do pedido ${ref_} impressa — vai na sacola.`,
      );
      return true;
    } finally {
      const next = new Set(printing.value);
      next.delete(ref_);
      printing.value = next;
      void refresh();
    }
  }

  async function printDue() {
    if (!canPrint.value) return;
    for (const ref_ of danfeAutoPrintRefs(queue.value, attempted)) {
      // Duas leituras seguidas podem listar o mesmo pedido: confere de novo.
      if (attempted.has(ref_)) continue;
      attempted.add(ref_);
      await printDanfe(ref_, { auto: true });
    }
  }

  // Sem guarda de `import.meta.client`: no SSR a leitura do quadro não existe
  // (`server: false`), então não há impressora e `printDue` não faz nada.
  watch([queue, canPrint], () => { void printDue(); }, { immediate: true });

  return { isPrinting, canPrint, unavailableReason, printDanfe };
}
