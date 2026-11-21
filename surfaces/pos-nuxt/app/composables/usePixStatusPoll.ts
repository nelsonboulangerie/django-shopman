import { POS_REQUEST_TIMEOUT_MS } from "~/composables/usePosAction";
import type { POSPaymentDeliveryProjection } from "~/types/pos";
import { timeoutSignal } from "../../../operator-kit/app/composables/useReachability";

/** O que o status por pedido responde (`pos/payment/<ref>/status/`). */
export interface PixStatusRead {
  is_paid?: boolean;
  is_terminal?: boolean;
  payment_delivery?: POSPaymentDeliveryProjection;
}

/** Como a espera do Pix acabou: pagou, morreu no servidor, ou passou do prazo. */
export type PixPollOutcome = "paid" | "terminal" | "deadline";

/**
 * A ESPERA DO PIX NO BALCÃO, uma só: a venda (`usePosSale`) e o saldo da encomenda
 * (`PosPreorderBalancePayment`) acompanham o Pix pelo MESMO status por pedido
 * (`pos/payment/<ref>/status/`, gateado por `operate_pos`), na mesma cadência.
 *
 * Quem decide que o Pix venceu é o status (`is_terminal`); a desistência local só
 * vale quando o servidor nem responde, e espera o prazo do Pix mais a folga
 * (`pendingPixDeadlineMs`). A tentativa isolada que falha não fala: a desistência
 * é que fala, e fala alto (quem chama decide o aviso).
 */
export function usePixStatusPoll() {
  const apiPath = useApiPath();
  let timer: ReturnType<typeof setInterval> | null = null;
  let generation = 0;

  function stop(expectedGeneration?: number) {
    if (expectedGeneration !== undefined && expectedGeneration !== generation) return;
    generation += 1;
    if (timer) { clearInterval(timer); timer = null; }
  }

  function start(orderRef: string, options: {
    deadlineMs: number;
    onStatus?: (status: PixStatusRead) => void;
    onOutcome: (outcome: PixPollOutcome) => void;
  }): void {
    stop();
    let inFlight = false;
    const current = generation;
    timer = setInterval(async () => {
      if (current !== generation) return;
      if (Date.now() >= options.deadlineMs) {
        stop(current);
        options.onOutcome("deadline");
        return;
      }
      if (inFlight) return;
      inFlight = true;
      try {
        const status = await $fetch<PixStatusRead>(
          apiPath(`/api/v1/backstage/pos/payment/${encodeURIComponent(orderRef)}/status/`),
          { credentials: "include", signal: timeoutSignal(POS_REQUEST_TIMEOUT_MS) },
        );
        if (current !== generation) return;
        options.onStatus?.(status);
        if (status?.is_paid) {
          stop(current);
          options.onOutcome("paid");
        } else if (status?.is_terminal) {
          stop(current);
          options.onOutcome("terminal");
        }
      } catch { /* silêncio-deliberado: falha transiente de rede, segue tentando */ }
      finally { inFlight = false; }
    }, 2500);
  }

  return { start, stop };
}
