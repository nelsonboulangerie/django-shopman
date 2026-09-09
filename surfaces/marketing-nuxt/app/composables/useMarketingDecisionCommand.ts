import type {
  MarketingCommandResponse,
  MarketingConfirmationChallenge,
} from "~/types/campaign";
import {
  decisionResumeIntent,
  MARKETING_DECISION_REAUTH_STATE,
  PENDING_MARKETING_DECISION_STATE,
  type MarketingDecisionAction,
  type MarketingDecisionResumeIntent,
  type PendingMarketingDecision,
} from "~/presentation/marketingDecisionSession";

export type { PendingMarketingDecision };

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
  const { data: operatorSession } = useNuxtData<{
    operator: { id: number } | null;
  }>("operator-session");
  const currentOwnerRef = computed(() =>
    operatorSession.value?.operator?.id
      ? `operator:${operatorSession.value.operator.id}`
      : "",
  );
  const pendingDecision = useState<PendingMarketingDecision | null>(
    PENDING_MARKETING_DECISION_STATE,
    () => null,
  );
  const pendingReauthentication =
    useState<MarketingDecisionResumeIntent | null>(
      MARKETING_DECISION_REAUTH_STATE,
      () => null,
    );

  async function begin(options: {
    announcementId: number;
    action: MarketingDecisionAction;
    body: Record<string, unknown>;
    idempotencyKey: string;
  }): Promise<MarketingCommandResponse | null> {
    const href = `/api/v1/backstage/marketing/announcements/${options.announcementId}/${options.action}/`;
    const intent = { ...options, href, ownerRef: currentOwnerRef.value };
    try {
      const response = await $fetch<MarketingCommandResponse>(href, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Idempotency-Key": options.idempotencyKey },
        body: options.body,
      });
      pendingReauthentication.value = null;
      return response;
    } catch (error) {
      if (flagMarketingSessionError(error)) {
        pendingDecision.value = null;
        pendingReauthentication.value = intent;
        return null;
      }
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
      pendingReauthentication.value = null;
      pendingDecision.value = { ...intent, challenge };
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
      pendingDecision.value = null;
      return response;
    } catch (error) {
      if (flagMarketingSessionError(error)) {
        // O token pertence à sessão/contexto anterior. Preservamos somente a
        // intenção, para pedir um challenge novo após reautenticar.
        pendingDecision.value = null;
        pendingReauthentication.value = decisionResumeIntent(command);
      }
      throw error;
    }
  }

  async function resumeAfterReauthentication(): Promise<MarketingCommandResponse | null> {
    const intent = pendingReauthentication.value;
    if (!intent) throw new Error("marketing_reauthentication_intent_missing");
    if (!intent.ownerRef || intent.ownerRef !== currentOwnerRef.value) {
      pendingReauthentication.value = null;
      throw new Error("marketing_reauthentication_actor_changed");
    }
    return begin(intent);
  }

  function cancel() {
    pendingDecision.value = null;
    pendingReauthentication.value = null;
  }

  return {
    pendingDecision,
    pendingReauthentication,
    begin,
    confirm,
    resumeAfterReauthentication,
    cancel,
  };
}
