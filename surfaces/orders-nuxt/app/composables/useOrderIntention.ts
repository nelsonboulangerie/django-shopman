import type { Action } from "~/generated/ordersContract";
import {
  COURIER_RIDE_PATH,
  courierRideAction,
  courierRideInputs,
  courierRideResource,
  type CourierRideCall,
  type CourierRideResult,
} from "~/presentation/courierRide";

type Intention = {
  key: string;
  owner: number;
  body: Record<string, unknown>;
  method: "POST" | "PATCH";
};
type Result = { outcome?: string; detail?: string; count?: number } & Omit<
  CourierRideResult,
  "outcome" | "detail"
>;

/** O que a incerteza é, dito pelo ato: "se o cancelamento foi gravado". */
const ORDER_OPERATION_SUBJECT: Record<string, string> = {
  cancel: "o cancelamento foi gravado",
  return: "a devolução foi gravada",
  "no-show": "o pedido foi encerrado como não retirado",
  "refund-retry": "o estorno foi pedido de novo",
  refund: "o estorno foi pedido",
  reject: "a recusa foi gravada",
  confirm: "o aceite foi gravado",
  advance: "o avanço do pedido foi gravado",
  notes: "a nota foi gravada",
  comment: "o comentário foi gravado",
  assign: "a atribuição foi gravada",
  unassign: "a liberação do pedido foi gravada",
  "settle-delivery-cash": "o recebimento foi gravado",
  "resend-payment-link": "o reenvio do link foi gravado",
  "requeue-fiscal": "o reprocessamento da NFC-e foi gravado",
  "undo-handoff": "o desfazer da saída foi gravado",
  "undo-ready": "o desfazer do pronto foi gravado",
  "courier-close-here": "a corrida foi encerrada aqui",
};

/**
 * A resposta não voltou e o recibo ainda não sabe: diga O QUE ficou incerto e o
 * que fazer. A frase antiga ("Resultado ainda desconhecido. Verifique esta
 * intenção…") não dizia nem uma coisa nem outra (dono, 07/11/2026).
 */
export function uncertainOutcomeMessage(
  subject = "a alteração foi gravada",
  where = "a tela",
  slow = false,
): string {
  return `${slow ? "O sistema demorou a responder. " : ""}Não deu para confirmar se ${subject}. Atualize ${where} para ver o estado atual antes de tentar de novo.`;
}

/** Session-only, person-bound intentions. Unknown results never create a new key. */
export function useOrderIntention() {
  const { data: session } = useNuxtData<{ operator?: { id: number } }>(
    "operator-session",
  );
  const pending = useState<Record<string, Intention>>(
    "orders-local-intentions",
    () => ({}),
  );
  watch(
    () => session.value?.operator?.id,
    (next) => {
      if (next)
        pending.value = Object.fromEntries(
          Object.entries(pending.value).filter(
            ([, intent]) => intent.owner === next,
          ),
        );
    },
  );

  async function readReceipt(
    resource: string,
    path: string,
    intent: Intention,
  ) {
    try {
      return await $fetch<Result>(path, {
        query: {
          idempotency_key: intent.key,
          ...(typeof intent.body.ref === "string"
            ? { ref: intent.body.ref }
            : {}),
        },
      });
    } catch (error) {
      const { status, data } = httpError(error);
      const body = data as { outcome?: unknown; code?: unknown } | null;
      const code =
        httpErrorCode(error) ||
        (typeof body?.code === "string" ? body.code : "");
      // Só o recibo de recusa definitiva libera outra intenção. Falha de leitura,
      // permissão ou chave com outro payload continua exigindo reconciliação.
      if (
        [400, 409, 422].includes(status) &&
        body?.outcome === "not_applied" &&
        ![
          "intention_conflict",
          "manager_approval_required",
          "manager_approval_invalid",
        ].includes(code) &&
        session.value?.operator?.id === intent.owner &&
        pending.value[resource]?.key === intent.key
      ) {
        Reflect.deleteProperty(pending.value, resource);
      }
      throw error;
    }
  }

  async function executePath(
    resource: string,
    path: string,
    action:
      | (Pick<Action, "enabled" | "reason" | "payload_schema"> &
          Partial<Pick<Action, "method">>)
      | undefined,
    inputs: Record<string, unknown>,
    approval?: Record<string, string>,
    uncertainty?: { subject?: string; where?: string },
  ) {
    const owner = session.value?.operator?.id;
    if (!owner) throw new Error("Identifique-se antes de continuar.");
    let intent = pending.value[resource];
    if (!intent) {
      // O que a tela leu: a revisão do pedido, ou a de cada pedido da corrida
      // (`base_revisions`, na chamada de uma corrida para vários).
      const observed =
        action?.payload_schema.base_revision ||
        Object.keys(
          (action?.payload_schema.base_revisions as
            | Record<string, unknown>
            | undefined) ?? {},
        ).length > 0;
      if (!action?.enabled || !observed) {
        throw new Error(
          action?.reason || "Atualize os dados antes de continuar.",
        );
      }
      intent = {
        owner,
        key: crypto.randomUUID(),
        method: action.method === "PATCH" ? "PATCH" : "POST",
        body: JSON.parse(
          JSON.stringify({ ...action.payload_schema, ...inputs }),
        ),
      };
      pending.value[resource] = intent;
    }
    const current = intent;
    const samePerson = () => session.value?.operator?.id === current.owner;
    if (
      Object.entries(inputs).some(
        ([key, value]) =>
          JSON.stringify(value) !== JSON.stringify(current.body[key]),
      )
    ) {
      const result = await readReceipt(resource, path, current);
      if (!samePerson())
        throw new Error("A identificação mudou. Confira os dados.");
      if (result.outcome === "applied") {
        Reflect.deleteProperty(pending.value, resource);
        throw new Error(
          "A gravação anterior foi confirmada. Seu novo rascunho ainda não foi salvo.",
        );
      }
      throw new Error(
        "Há uma gravação anterior sem resultado confirmado. Seu novo rascunho foi preservado.",
      );
    }
    const finish = (result: Result, slow = false) => {
      if (!samePerson())
        throw new Error(
          "A identificação mudou. Confira os dados antes de continuar.",
        );
      if (result.outcome === "applied") {
        Reflect.deleteProperty(pending.value, resource);
        return result;
      }
      throw new Error(
        result.detail ||
          uncertainOutcomeMessage(uncertainty?.subject, uncertainty?.where, slow),
      );
    };
    try {
      const result = await $fetch<Result>(path, {
        method: current.method,
        headers: { "Idempotency-Key": current.key },
        body: {
          ...current.body,
          ...(approval ? { manager_approval: approval } : {}),
        },
      });
      return finish(result);
    } catch (error) {
      if (!samePerson()) throw error;
      const status = httpError(error).status;
      // O servidor declarou que nada foi aplicado (recusa na fase de preparo, ex.:
      // iFood fora do ar ao ler os motivos). Vale mesmo em 5xx: sem isto a tela
      // tratava o 503 como "talvez gravou", prendia a intenção e toda tentativa
      // seguinte caía em "há uma gravação anterior" até o F5.
      const refusedBody = httpError(error).data as { outcome?: unknown } | null;
      if (status && status >= 500 && refusedBody?.outcome === "not_applied") {
        Reflect.deleteProperty(pending.value, resource);
        throw error;
      }
      if (status && status >= 400 && status < 500) {
        const directCode = (httpError(error).data as { code?: unknown } | null)
          ?.code;
        const code =
          httpErrorCode(error) ||
          (typeof directCode === "string" ? directCode : "");
        if (
          status !== 401 &&
          status !== 403 &&
          ![
            "intention_conflict",
            "manager_approval_required",
            "manager_approval_invalid",
          ].includes(code)
        )
          Reflect.deleteProperty(pending.value, resource);
        throw error;
      }
      // A resposta pode ter se perdido depois do commit. Consultar não executa efeitos.
      // É o caminho de toda falha SEM a declaração do servidor: 5xx do BFF (o
      // Django não respondeu em 25 s: ``upstream_timeout``; a borda respondeu no
      // lugar dele: ``upstream_unavailable``) ou queda de rede.
      const slow = httpErrorCode(error) === "upstream_timeout";
      const result = await readReceipt(resource, path, current);
      return finish(result, slow);
    }
  }
  async function checkPath(resource: string, path: string) {
    const intent = pending.value[resource];
    if (!intent || intent.owner !== session.value?.operator?.id)
      throw new Error(
        "Não há gravação pendente para consultar. Confira a ordem atual.",
      );
    const result = await readReceipt(resource, path, intent);
    if (intent.owner !== session.value?.operator?.id)
      throw new Error("A identificação mudou. Confira os dados.");
    if (result.outcome === "applied")
      Reflect.deleteProperty(pending.value, resource);
    return result;
  }
  /** A ação de UM pedido, devolvendo o recibo do servidor (o estorno lê dele o resultado). */
  async function executeReceipt(
    ref_: string,
    operation: string,
    action: Action | undefined,
    inputs: Record<string, unknown>,
    approval?: Record<string, string>,
  ) {
    return await executePath(
      `${ref_}:${operation}`,
      `/api/v1/backstage/orders/${encodeURIComponent(ref_)}/${encodeURIComponent(operation)}/`,
      action,
      inputs,
      approval,
      {
        subject: ORDER_OPERATION_SUBJECT[operation] ?? "a ação foi gravada",
        where: "o pedido",
      },
    );
  }
  async function execute(
    ref_: string,
    operation: string,
    action: Action | undefined,
    inputs: Record<string, unknown>,
    approval?: Record<string, string>,
  ) {
    await executeReceipt(ref_, operation, action, inputs, approval);
    return true;
  }
  /**
   * Uma corrida da TaOn para vários pedidos (`courier-ride`), pela mesma
   * intenção das outras ações: quem a tela leu, a revisão de CADA pedido e uma
   * chave por corrida, guardada até a resposta definitiva (o toque repetido
   * depois de rede caída reenvia a mesma chave e recebe a mesma corrida).
   * `action` é a ação `courier-ride` da projeção. Devolve o que o servidor
   * gravou: o número e a letra da corrida, ou `already_called` quando ela já
   * existia com estes mesmos pedidos.
   */
  async function executeRide(
    action: Parameters<typeof courierRideAction>[0],
    call: CourierRideCall,
  ): Promise<CourierRideResult> {
    return await executePath(
      courierRideResource(call.refs),
      COURIER_RIDE_PATH,
      courierRideAction(action, call.refs),
      courierRideInputs(call),
      undefined,
      { subject: "a corrida foi chamada", where: "os pedidos" },
    );
  }
  return {
    execute,
    executeReceipt,
    executePath,
    executeRide,
    checkPath,
    hasPending: computed(() => Object.keys(pending.value).length > 0),
  };
}
