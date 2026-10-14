import type { ComputedRef } from "vue";
import { toast } from "vue-sonner";

import type { POSProjection } from "~/types/pos";

type CounterAgent = Pick<ReturnType<typeof useCounterAgent>, "print">;

/**
 * A DANFE na bobina, esperando a nota autorizar: um caminho só para a venda de
 * balcão (`pages/index.vue`) e a encomenda entregue no balcão
 * (`usePosPreorderActions`, P2-27 do mapa de cenários).
 *
 * A NFC-e é assíncrona: no instante do gesto ela ainda não autorizou (o
 * endpoint responde 409 até lá). Então espera, com fim: ~90s (30 tentativas de
 * 3s). Nota que demora mais que isso não aparece enquanto o cliente está no
 * balcão, e insistir para sempre deixaria um timer vivo atrás de cada venda.
 * Quando desiste, não desiste calado: cai no aviso que diz o próximo passo.
 */
export const DANFE_WAIT_TRIES = 30;
export const DANFE_WAIT_INTERVAL_MS = 3000;

export function usePosDanfePrint(pos: ComputedRef<POSProjection | null>, agent: CounterAgent) {
  const apiPath = useApiPath();
  const runtimeConfig = useRuntimeConfig();
  // O Django mora em outro subdomínio: o link da nota na tela é absoluto.
  const djangoOrigin = computed(() => String(runtimeConfig.public.djangoBaseUrl || ""));
  let timer: ReturnType<typeof setTimeout> | null = null;

  /** A nota aberta na tela (host do Django): a mesma DANFE da bobina, para leitura. */
  function screenUrl(orderRef: string): string {
    return `${djangoOrigin.value}/fiscal/danfe/${encodeURIComponent(orderRef)}/`;
  }

  async function fetchDanfe(orderRef: string) {
    return await $fetch<{ payload_b64: string; title: string }>(
      apiPath(`/api/v1/backstage/pos/orders/${encodeURIComponent(orderRef)}/danfe-escpos/`),
      { credentials: "include" },
    );
  }

  /**
   * Falha nunca termina em "indisponível" seco: quem tem acesso ganha a nota na
   * tela como ação; quem não tem ganha o próximo passo. As últimas vendas
   * listam também a encomenda retirada hoje (`build_pos_recent_sales`).
   */
  function fallbackToast(orderRef: string, reason: string) {
    if (pos.value?.danfe_screen_allowed && djangoOrigin.value) {
      toast.error(`A DANFE não saiu na bobina: ${reason}`, {
        action: {
          label: "Ver a nota na tela",
          onClick: () => window.open(screenUrl(orderRef), "_blank", "noopener"),
        },
      });
    } else {
      toast.error(`A DANFE não saiu na bobina: ${reason}. Reimprima nas últimas vendas quando o agente voltar.`);
    }
  }

  function stop() {
    if (timer) clearTimeout(timer);
    timer = null;
  }

  /**
   * Espera a nota autorizar e imprime. `onAuthorized` avisa quem mostra o estado
   * da nota (o 409 virou 200: a nota EXISTE). Uma espera por vez.
   */
  async function printWhenAuthorized(
    orderRef: string,
    options: { onAuthorized?: () => void } = {},
    tries = 0,
  ): Promise<void> {
    if (!import.meta.client) return;
    if (tries === 0) stop();
    try {
      const danfe = await fetchDanfe(orderRef);
      options.onAuthorized?.();
      const outcome = await agent.print(danfe.payload_b64, danfe.title);
      if (outcome.status === "printed") {
        toast.success("DANFE impressa.");
        return;
      }
      fallbackToast(orderRef, outcome.detail || "impressão indisponível nesta estação");
    } catch {
      // 409 enquanto a SEFAZ não autoriza: tentar de novo é o comportamento certo.
      if (tries + 1 < DANFE_WAIT_TRIES) {
        timer = setTimeout(() => void printWhenAuthorized(orderRef, options, tries + 1), DANFE_WAIT_INTERVAL_MS);
        return;
      }
      fallbackToast(orderRef, "a nota demorou mais que o esperado para autorizar");
    }
  }

  return { screenUrl, fetchDanfe, fallbackToast, printWhenAuthorized, stop };
}
