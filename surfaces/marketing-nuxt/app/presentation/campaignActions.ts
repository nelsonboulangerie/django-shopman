import type { Campaign, MarketingActionProjectionV2 } from "~/types/campaign";

export interface CampaignEditAvailability {
  enabled: boolean;
  reason: string;
}

/** A Action de edição pertence à campanha e à versão que está na tela. */
export function campaignEditActionFor(
  rule: Pick<Campaign, "pk">,
  actions: MarketingActionProjectionV2[],
): MarketingActionProjectionV2 | undefined {
  return actions.find(
    (action) =>
      action.resource_ref === `campaign:${rule.pk}` &&
      action.kind === "edit_campaign",
  );
}

/**
 * Não basta achar uma Action com o mesmo nome: uma projeção velha, de outro recurso
 * ou com transporte inesperado não autoriza uma mutação nova no navegador.
 */
export function isExactCampaignEditAction(
  rule: Pick<Campaign, "pk" | "version">,
  action: MarketingActionProjectionV2 | undefined,
): boolean {
  const resource = `campaign:${rule.pk}`;
  return Boolean(
    action &&
    action.enabled &&
    action.resource_ref === resource &&
    action.ref === `${resource}:edit_campaign:v${rule.version}` &&
    action.kind === "edit_campaign" &&
    action.href === `/settings/campaigns#campaign-${rule.pk}` &&
    action.method === "GET" &&
    action.idempotency === "none" &&
    !action.confirmation.token_required,
  );
}

export function campaignEditAvailability(
  rule: Pick<Campaign, "pk" | "version">,
  actions: MarketingActionProjectionV2[],
): CampaignEditAvailability {
  const action = campaignEditActionFor(rule, actions);
  if (isExactCampaignEditAction(rule, action))
    return { enabled: true, reason: "" };
  if (action?.reason === "missing_capability") {
    return {
      enabled: false,
      reason: "Seu perfil não autoriza alterações nesta campanha.",
    };
  }
  if (action && !action.enabled) {
    return {
      enabled: false,
      reason: "Esta campanha não pode ser alterada no estado atual.",
    };
  }
  return {
    enabled: false,
    reason:
      "A edição está indisponível até atualizar a autorização segura da campanha.",
  };
}

/** O relógio de leitura é obrigatório: omiti-lo faria o PATCH contornar o CAS. */
export function campaignPatchPayload(
  rule: Pick<Campaign, "updated_at">,
  body: Partial<Campaign> & Record<string, unknown>,
): Record<string, unknown> {
  const baseUpdatedAt = String(rule.updated_at || "").trim();
  if (!baseUpdatedAt)
    throw new Error("marketing_campaign_base_version_missing");
  return { ...body, base_updated_at: baseUpdatedAt };
}
