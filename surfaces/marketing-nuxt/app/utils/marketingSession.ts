import {
  decisionResumeIntent,
  MARKETING_DECISION_REAUTH_STATE,
  PENDING_MARKETING_DECISION_STATE,
  type MarketingDecisionResumeIntent,
  type PendingMarketingDecision,
} from "~/presentation/marketingDecisionSession";

// Política do Marketing, deliberadamente FORA do kit. O `operatorSessionOnError`
// comum (operator-kit/app/utils/operatorSession.ts) reabre o gate em qualquer
// 401/403; aqui 401 significa sessão ausente/expirada e reabre o gate, e 403 só
// reabre o cadeado quando o backend disser `station_locked` — capability negada
// continua forbidden, porque entrar de novo não criaria autorização. Além disso
// guarda o intent da decisão pendente antes da reautenticação, o que depende de
// `~/presentation/marketingDecisionSession` e não generaliza para as outras
// superfícies. Nome próprio para não sombrear o auto-import do kit.
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

export function marketingSessionOnError(ctx: {
  response: { status: number; _data?: unknown };
}): void {
  flagMarketingSessionError({
    status: ctx.response.status,
    data: ctx.response._data,
  });
}
