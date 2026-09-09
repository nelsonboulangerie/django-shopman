import type { MarketingConfirmationChallenge } from "~/types/campaign";

export type MarketingDecisionAction = "approve" | "reject";

export type PendingMarketingDecision = {
  announcementId: number;
  action: MarketingDecisionAction;
  href: string;
  body: Record<string, unknown>;
  idempotencyKey: string;
  ownerRef: string;
  challenge: MarketingConfirmationChallenge;
};

export type MarketingDecisionResumeIntent = Omit<
  PendingMarketingDecision,
  "challenge"
>;

export const PENDING_MARKETING_DECISION_STATE = "marketing-pending-decision";
export const MARKETING_DECISION_REAUTH_STATE =
  "marketing-decision-after-reauth";

export function decisionResumeIntent(
  command: PendingMarketingDecision,
): MarketingDecisionResumeIntent {
  const { challenge: _discarded, ...intent } = command;
  return intent;
}
