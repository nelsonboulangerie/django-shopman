import type { ComputedRef } from "vue";
import { toast } from "vue-sonner";

import type { DrawerState } from "~/composables/useCashDrawer";
import type { Action } from "~/types/pos";
import { actionHref } from "~/utils/posIntent";

interface DrawerLockDeps {
  drawer: { readState: () => Promise<DrawerState> };
  actions: ComputedRef<Action[]>;
  action: {
    call: <T = unknown>(path: string, opts?: { body?: Record<string, unknown> }) => Promise<T>;
  };
}

/**
 * A trava da gaveta: o PDV recusa INICIAR a próxima venda enquanto SABE que a
 * gaveta está aberta.
 *
 * As regras foram decididas e não se reabrem aqui:
 *
 * - **Trava ao iniciar** a próxima venda, nunca no meio de uma. Venda começada
 *   não vira refém.
 * - **Sem carência.** Se a trava é na próxima venda, o operador já teve o tempo
 *   dele. Carência transformaria a exceção em rotina invisível.
 * - **Só trava quando SABE.** Estado desconhecido (agente fora, estação sem
 *   medição, gaveta de chave) NUNCA trava. Isso inverte o modo de falha: sensor
 *   ruim degrada para "sem controle", jamais para "balcão parado com fila".
 * - **Gerente destrava com PIN**, e o destrave vai para o log do servidor. É para
 *   a gaveta emperrada, que existe. Cada destrave vale UMA venda.
 *
 * Quem lê a gaveta é a página (o agente vive na loopback do balcão; o servidor
 * não alcança). O servidor só entra no destrave, para registrar quem liberou.
 */
export function useDrawerLock({ drawer, actions, action }: DrawerLockDeps) {
  /** Diálogo "gaveta aberta" na tela. */
  const open = ref(false);
  /** O operador disse "já fechei" e a gaveta continuava aberta. */
  const stillOpen = ref(false);
  /** Diálogo de PIN do gerente por cima da trava. */
  const managerOpen = ref(false);
  const managerError = ref("");
  /** Lendo o sensor ou registrando o destrave. */
  const busy = ref(false);

  // O que o sensor disse quando travou, para o destrave levar a prova ao log.
  let lastRaw = "";
  // A venda que ficou esperando atrás da trava.
  let pending: (() => Promise<void>) | null = null;

  /**
   * Guarda a próxima venda. Se a gaveta está sabidamente aberta, segura o
   * `proceed`, abre o diálogo e devolve. Em todos os outros casos (fechada,
   * desconhecida, sem agente) chama `proceed` na hora.
   */
  async function guard(proceed: () => Promise<void>): Promise<void> {
    if (busy.value) return;
    busy.value = true;
    let state: DrawerState;
    try {
      state = await drawer.readState();
    } finally {
      busy.value = false;
    }
    if (!(state.known && state.open)) {
      await proceed();
      return;
    }
    lastRaw = state.raw;
    pending = proceed;
    stillOpen.value = false;
    managerError.value = "";
    open.value = true;
  }

  /** "Já fechei": lê de novo. Fechou (ou parou de dar para saber) → a venda segue. */
  async function recheck(): Promise<void> {
    if (busy.value) return;
    busy.value = true;
    try {
      const state = await drawer.readState();
      if (state.known && state.open) {
        stillOpen.value = true;
        return;
      }
      await release();
    } finally {
      busy.value = false;
    }
  }

  function askManager() {
    managerError.value = "";
    managerOpen.value = true;
  }

  /**
   * O gerente assina. O servidor valida o PIN e grava o evento; só depois a
   * venda segue. Erro de PIN volta para o diálogo do gerente (não para um toast
   * que some), senão o gerente reenvia o mesmo PIN errado para sempre.
   */
  async function unlock(username: string, pin: string): Promise<void> {
    return autorizar({ username, pin });
  }

  /** Mesma autorização, pelo crachá. Ver `ManagerApproval` no `usePosCashSession`. */
  async function unlockWithBadge(badge: string): Promise<void> {
    return autorizar({ badge });
  }

  async function autorizar(aprovacao: Record<string, string>): Promise<void> {
    if (busy.value) return;
    busy.value = true;
    try {
      const body: Record<string, unknown> = { manager_approval: aprovacao };
      if (lastRaw) body.drawer_raw = lastRaw;
      await action.call(
        actionHref(actions.value, "drawer_unlock", "/api/v1/backstage/pos/cash/drawer-unlock/"),
        { body },
      );
      managerOpen.value = false;
      await release();
    } catch (error) {
      const code = httpErrorCode(error);
      const message = httpErrorMessage(error, "Falha ao liberar a gaveta.");
      if (code === "manager_approval_required" || code === "manager_approval_invalid") {
        managerError.value = message;
        return;
      }
      toast.error(message);
    } finally {
      busy.value = false;
    }
  }

  /** Desiste: a venda que esperava não acontece. */
  function dismiss() {
    open.value = false;
    managerOpen.value = false;
    pending = null;
  }

  async function release(): Promise<void> {
    const proceed = pending;
    pending = null;
    open.value = false;
    stillOpen.value = false;
    if (proceed) await proceed();
  }

  return { open, stillOpen, managerOpen, managerError, busy, guard, recheck, askManager, unlock, unlockWithBadge, dismiss };
}
