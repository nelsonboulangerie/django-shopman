import {
  decisionResumeIntent,
  MARKETING_DECISION_REAUTH_STATE,
  PENDING_MARKETING_DECISION_STATE,
  type MarketingDecisionResumeIntent,
  type PendingMarketingDecision,
} from "~/presentation/marketingDecisionSession";

// Política única do app: 401 significa sessão ausente/expirada e reabre o gate;
// 403 só reabre o cadeado quando o backend disser `station_locked`. Capability
// negada continua forbidden — entrar de novo não criaria autorização.
export function flagMarketingSessionError(error: unknown): boolean {
  if (useOperatorSession().flagIfUnauthenticated(error)) {
    const pending = useState<PendingMarketingDecision | null>(
      PENDING_MARKETING_DECISION_STATE,
      () => null,
    );
    if (pending.value) {
      const resumable = useState<MarketingDecisionResumeIntent | null>(
        MARKETING_DECISION_REAUTH_STATE,
        () => null,
      );
      resumable.value = decisionResumeIntent(pending.value);
      pending.value = null;
    }
    void refreshNuxtData("operator-session");
    return true;
  }
  if (useStationLock().flagIfStationLocked(error)) {
    void refreshNuxtData("operator-session");
    return true;
  }
  return false;
}

export function operatorSessionOnError(ctx: {
  response: { status: number; _data?: unknown };
}): void {
  flagMarketingSessionError({
    status: ctx.response.status,
    data: ctx.response._data,
  });
}
