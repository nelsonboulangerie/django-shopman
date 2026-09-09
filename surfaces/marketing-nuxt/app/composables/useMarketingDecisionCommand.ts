import type {
  MarketingCommandResponse,
  MarketingConfirmationChallenge,
} from "~/types/campaign";

type DecisionAction = "approve" | "reject";

export type PendingMarketingDecision = {
  announcementId: number;
  action: DecisionAction;
  href: string;
  body: Record<string, unknown>;
  idempotencyKey: string;
  challenge: MarketingConfirmationChallenge;
};

function errorPayload(error: unknown): unknown {
  if (typeof error !== "object" || error === null || !("data" in error))
    return {};
  return (error as { data?: unknown }).data ?? {};
}

function confirmationChallenge(
  error: unknown,
): MarketingConfirmationChallenge | null {
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

export function useMarketingDecisionCommand() {
  const pendingDecision = ref<PendingMarketingDecision | null>(null);

  async function begin(options: {
    announcementId: number;
    action: DecisionAction;
    body: Record<string, unknown>;
    idempotencyKey: string;
  }): Promise<MarketingCommandResponse | null> {
    const href = `/api/v1/backstage/marketing/announcements/${options.announcementId}/${options.action}/`;
    try {
      return await $fetch<MarketingCommandResponse>(href, {
        method: "POST",
        headers: { "Idempotency-Key": options.idempotencyKey },
        body: options.body,
      });
    } catch (error) {
      const challenge = confirmationChallenge(error);
      if (!challenge) throw error;
      if (
        challenge.resource_ref !== `announcement:${options.announcementId}` ||
        challenge.base_version !== Number(options.body.base_version)
      ) {
        throw new Error("marketing_confirmation_context_mismatch", {
          cause: error,
        });
      }
      pendingDecision.value = { ...options, href, challenge };
      return null;
    }
  }

  async function confirm(options: {
    credential?: string;
    typedConfirmation?: string;
  }): Promise<MarketingCommandResponse> {
    const command = pendingDecision.value;
    if (!command) throw new Error("marketing_confirmation_missing");
    if (command.challenge.dual_control) {
      throw new Error("marketing_dual_control_required");
    }
    if (command.challenge.step_up !== "none") {
      await $fetch("/api/v1/backstage/marketing/security/step-up/", {
        method: "POST",
        body: {
          method: command.challenge.step_up,
          credential: String(options.credential || "").trim(),
        },
      });
    }
    const response = await $fetch<MarketingCommandResponse>(command.href, {
      method: "POST",
      headers: { "Idempotency-Key": command.idempotencyKey },
      body: {
        ...command.body,
        confirmation_token: command.challenge.token,
        typed_confirmation: String(options.typedConfirmation || "").trim(),
      },
    });
    pendingDecision.value = null;
    return response;
  }

  function cancel() {
    pendingDecision.value = null;
  }

  return { pendingDecision, begin, confirm, cancel };
}
