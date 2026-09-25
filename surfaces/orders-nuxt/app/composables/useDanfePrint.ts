import type { ComputedRef } from "vue";

import type { StationDeviceAgent } from "~/types/orders";
import {
  localDeviceAgentErrorMessage,
  printWithLocalDeviceAgent,
} from "../../../operator-kit/app/utils/localDeviceAgent";

type DanfePrintResponse =
  | { via: "relay"; reprint: boolean; target_label: string }
  | { via: "local"; reprint: boolean; payload_b64: string; title: string };

/**
 * O botão "Imprimir DANFE" do card.
 *
 * A DANFE da entrega sai SOZINHA pelo servidor (relay para a impressora do
 * despacho, `services/order_danfe.py`), e esta tela não participa disso: um
 * Gestor aberto num tablet sem impressora não segura papel nenhum. O botão
 * pede ao servidor a mesma coisa, à mão, para imprimir ou reimprimir.
 *
 * Só quando a loja não tem impressora de despacho o servidor devolve os bytes,
 * e esta estação relaia ao agente local dela (`device_agent`, o mesmo do PDV).
 */
export function useDanfePrint(
  deviceAgent: ComputedRef<StationDeviceAgent | null>,
  refresh: () => unknown,
) {
  // Por pedido, não global: um toque em um card não trava o botão de outro.
  const printing = ref<Set<string>>(new Set());
  const isPrinting = (ref_: string) => printing.value.has(ref_);

  const hasLocalAgent = computed(() => Boolean(deviceAgent.value?.can_print && deviceAgent.value.agent_url));

  async function printDanfe(ref_: string): Promise<boolean> {
    if (printing.value.has(ref_)) return false;
    printing.value = new Set(printing.value).add(ref_);
    try {
      let job: DanfePrintResponse;
      try {
        job = await $fetch<DanfePrintResponse>(
          `/api/v1/backstage/orders/${encodeURIComponent(ref_)}/danfe-escpos/`,
          { method: "POST", body: { local_agent: hasLocalAgent.value } },
        );
      } catch (error) {
        useSonner.error(httpErrorMessage(error, `A DANFE do pedido ${ref_} não foi impressa. Tente de novo.`));
        return false;
      }
      if (job.via === "relay") {
        useSonner.success(
          job.reprint
            ? `Reimpressão da DANFE do pedido ${ref_} enviada para a impressora de ${job.target_label}.`
            : `DANFE do pedido ${ref_} enviada para a impressora de ${job.target_label}.`,
        );
        return true;
      }
      const agent = deviceAgent.value;
      if (!agent) return false;
      try {
        await printWithLocalDeviceAgent(agent, job.payload_b64, job.title);
      } catch (error) {
        useSonner.error(`A DANFE do pedido ${ref_} não saiu: ${localDeviceAgentErrorMessage(error)}`);
        return false;
      }
      useSonner.success(job.reprint ? `DANFE do pedido ${ref_} reimpressa.` : `DANFE do pedido ${ref_} impressa.`);
      return true;
    } finally {
      const next = new Set(printing.value);
      next.delete(ref_);
      printing.value = next;
      void refresh();
    }
  }

  return { isPrinting, printDanfe };
}
