import type { MaybeRefOrGetter } from "vue";
import { toValue } from "vue";
import type {
  ProductionConflictRecovery,
} from "~/generated/productionContract";

export type GuardedMutationAction = {
  ref: string;
  enabled: boolean;
  reason: string;
  proof: string;
  expected_rev: number | null;
};

type FreshProjection = {
  generated_at: string;
  source_revision: string;
  fresh_until: string;
  contract_version: number;
  actions: GuardedMutationAction[];
};

export interface ProductionMutationMetadata {
  projection_generated_at: string;
  source_revision: string;
  fresh_until: string;
  contract_version: number;
  action_ref: string;
  action_proof: string;
}

export type ProductionMutationAuthorization =
  | {
      ok: true;
      metadata: ProductionMutationMetadata;
      action: GuardedMutationAction;
    }
  | { ok: false; blocked: ProductionMutationBlock };

export interface ProductionMutationBlock {
  code:
    | "offline"
    | "stale_projection"
    | "action_not_projected"
    | "action_disabled";
  detail: string;
  recovery: ProductionConflictRecovery;
}

const ISO_INSTANT =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/;

/** Parseia somente o timestamp ISO emitido pelo contrato; valores ambíguos falham fechados. */
export function projectionFreshUntilMs(value: unknown): number | null {
  if (typeof value !== "string") return null;
  const match = ISO_INSTANT.exec(value);
  if (!match) return null;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  if (
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > new Date(Date.UTC(year, month, 0)).getUTCDate() ||
    hour > 23 ||
    minute > 59 ||
    second > 59
  ) {
    return null;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object"
    ? (value as Record<string, unknown>)
    : null;
}

function staleRecovery(error: unknown): ProductionMutationBlock | null {
  const envelope = asRecord(httpError(error).data);
  const body = asRecord(envelope?.error);
  if (body?.code !== "stale_projection") return null;

  const recovery = asRecord(body.recovery);
  return {
    code: "stale_projection",
    detail:
      typeof envelope?.detail === "string" && envelope.detail
        ? envelope.detail
        : "Os dados mudaram desde a última atualização.",
    recovery: {
      action: recovery?.action === "retry" ? "retry" : "refresh",
      label:
        typeof recovery?.label === "string" && recovery.label
          ? recovery.label
          : "Atualizar dados",
    },
  };
}

function forbiddenRecovery(error: unknown): { detail: string; label: string } | null {
  const envelope = asRecord(httpError(error).data);
  const body = asRecord(envelope?.error);
  if (body?.code !== "forbidden") return null;
  const recovery = asRecord(body.recovery);
  return {
    detail:
      typeof envelope?.detail === "string" && envelope.detail
        ? envelope.detail
        : "Seu acesso não permite esta ação.",
    label:
      typeof recovery?.label === "string" && recovery.label
        ? recovery.label
        : "Solicite acesso a um gestor.",
  };
}

/**
 * Pré-condição única para escritas da Produção.
 *
 * Toda mutation é negada antes de criar a tentativa/idempotency key quando a
 * estação está offline ou a projeção está ausente, inválida ou vencida. A
 * recuperação nunca repete uma escrita: ela apenas atualiza a projeção para o
 * operador revisar o formulário preservado e confirmar novamente.
 */
export function useProductionMutationGuard<T extends FreshProjection>(
  projection: MaybeRefOrGetter<T | null | undefined>,
  refreshProjection: () => unknown,
  now: () => number = Date.now,
) {
  const { isOnline } = useConnectivity();

  async function refreshSafely() {
    try {
      await refreshProjection();
    } catch (error) {
      useSonner.error(
        httpErrorMessage(error, "Não foi possível atualizar os dados. Tente novamente."),
      );
    }
  }

  function notify(block: ProductionMutationBlock) {
    const label =
      block.recovery.action === "refresh"
        ? block.recovery.label
        : "Atualizar dados";
    useSonner.error(block.detail, {
      action: {
        label,
        onClick: () => void refreshSafely(),
      },
    });
  }

  function currentBlock(): ProductionMutationBlock | null {
    if (!isOnline.value) {
      return {
        code: "offline",
        detail: "Sem conexão. A ação não foi enviada e seus dados foram preservados.",
        recovery: { action: "refresh", label: "Atualizar ao reconectar" },
      };
    }

    const current = toValue(projection);
    const generatedAt = projectionFreshUntilMs(current?.generated_at);
    const freshUntil = projectionFreshUntilMs(current?.fresh_until);
    if (
      generatedAt === null ||
      typeof current?.source_revision !== "string" ||
      !current.source_revision.trim() ||
      !Number.isInteger(current.contract_version) ||
      current.contract_version < 1 ||
      freshUntil === null ||
      freshUntil <= now()
    ) {
      return {
        code: "stale_projection",
        detail: "Estes dados estão desatualizados. Atualize antes de confirmar.",
        recovery: { action: "refresh", label: "Atualizar dados" },
      };
    }
    return null;
  }

  function authorizeMutation(actionRef: string): ProductionMutationAuthorization {
    const block = currentBlock();
    if (block) {
      notify(block);
      return { ok: false, blocked: block };
    }
    const current = toValue(projection)!;
    const action = current.actions.find((candidate) => candidate.ref === actionRef);
    if (!action) {
      const unavailable: ProductionMutationBlock = {
        code: "action_not_projected",
        detail: "Esta ação não faz parte do painel atual. Atualize os dados antes de agir.",
        recovery: { action: "refresh", label: "Atualizar dados" },
      };
      notify(unavailable);
      return { ok: false, blocked: unavailable };
    }
    if (!action.enabled) {
      const disabled: ProductionMutationBlock = {
        code: "action_disabled",
        detail: action.reason || "Esta ação está indisponível no contexto atual.",
        recovery: { action: "refresh", label: "Atualizar dados" },
      };
      notify(disabled);
      return { ok: false, blocked: disabled };
    }
    if (!action.proof.trim()) {
      const unavailable: ProductionMutationBlock = {
        code: "action_not_projected",
        detail: "A autorização desta ação não veio no painel atual. Atualize os dados antes de agir.",
        recovery: { action: "refresh", label: "Atualizar dados" },
      };
      notify(unavailable);
      return { ok: false, blocked: unavailable };
    }
    return {
      ok: true,
      action,
      metadata: {
        projection_generated_at: current.generated_at,
        source_revision: current.source_revision,
        fresh_until: current.fresh_until,
        contract_version: current.contract_version,
        action_ref: action.ref,
        action_proof: action.proof,
      },
    };
  }

  function handleMutationError(error: unknown): boolean {
    const block = staleRecovery(error);
    if (block) {
      notify(block);
      return true;
    }
    const forbidden = forbiddenRecovery(error);
    if (!forbidden) return false;
    useSonner.error(forbidden.detail, { description: forbidden.label });
    return true;
  }

  return { currentBlock, authorizeMutation, handleMutationError, refreshSafely };
}
