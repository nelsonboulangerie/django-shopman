import type { ComputedRef } from "vue";
import { toast } from "vue-sonner";

import type { Action, POSCashManagementCapability, POSProjection } from "~/types/pos";
import { requiresOpenShiftForSale } from "~/presentation/cash";
import { actionHref } from "~/utils/posIntent";

interface CashSessionDeps {
  pos: ComputedRef<POSProjection | null>;
  actions: ComputedRef<Action[]>;
  refresh: () => Promise<void>;
  action: { call: (path: string, opts?: { body?: Record<string, unknown> }) => Promise<unknown> };
}

/**
 * Write-side da SESSÃO de caixa (antesala): abrir/fechar turno, fechar turno
 * bloqueante e movimentos (sangria/suprimento/ajuste). Vivia dentro do
 * usePosSale quando o caixa era um diálogo da tela de venda; com a antesala
 * (`/session`) a sessão tem tela própria e o write-side acompanha. Cada ação
 * devolve `true` no sucesso para a página decidir navegação (ex.: abrir caixa
 * → ir vender). Erros sobem como toast, mesmo dialeto do restante do PDV.
 */
export function usePosCashSession({ pos, actions, refresh, action }: CashSessionDeps) {
  const busy = ref(false);

  // Sangria e suprimento mexem no dinheiro da gaveta e não imprimem nada — por
  // isso o gancho "abrir ao imprimir" do driver nunca serviria aqui. Mesmo
  // caminho da venda em dinheiro: um só, para os quatro momentos.
  const drawer = useCashDrawer(pos);

  const cashManagement = computed<POSCashManagementCapability | null>(
    () => pos.value?.checkout?.capabilities?.cash_management ?? null,
  );
  const movementKinds = computed<string[]>(
    () => cashManagement.value?.movement_kinds || ["sangria", "suprimento", "ajuste"],
  );
  // O bloqueio de venda sem turno é contrato da Projection (hoje sempre true);
  // o gate de redirect da antesala lê daqui em vez de assumir.
  const shiftRequiredForSale = computed(() => requiresOpenShiftForSale(cashManagement.value));

  // Desafio de gerente pendente numa retirada: a página abre o diálogo de PIN e
  // reenvia o mesmo movimento com a autorização. Vazio = nada pendente.
  const managerChallenge = ref<{ code: string; message: string } | null>(null);

  async function run(path: string, body: Record<string, unknown>, failMessage: string): Promise<boolean> {
    if (busy.value) return false;
    busy.value = true;
    try {
      await action.call(path, { body });
      await refresh();
      return true;
    } catch (error) {
      const code = httpErrorCode(error);
      if (code === "manager_approval_required" || code === "manager_approval_invalid") {
        managerChallenge.value = { code, message: httpErrorMessage(error, failMessage) };
        return false;
      }
      toast.error(httpErrorMessage(error, failMessage));
      return false;
    } finally {
      busy.value = false;
    }
  }

  function openCashShift(amount: string): Promise<boolean> {
    return run(
      actionHref(actions.value, "open_cash_shift", "/api/v1/backstage/pos/cash/open/"),
      { opening_amount: amount || "0", terminal_ref: pos.value?.terminal_ref || "" },
      "Falha ao abrir caixa.",
    );
  }

  function closeCashShift(payload: { amount: string; notes: string }): Promise<boolean> {
    return run(
      actionHref(actions.value, "close_cash_shift", "/api/v1/backstage/pos/cash/close/"),
      { closing_amount: payload.amount || "0", notes: payload.notes },
      "Falha ao fechar caixa.",
    );
  }

  // Fecha (contagem cega) o turno que bloqueia o terminal — gerente ou dono.
  // Destrava o terminal para o operador atual abrir o seu.
  function closeBlockingShift(payload: { shift_id: number; amount: string; notes: string }): Promise<boolean> {
    return run(
      "/api/v1/backstage/pos/cash/close-blocking/",
      { shift_id: payload.shift_id, closing_amount: payload.amount || "0", notes: payload.notes },
      "Falha ao fechar o turno.",
    );
  }

  // Retirada de gaveta (sangria, ajuste negativo) exige PIN do gerente. Quem
  // decide é o servidor: a tela envia, e só abre o desafio quando ele recusa com
  // `manager_approval_required`. Assim a regra do que precisa de autorização tem
  // um dono só, e o PDV não precisa adivinhar antes de perguntar.
  function registerCashMovement(payload: {
    kind: string;
    amount: string;
    reason: string;
    managerApproval?: { username: string; pin: string } | null;
  }): Promise<boolean> {
    const body: Record<string, unknown> = {
      kind: payload.kind,
      amount: payload.amount || "0",
      reason: payload.reason,
    };
    if (payload.managerApproval) body.manager_approval = payload.managerApproval;
    return run(
      actionHref(actions.value, "cash_movement", "/api/v1/backstage/pos/cash/movement/"),
      body,
      "Falha ao registrar movimento.",
    ).then((ok) => {
      // Só abre depois do servidor aceitar: gaveta aberta por um movimento que
      // foi recusado (PIN errado, caixa fechado) é dinheiro exposto sem lastro.
      if (ok) void drawer.kick(payload.kind);
      return ok;
    });
  }

  /**
   * Abrir a gaveta sem venda e sem movimento — conferência, troco, o que for.
   *
   * É o único dos quatro momentos que não deixa rastro sozinho: não há pedido
   * nem `CashMovement` contando a história depois. Por isso passa pelo servidor
   * ANTES de chutar: primeiro a linha na trilha, depois a gaveta. Se o registro
   * falhar, a gaveta não abre — senão sobraria justamente o buraco que a chave
   * física já deixava.
   */
  async function openDrawerWithoutSale(reason: string): Promise<boolean> {
    if (busy.value) return false;
    const registered = await run(
      actionHref(actions.value, "drawer_open", "/api/v1/backstage/pos/cash/drawer-open/"),
      { reason },
      "Falha ao registrar a abertura.",
    );
    if (!registered) return false;
    return drawer.kick("no_sale");
  }

  return {
    busy,
    movementKinds,
    shiftRequiredForSale,
    managerChallenge,
    openCashShift,
    closeCashShift,
    closeBlockingShift,
    registerCashMovement,
    // Gaveta: a antesala mostra o botão só onde existe caminho de software.
    canOpenDrawer: drawer.canKick,
    drawerUnavailableReason: drawer.unavailableReason,
    drawerProbing: drawer.probing,
    openDrawerWithoutSale,
    probeDrawer: drawer.probe,
  };
}
