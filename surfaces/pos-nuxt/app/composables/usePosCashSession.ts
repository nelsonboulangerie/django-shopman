import type { ComputedRef } from "vue";
import { toast } from "vue-sonner";

import type { PrintOutcome } from "~/composables/useCashDrawer";
import type { Action, POSCashManagementCapability, POSProjection } from "~/types/pos";
import { requiresOpenShiftForSale } from "~/presentation/cash";
import { actionHref } from "~/utils/posIntent";

interface CashSessionDeps {
  pos: ComputedRef<POSProjection | null>;
  actions: ComputedRef<Action[]>;
  refresh: () => Promise<void>;
  // Genérico e com `method` porque o comprovante é LIDO antes de ser impresso:
  // o servidor compõe os bytes, a tela só relaia.
  action: {
    call: <T = unknown>(
      path: string,
      opts?: { method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE"; body?: Record<string, unknown> },
    ) => Promise<T>;
  };
}

/**
 * Write-side da SESSÃO de caixa (antesala): abrir/fechar turno, fechar turno
 * bloqueante e movimentos (sangria/suprimento). Vivia dentro do
 * usePosSale quando o caixa era um diálogo da tela de venda; com a antesala
 * (`/session`) a sessão tem tela própria e o write-side acompanha. Cada ação
 * devolve `true` no sucesso para a página decidir navegação (ex.: abrir caixa
 * → ir vender). Erros sobem como toast, mesmo dialeto do restante do PDV.
 */
/**
 * A autorização do gerente, pelas DUAS portas.
 *
 * `{username, pin}` ou `{badge}`: o servidor aceita as duas, resolve a mesma
 * pessoa, exige a mesma `cashman.adjust_shift` e grava a mesma assinatura em
 * `Entry.approved_by`. Um tipo só aqui evita que uma das chamadas aceite crachá
 * e a vizinha não — que é como o crachá acabou faltando na sangria.
 */
export interface ManagerApproval {
  username?: string;
  pin?: string;
  badge?: string;
}

export function usePosCashSession({ pos, actions, refresh, action }: CashSessionDeps) {
  const busy = ref(false);
  // O id do último lançamento (sangria/suprimento) aceito pelo servidor — é
  // dele que sai o comprovante: a linha do livro do turno (`cashman.Entry`).
  const lastEntryId = ref<number | null>(null);

  // Sangria e suprimento mexem no dinheiro da gaveta e não imprimem nada — por
  // isso o gancho "abrir ao imprimir" do driver nunca serviria aqui. Mesmo
  // caminho da venda em dinheiro: um só, para os quatro momentos.
  const drawer = useCashDrawer(pos);

  const cashManagement = computed<POSCashManagementCapability | null>(
    () => pos.value?.checkout?.capabilities?.cash_management ?? null,
  );
  const movementKinds = computed<string[]>(
    () => cashManagement.value?.movement_kinds || ["sangria", "suprimento"],
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
      const resposta = await action.call<{ entry_id?: number }>(path, { body });
      lastEntryId.value = resposta?.entry_id ?? null;
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

  // Retirada de gaveta (sangria) exige PIN do gerente. Quem
  // decide é o servidor: a tela envia, e só abre o desafio quando ele recusa com
  // `manager_approval_required`. Assim a regra do que precisa de autorização tem
  // um dono só, e o PDV não precisa adivinhar antes de perguntar.
  function registerCashMovement(payload: {
    kind: string;
    amount: string;
    reason: string;
    managerApproval?: ManagerApproval | null;
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
      if (ok) {
        void drawer.kick(payload.kind);
        void printMovementReceipt(lastEntryId.value);
      }
      return ok;
    });
  }

  /**
   * Imprime o comprovante e REGISTRA o que aconteceu com o papel.
   *
   * O comprovante nasceu de "sangria sem testemunha" — o mesmo motivo do PIN.
   * Por isso sai sozinho: testemunha que depende de alguém lembrar de clicar
   * não é testemunha.
   *
   * ⚠️ A falha NÃO desfaz o movimento. O dinheiro já saiu e o registro já
   * existe; travar o caixa porque a impressora emperrou seria remédio pior que
   * a doença. O que não pode é a falha passar calada — ela vira registro e
   * toast, e o papel pode ser reimpresso depois.
   */
  async function printMovementReceipt(entryId: number | null): Promise<void> {
    if (!entryId) return;
    const base = `/api/v1/backstage/pos/cash/entry/${entryId}/receipt/`;
    let outcome: PrintOutcome;
    try {
      const receipt = await action.call<{ payload_b64: string; title: string }>(base, { method: "GET" });
      outcome = await drawer.print(receipt.payload_b64, receipt.title);
    } catch (error) {
      outcome = { status: "failed", detail: httpErrorMessage(error, "Falha ao montar o comprovante.") };
    }
    if (outcome.status === "failed") {
      toast.error(`O comprovante não saiu: ${outcome.detail}`);
    }
    // Registrar é o ponto todo: sem isto, papel que faltou parece papel que
    // alguém escondeu. Se ESTA chamada falhar, o movimento fica "sem
    // confirmação" — honesto, porque é exatamente o que sabemos.
    await action
      .call(base, { body: { status: outcome.status, detail: outcome.detail } })
      .catch(() => {});
  }

  /**
   * Abrir a gaveta sem venda e sem movimento — conferência, troco, o que for.
   *
   * É o único dos quatro momentos que não deixa rastro sozinho: não há pedido
   * nem sangria/suprimento contando a história depois. Por isso passa pelo servidor
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

  // ── Pedido de troco ─────────────────────────────────────────────────────
  //
  // Faltou troco: em vez de o operador atravessar a loja com dinheiro até o
  // cofre — trajeto que a câmera só cobre em parte, e cuja falta só apareceria
  // no fechamento —, ele PEDE, alguém traz, e a troca acontece no balcão entre
  // duas pessoas.
  //
  // ⚠️ NENHUMA destas três funções mexe em dinheiro. Trocar é net zero: saem
  // R$ 50, entram 5×R$ 10, o total da gaveta não muda. Se alguma delas passar
  // por `cash/movement/`, o esperado do fechamento cai por um dinheiro que nunca
  // saiu e o turno fecha com falta fantasma.

  const pendingChangeRequests = computed(
    () => pos.value?.cash_runtime?.pending_change_requests ?? [],
  );

  function requestChange(
    payload: { amount: string; denominations: number[]; note: string },
  ): Promise<boolean> {
    return run(
      actionHref(actions.value, "request_change", "/api/v1/backstage/pos/cash/change-request/"),
      { amount: payload.amount, denominations: payload.denominations, note: payload.note },
      "Falha ao pedir troco.",
    );
  }

  /**
   * O gerente atende no balcão: PIN, gaveta abre, a troca acontece à vista.
   *
   * Envia sem aprovação primeiro, como a sangria ao lado: quem decide o que
   * exige assinatura é o SERVIDOR. Duplicar essa regra na tela daria dois donos
   * para a mesma pergunta, e o dia em que divergissem a tela é que estaria
   * errada — mas quem pagaria seria a gaveta.
   */
  function serveChangeRequest(payload: {
    ref: string;
    managerApproval?: ManagerApproval | null;
  }): Promise<boolean> {
    const body: Record<string, unknown> = {};
    if (payload.managerApproval) body.manager_approval = payload.managerApproval;
    return run(
      `/api/v1/backstage/pos/cash/change-request/${encodeURIComponent(payload.ref)}/serve/`,
      body,
      "Falha ao atender o pedido.",
    ).then((ok) => {
      // Só depois do `ok`: gaveta aberta por um atendimento recusado (PIN
      // errado, pedido já resolvido) é dinheiro exposto sem lastro.
      if (ok) void drawer.kick("change_request");
      return ok;
    });
  }

  // Devolução em dinheiro de venda cancelada. Cancelar não é devolver: o
  // gestor cancela de noite e ninguém abriu gaveta; a pendência fica aqui até
  // quem está com a gaveta aberta entregar as notas, com PIN de gerente (dinheiro
  // sai da gaveta com segunda assinatura, como a sangria). Só então o servidor
  // grava Payman e livro, juntos.
  const pendingCashRefunds = computed(
    () => pos.value?.cash_runtime?.pending_cash_refunds ?? [],
  );

  function refundCash(payload: {
    orderRef: string;
    managerApproval?: ManagerApproval | null;
  }): Promise<boolean> {
    const body: Record<string, unknown> = {};
    if (payload.managerApproval) body.manager_approval = payload.managerApproval;
    return run(
      `/api/v1/backstage/pos/cash/refund/${encodeURIComponent(payload.orderRef)}/`,
      body,
      "Falha ao devolver o dinheiro.",
    ).then((ok) => {
      // A gaveta abre para entregar as notas, e só depois do `ok`: devolução
      // recusada (PIN errado, já devolvida) não pode abrir a gaveta.
      if (ok) void drawer.kick("cash_refund");
      return ok;
    });
  }

  // Conta na casa: o cliente acerta (parte d)a conta. Em dinheiro, entra neste
  // turno; pix/cartão é atestado no balcão. O servidor captura por venda inteira
  // (FIFO) e recusa valor que não cobre nem a mais antiga.
  const accountBalances = computed(() => pos.value?.cash_runtime?.account_balances ?? []);

  function settleAccount(payload: { customerRef: string; amount: string; method: string }): Promise<boolean> {
    return run(
      `/api/v1/backstage/pos/accounts/${encodeURIComponent(payload.customerRef)}/settle/`,
      { amount: payload.amount, method: payload.method },
      "Falha ao receber o acerto.",
    ).then((ok) => {
      // Dinheiro entrando: a gaveta abre para guardar, depois do `ok`.
      if (ok && payload.method === "cash") void drawer.kick("account_settled");
      return ok;
    });
  }

  function cancelChangeRequest(ref: string): Promise<boolean> {
    return run(
      `/api/v1/backstage/pos/cash/change-request/${encodeURIComponent(ref)}/cancel/`,
      {},
      "Falha ao cancelar o pedido.",
    );
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
    // Pedido de troco: o dinheiro fica no balcão, o troco vem até ele.
    pendingChangeRequests,
    requestChange,
    serveChangeRequest,
    cancelChangeRequest,
    // Devolução em dinheiro de venda cancelada: o gesto físico, com PIN.
    pendingCashRefunds,
    refundCash,
    // Conta na casa: saldos em aberto e o acerto.
    accountBalances,
    settleAccount,
  };
}
