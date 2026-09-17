// Import explícito, e não o auto-import da layer: assim a política REAL roda no
// harness de unidade do Marketing, que monta o módulo sem o runtime Nuxt. O teste
// continua provando o comportamento inteiro, não só o pedaço de cá.
import { flagOperatorSessionRefusal } from "../../../operator-kit/app/utils/operatorSession";
import {
  decisionResumeIntent,
  MARKETING_DECISION_REAUTH_STATE,
  PENDING_MARKETING_DECISION_STATE,
  type MarketingDecisionResumeIntent,
  type PendingMarketingDecision,
} from "~/presentation/marketingDecisionSession";

// A POLÍTICA é a comum — `flagOperatorSessionRefusal`, do kit. O que é só do
// Marketing é o que ele faz na sessão expirada: aprovar ou rejeitar um anúncio é ato
// público e irreversível, com chave de idempotência e um desafio de confirmação. Se a
// sessão morre no meio, a intenção é guardada e o DESAFIO é descartado: confirmação
// respondida antes da sessão morrer não atravessa a reautenticação.
//
// Isso depende de `PendingMarketingDecision`, tipo do domínio dele, e não generaliza.
// Nome próprio para não sombrear o auto-import do kit.
export function flagMarketingSessionError(error: unknown): boolean {
  const refusal = flagOperatorSessionRefusal(error);
  if (refusal === "expired") parkPendingDecision();
  if (refusal) void refreshNuxtData("operator-session");
  return refusal !== null;
}

function parkPendingDecision(): void {
  const pending = useState<PendingMarketingDecision | null>(
    PENDING_MARKETING_DECISION_STATE,
    () => null,
  );
  if (!pending.value) return;
  const resumable = useState<MarketingDecisionResumeIntent | null>(
    MARKETING_DECISION_REAUTH_STATE,
    () => null,
  );
  resumable.value = decisionResumeIntent(pending.value);
  pending.value = null;
}

export function marketingSessionOnError(ctx: {
  response: { status: number; _data?: unknown };
}): void {
  flagMarketingSessionError({
    status: ctx.response.status,
    data: ctx.response._data,
  });
}
