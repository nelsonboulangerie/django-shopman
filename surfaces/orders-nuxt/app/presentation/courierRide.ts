// Presentation — a intenção de chamar UMA corrida para vários pedidos (`courier-ride`).
//
// As três telas que juntam entregas (as Entregas, o Painel e o detalhe do pedido)
// chamam pela mesma porta, no protocolo de intenção: quem a tela leu
// (`expected_actor_id`), o que ela leu de CADA pedido (`base_revisions`) e uma chave
// por corrida, guardada até a resposta definitiva. O servidor entrega isso pronto na
// ação `courier-ride` da projeção (`group_action` das Entregas, `ride_action` do
// Painel, a ação do pedido no detalhe); aqui só se recorta para a corrida escolhida.
import type { Action } from "~/generated/ordersContract";

export const COURIER_RIDE_PATH = "/api/v1/backstage/orders/courier-ride/";

/** O que a tela escolheu para a corrida: os pedidos e a custódia que sai com ela. */
export interface CourierRideCall {
  refs: string[];
  change_out: Record<string, string>;
  machine: string;
  /** O número (letra e cor) que a tela mostrava; o servidor mantém se continuar livre. */
  ride_number?: number;
}

/** O que o servidor responde quando a corrida foi pedida (ou já existia). */
export interface CourierRideResult {
  outcome?: string;
  detail?: string;
  ride_number?: number | null;
  ride_letter?: string;
  /** A corrida com estes mesmos pedidos já existia: nada foi gravado de novo. */
  already_called?: boolean;
}

type RideAction = Pick<Action, "enabled" | "reason" | "payload_schema"> &
  Partial<Pick<Action, "method">>;

/**
 * A chave de onde mora a intenção desta corrida enquanto a resposta não é
 * definitiva: os mesmos pedidos, em qualquer ordem, são a mesma corrida. É o que
 * faz o toque repetido depois de rede caída reenviar a MESMA chave.
 */
export function courierRideResource(refs: readonly string[]): string {
  return `courier-ride:${[...refs].sort().join("+")}`;
}

/**
 * A ação da projeção, recortada para os pedidos desta corrida: só as revisões
 * deles. Faltou a de algum (a tela é mais velha que a lista), a ação sai
 * desabilitada com o motivo, e nada é enviado.
 */
export function courierRideAction(
  action: RideAction | null | undefined,
  refs: readonly string[],
): RideAction | undefined {
  if (!action) return undefined;
  const all = (action.payload_schema.base_revisions ?? {}) as Record<string, unknown>;
  const revisions = Object.fromEntries(
    refs
      .filter((ref) => typeof all[ref] === "string" && all[ref])
      .map((ref) => [ref, all[ref] as string]),
  );
  const complete = Object.keys(revisions).length === refs.length;
  return {
    enabled: action.enabled && complete,
    reason: action.reason || (complete ? "" : "Os pedidos mudaram. Atualize antes de chamar a corrida."),
    method: action.method,
    payload_schema: {
      expected_actor_id: action.payload_schema.expected_actor_id,
      base_revisions: revisions,
    },
  };
}

/** O que vai no corpo além do que a ação traz: os pedidos e a custódia. */
export function courierRideInputs(call: CourierRideCall): Record<string, unknown> {
  return {
    refs: [...call.refs],
    change_out: { ...call.change_out },
    machine: call.machine,
    ...(call.ride_number ? { ride_number: call.ride_number } : {}),
  };
}
