import type {
  MarketingActionProjectionV2,
  MarketingCommandResponse,
  MarketingConfirmationChallenge,
} from "~/types/campaign";

type Fetcher = typeof $fetch;

export type RecoveryChallengeResult =
  | { kind: "challenge"; challenge: MarketingConfirmationChallenge }
  | { kind: "receipt"; response: MarketingCommandResponse };

export type RecoveryConfirmation = {
  credential?: string;
  typedConfirmation?: string;
};

const RECOVERY_PATHS = {
  cancel_announcement: "cancel",
  retry_failed_delivery: "retry-deliveries",
  reconcile_unknown_delivery: "reconcile-deliveries",
} as const;

export type RecoveryAction = MarketingActionProjectionV2 & {
  kind: keyof typeof RECOVERY_PATHS;
};

function errorPayload(error: unknown): unknown {
  if (typeof error !== "object" || error === null || !("data" in error))
    return {};
  return (error as { data?: unknown }).data ?? {};
}

function challengeFrom(error: unknown): MarketingConfirmationChallenge | null {
  const payload = errorPayload(error) as {
    code?: string;
    confirmation?: Partial<MarketingConfirmationChallenge>;
  };
  const confirmation = payload.confirmation;
  if (
    payload.code !== "confirmation_required" ||
    !confirmation?.token ||
    !confirmation.ref ||
    !confirmation.resource_ref
  ) {
    return null;
  }
  return confirmation as MarketingConfirmationChallenge;
}

export function isRecoveryAction(
  action: MarketingActionProjectionV2,
): action is RecoveryAction {
  return action.kind in RECOVERY_PATHS;
}

/** Never execute an arbitrary Action href even if a compromised payload supplies it. */
export function assertRecoveryAction(
  action: MarketingActionProjectionV2,
  announcementId: number,
): asserts action is RecoveryAction {
  if (!isRecoveryAction(action) || action.method !== "POST") {
    throw new Error("unsupported_marketing_recovery_action");
  }
  const expected = `/api/v1/backstage/marketing/announcements/${announcementId}/${RECOVERY_PATHS[action.kind]}/`;
  if (
    action.href !== expected ||
    action.resource_ref !== `announcement:${announcementId}`
  ) {
    throw new Error("unsafe_marketing_recovery_action");
  }
}

function commandOptions(
  action: RecoveryAction,
  baseVersion: number,
  idempotencyKey: string,
  body: Record<string, unknown> = {},
) {
  return {
    method: "POST" as const,
    headers: { "Idempotency-Key": idempotencyKey },
    body: { base_version: baseVersion, ...body },
  };
}

/** Ask the backend for the exact immutable consequence; no effect happens on 428. */
export async function beginMarketingRecovery(
  fetcher: Fetcher,
  action: MarketingActionProjectionV2,
  options: {
    announcementId: number;
    baseVersion: number;
    idempotencyKey: string;
    body?: Record<string, unknown>;
  },
): Promise<RecoveryChallengeResult> {
  assertRecoveryAction(action, options.announcementId);
  if (!action.enabled) throw new Error("disabled_marketing_recovery_action");
  try {
    const response = await fetcher<MarketingCommandResponse>(
      action.href,
      commandOptions(
        action,
        options.baseVersion,
        options.idempotencyKey,
        options.body,
      ),
    );
    return { kind: "receipt", response };
  } catch (error) {
    const challenge = challengeFrom(error);
    if (!challenge) throw error;
    if (
      challenge.resource_ref !== action.resource_ref ||
      challenge.base_version !== options.baseVersion
    ) {
      throw new Error("marketing_confirmation_context_mismatch", {
        cause: error,
      });
    }
    return { kind: "challenge", challenge };
  }
}

/** Consume the same token/key/version only after the operator completed every gate. */
export async function confirmMarketingRecovery(
  fetcher: Fetcher,
  action: MarketingActionProjectionV2,
  challenge: MarketingConfirmationChallenge,
  confirmation: RecoveryConfirmation,
  options: {
    announcementId: number;
    baseVersion: number;
    idempotencyKey: string;
    body?: Record<string, unknown>;
  },
): Promise<MarketingCommandResponse> {
  assertRecoveryAction(action, options.announcementId);
  if (
    challenge.resource_ref !== action.resource_ref ||
    challenge.base_version !== options.baseVersion
  ) {
    throw new Error("marketing_confirmation_context_mismatch");
  }
  if (challenge.dual_control) {
    throw new Error("marketing_dual_control_required");
  }
  if (challenge.step_up !== "none") {
    await fetcher("/api/v1/backstage/marketing/security/step-up/", {
      method: "POST",
      body: {
        method: challenge.step_up,
        credential: String(confirmation.credential || "").trim(),
      },
    });
  }
  return await fetcher<MarketingCommandResponse>(
    action.href,
    commandOptions(action, options.baseVersion, options.idempotencyKey, {
      ...options.body,
      confirmation_token: challenge.token,
      typed_confirmation: String(confirmation.typedConfirmation || "").trim(),
    }),
  );
}
