import type { ComputedRef } from "vue";

import type { useCounterAgent } from "~/composables/useCounterAgent";
import {
  drawerOpeningMessage,
  type DrawerOpeningPurpose,
  type DrawerOpeningState,
  type DrawerRelayCapability,
  type PendingCashDrawer,
} from "~/presentation/drawerOpening";
import type { Action, POSProjection } from "~/types/pos";
import { actionHref } from "~/utils/posIntent";

interface DrawerOpeningDeps {
  pos: ComputedRef<POSProjection | null>;
  actions: ComputedRef<Action[]>;
  action: {
    call: <T = unknown>(
      path: string,
      opts?: { method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE"; body?: Record<string, unknown> },
    ) => Promise<T>;
  };
  drawer: ReturnType<typeof useCounterAgent>;
}

interface PulseBody {
  ok?: boolean;
  entry_id?: number;
  pulse?: { ref: string; state: DrawerOpeningState; message: string } | null;
}

/** O agente busca trabalho a cada 2 s; o pulso vale 30 s e o lease 45 s. */
const POLL_EVERY_MS = 1000;
const POLL_LIMIT_MS = 50_000;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Abrir a gaveta de qualquer posto, com autoria (decisão do dono, 04/10/2026).
 *
 * Um gesto, dois caminhos, um registro no livro:
 *
 * - **no Balcão** (o agente responde na loopback desta máquina): grava a abertura
 *   (`via: local`) e só então chuta, como sempre;
 * - **no tablet** (o agente não está aqui): pede ao servidor (`via: relay`), que
 *   grava a abertura e põe o pulso na fila do agente do Balcão; a tela acompanha
 *   o pulso até o agente responder ou o prazo vencer.
 *
 * ⚠️ Nunca finge sucesso: sem rede, sem relay ou sem resposta do agente, o estado
 * diz que a gaveta NÃO abriu e por quê. Quem é o autor é quem está neste
 * dispositivo (o PIN dele), não quem está logado no PC do Balcão.
 */
export function useDrawerOpening({ pos, actions, action, drawer }: DrawerOpeningDeps) {
  const state = ref<DrawerOpeningState>("idle");
  const message = ref("");
  /**
   * O dinheiro das vendas do tablet esperando a gaveta, um cartão por venda. Fica
   * de pé depois da "Nova venda": o atendente pode atender outra mesa no caminho.
   */
  const pendingCash = ref<PendingCashDrawer[]>([]);
  /** A venda cujo dinheiro está sendo guardado agora (o estado acima é dela). */
  const openingRef = ref("");

  const relay = computed<DrawerRelayCapability | null>(() => pos.value?.drawer_relay ?? null);
  const terminalLabel = computed(() => relay.value?.terminal_label || pos.value?.terminal_label || "Balcão");
  /** Existe ALGUM caminho de abrir por software (local ou relay)? */
  const canOpen = computed(() => drawer.canKick.value || Boolean(relay.value?.available));
  const busy = computed(() => state.value === "sending");

  function settle(next: DrawerOpeningState, serverMessage = "") {
    state.value = next;
    message.value = drawerOpeningMessage(next, terminalLabel.value, serverMessage);
  }

  function reset() {
    state.value = "idle";
    message.value = "";
  }

  function drawerOpenPath(): string {
    return actionHref(actions.value, "drawer_open", "/api/v1/backstage/pos/cash/drawer-open/");
  }

  async function post(body: Record<string, unknown>): Promise<PulseBody | null> {
    try {
      return await action.call<PulseBody>(drawerOpenPath(), { body });
    } catch (error) {
      const info = httpError(error);
      if (!info.status) {
        settle("offline");
      } else {
        settle("failed", httpErrorMessage(error, "A abertura não entrou no livro-caixa: a gaveta não abriu."));
      }
      return null;
    }
  }

  async function followPulse(ref: string): Promise<void> {
    const started = Date.now();
    const path = `/api/v1/backstage/pos/cash/drawer-pulse/${encodeURIComponent(ref)}/`;
    while (Date.now() - started < POLL_LIMIT_MS) {
      await sleep(POLL_EVERY_MS);
      try {
        const body = await action.call<{ pulse: { state: DrawerOpeningState; message: string } }>(path, {
          method: "GET",
        });
        if (body.pulse.state !== "sending") {
          settle(body.pulse.state, body.pulse.message);
          return;
        }
      } catch (error) {
        if (!httpError(error).status) {
          // A rede do tablet caiu no meio: não dá para saber se abriu.
          settle("uncertain", `Sem conexão para confirmar. Olhe a gaveta do ${terminalLabel.value} antes de pedir de novo.`);
          return;
        }
      }
    }
    settle("uncertain");
  }

  /**
   * Abre a gaveta. `purpose: "sale"` leva o pedido; `"no_sale"` leva o motivo.
   * Devolve `true` só quando a gaveta abriu (ou o chute local foi aceito).
   */
  async function open(opts: { purpose: DrawerOpeningPurpose; orderRef?: string; reason?: string }): Promise<boolean> {
    if (busy.value) return false;
    openingRef.value = opts.orderRef || "";
    if (import.meta.client && typeof navigator !== "undefined" && navigator.onLine === false) {
      settle("offline");
      return false;
    }
    settle("sending");
    const body: Record<string, unknown> = { purpose: opts.purpose };
    if (opts.orderRef) body.order_ref = opts.orderRef;
    if (opts.reason) body.reason = opts.reason;

    if (await drawer.reachable()) {
      const registered = await post({ ...body, via: "local" });
      if (!registered) return false;
      const kicked = await drawer.kick(opts.purpose === "sale" ? "cash_sale" : "no_sale");
      settle(kicked ? "sent" : "failed");
      return kicked;
    }

    if (!relay.value?.available) {
      settle("failed", relay.value?.reason || drawer.unavailableReason.value);
      return false;
    }
    const answer = await post({ ...body, via: "relay" });
    if (!answer) return false;
    if (!answer.pulse) {
      settle("failed");
      return false;
    }
    await followPulse(answer.pulse.ref);
    const opened = state.value === "sent";
    if (opened && opts.purpose === "sale") {
      pendingCash.value = pendingCash.value.filter((item) => item.orderRef !== opts.orderRef);
    }
    return opened;
  }

  /**
   * Depois de uma venda que pôs dinheiro na gaveta. No Balcão, abre sozinha (se
   * o dono deixou) e registra; no tablet, NUNCA abre sozinha: guarda o cartão
   * para o atendente tocar quando estiver na frente da gaveta.
   */
  async function afterCashSale(sale: PendingCashDrawer, openOnCashSale: boolean): Promise<void> {
    reset();
    if (await drawer.reachable()) {
      if (!openOnCashSale) return;
      const kicked = await drawer.kick("cash_sale");
      // O registro vem depois do chute: o dinheiro já está na mão e a linha
      // `sale` já está no livro. Falhar aqui não fecha a gaveta nem refaz a venda.
      if (kicked) {
        void action
          .call(drawerOpenPath(), { body: { purpose: "sale", order_ref: sale.orderRef, via: "local" } })
          .catch(() => {});
      }
      return;
    }
    if (!canOpen.value) return;
    pendingCash.value = [...pendingCash.value.filter((item) => item.orderRef !== sale.orderRef), sale];
  }

  /** "Abri na chave": o cartão sai sem pulso (a abertura física não passou por aqui). */
  function dismissPendingCash(orderRef: string) {
    pendingCash.value = pendingCash.value.filter((item) => item.orderRef !== orderRef);
    if (openingRef.value === orderRef) reset();
  }

  return {
    state,
    message,
    busy,
    canOpen,
    relay,
    terminalLabel,
    pendingCash,
    openingRef,
    open,
    afterCashSale,
    dismissPendingCash,
    reset,
  };
}
