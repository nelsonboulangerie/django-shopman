// Disparar ou não disparar — e o PORQUÊ, em frase que o gestor lê.
//
// A lista de campanhas escondia a razão num `title` de botão desabilitado, e o
// Firefox não mostra tooltip em botão desabilitado: a tela dizia "Indisponível"
// e calava. A frase agora nasce aqui, para a linha poder mostrá-la por extenso.
import type {
  Campaign,
  MarketingActionProjectionV2,
  MarketingCommandResponse,
} from "~/types/campaign";

export interface FireAvailability {
  enabled: boolean;
  /** Vazio quando o disparo está liberado. */
  reason: string;
}

export function fireActionFor(
  rule: Pick<Campaign, "pk">,
  actions: MarketingActionProjectionV2[],
): MarketingActionProjectionV2 | undefined {
  return actions.find(
    (action) =>
      action.resource_ref === `campaign:${rule.pk}` &&
      action.kind === "fire_campaign",
  );
}

export function fireAvailability(
  rule: Pick<Campaign, "pk" | "is_active">,
  actions: MarketingActionProjectionV2[],
): FireAvailability {
  const action = fireActionFor(rule, actions);
  if (action?.enabled) return { enabled: true, reason: "" };
  if (!rule.is_active || action?.reason === "campaign_inactive") {
    return {
      enabled: false,
      reason: "Ligue a campanha antes de preparar um disparo.",
    };
  }
  if (!action || action.reason === "command_not_available") {
    return {
      enabled: false,
      reason:
        "O disparo direto está indisponível até concluir a atualização de segurança.",
    };
  }
  if (action.reason === "missing_capability") {
    return {
      enabled: false,
      reason: "Seu perfil não autoriza disparos manuais.",
    };
  }
  return {
    enabled: false,
    reason: "O disparo manual não está disponível agora.",
  };
}

/**
 * Para onde o disparo bem-sucedido leva a tela.
 *
 * O painel de sucesso não decidia nada: o único caminho adiante era tocar "Revisar
 * anúncio agora". Quem disparou já queria a revisão, então a navegação É a resposta.
 * O `dispatch` na query não carrega número nenhum — só diz de onde a tela veio, para a
 * revisão poder explicar por que o gestor está ali e se foi o mesmo toque de antes.
 */
export function fireDispatchRoute(
  response: Pick<MarketingCommandResponse, "replayed" | "announcement">,
): { path: string; query: { dispatch: "new" | "replayed" }; hash: string } {
  return {
    path: `/announcements/${response.announcement.pk}`,
    query: { dispatch: response.replayed ? "replayed" : "new" },
    hash: "#review",
  };
}
