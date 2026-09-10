import type { MarketingActionProjectionV2 } from "~/generated/marketingClient";
import type {
  Campaign,
  ChosenAudience,
  MarketingCommandResponse,
  MarketingConfirmationChallenge,
} from "~/types/campaign";

export type PendingCampaignFireCommand = {
  campaignId: number;
  action: "fire";
  href: string;
  body: Record<string, unknown>;
  idempotencyKey: string;
  fingerprint: string;
  challenge: MarketingConfirmationChallenge;
};

type CampaignFireIntent = Omit<PendingCampaignFireCommand, "challenge">;

function errorPayload(error: unknown): unknown {
  if (typeof error !== "object" || error === null || !("data" in error))
    return {};
  return (error as { data?: unknown }).data ?? {};
}

function errorCode(error: unknown): string {
  const payload = errorPayload(error) as { code?: unknown };
  return typeof payload.code === "string" ? payload.code : "";
}

function challengeFrom(error: unknown): MarketingConfirmationChallenge | null {
  const payload = errorPayload(error) as {
    code?: string;
    confirmation?: Partial<MarketingConfirmationChallenge>;
  };
  const challenge = payload.confirmation;
  if (
    payload.code !== "confirmation_required" ||
    !challenge?.token ||
    !challenge.ref ||
    !challenge.resource_ref
  ) {
    return null;
  }
  return challenge as MarketingConfirmationChallenge;
}

function exactFireHref(
  rule: Campaign,
  action: MarketingActionProjectionV2,
): string {
  const expectedResource = `campaign:${rule.pk}`;
  const expectedHref = `/api/v1/backstage/marketing/rules/${rule.pk}/fire/`;
  const expectedRef = `${expectedResource}:fire_campaign:v${rule.version}`;
  if (
    action.kind !== "fire_campaign" ||
    !action.enabled ||
    action.resource_ref !== expectedResource ||
    action.ref !== expectedRef ||
    action.href !== expectedHref ||
    action.method !== "POST" ||
    action.idempotency !== "required" ||
    !action.confirmation.token_required
  ) {
    throw new Error("marketing_fire_action_mismatch");
  }
  return expectedHref;
}

function intentFingerprint(rule: Campaign, audience: ChosenAudience): string {
  return JSON.stringify({
    audience: Object.fromEntries(
      Object.entries(audience).sort(([left], [right]) =>
        left.localeCompare(right),
      ),
    ),
    campaignId: rule.pk,
    version: rule.version,
  });
}

export function useCampaignFireCommand() {
  const pendingCommand = ref<PendingCampaignFireCommand | null>(null);
  const retryIntent = ref<CampaignFireIntent | null>(null);

  async function post(intent: CampaignFireIntent) {
    return await $fetch<MarketingCommandResponse>(intent.href, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Idempotency-Key": intent.idempotencyKey },
      body: intent.body,
    });
  }

  async function begin(options: {
    rule: Campaign;
    action: MarketingActionProjectionV2;
    audience: ChosenAudience;
  }): Promise<MarketingCommandResponse | null> {
    const href = exactFireHref(options.rule, options.action);
    const fingerprint = intentFingerprint(options.rule, options.audience);
    const previous = retryIntent.value;
    const body: Record<string, unknown> = {
      base_version: options.rule.version,
    };
    if (Object.keys(options.audience).length)
      body.audience_rules = options.audience;
    const intent: CampaignFireIntent = {
      campaignId: options.rule.pk,
      action: "fire",
      href,
      body,
      fingerprint,
      idempotencyKey:
        previous?.fingerprint === fingerprint
          ? previous.idempotencyKey
          : globalThis.crypto.randomUUID(),
    };
    retryIntent.value = intent;

    try {
      const response = await post(intent);
      pendingCommand.value = null;
      retryIntent.value = null;
      return response;
    } catch (error) {
      if (flagMarketingSessionError(error)) {
        pendingCommand.value = null;
        throw error;
      }
      const challenge = challengeFrom(error);
      if (!challenge) {
        if (
          ["version_conflict", "campaign_inactive", "campaign_not_found"].includes(
            errorCode(error),
          )
        ) {
          retryIntent.value = null;
        }
        throw error;
      }
      if (
        challenge.resource_ref !== `campaign:${options.rule.pk}` ||
        challenge.base_version !== options.rule.version
      ) {
        retryIntent.value = null;
        throw new Error("marketing_fire_confirmation_context_mismatch", {
          cause: error,
        });
      }
      pendingCommand.value = { ...intent, challenge };
      return null;
    }
  }

  async function confirm(options: {
    credential?: string;
    typedConfirmation?: string;
  }): Promise<MarketingCommandResponse> {
    const command = pendingCommand.value;
    if (!command) throw new Error("marketing_fire_confirmation_missing");
    if (command.challenge.dual_control)
      throw new Error("marketing_dual_control_required");
    try {
      if (command.challenge.step_up !== "none") {
        await $fetch("/api/v1/backstage/marketing/security/step-up/", {
          method: "POST",
          credentials: "same-origin",
          body: {
            method: command.challenge.step_up,
            credential: String(options.credential || "").trim(),
          },
        });
      }
      const response = await $fetch<MarketingCommandResponse>(command.href, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Idempotency-Key": command.idempotencyKey },
        body: {
          ...command.body,
          confirmation_token: command.challenge.token,
          typed_confirmation: String(options.typedConfirmation || "").trim(),
        },
      });
      pendingCommand.value = null;
      retryIntent.value = null;
      return response;
    } catch (error) {
      if (flagMarketingSessionError(error)) pendingCommand.value = null;
      if (
        [
          "version_conflict",
          "confirmation_context_changed",
          "confirmation_expired",
        ].includes(errorCode(error))
      ) {
        pendingCommand.value = null;
        retryIntent.value = null;
      }
      throw error;
    }
  }

  function cancel() {
    pendingCommand.value = null;
    retryIntent.value = null;
  }

  return { pendingCommand, begin, confirm, cancel };
}
