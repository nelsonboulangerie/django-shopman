import type { MaybeRefOrGetter } from "vue";
import { toValue, watch } from "vue";
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
    | "action_disabled"
    | "changed_elsewhere";
  detail: string;
  recovery: ProductionConflictRecovery;
}

/**
 * Quanto antes do vencimento a própria tela busca números novos. O poll do
 * Planejamento roda a cada 60–72 s e a projeção vale 90 s: com o poll em dia,
 * esta renovação nunca dispara. Ela existe para o poll que falhou (rede,
 * deploy reiniciando o servidor) — antes dela, UMA falha deixava a tela
 * vencida até o poll seguinte, e o toque do operador era recusado.
 */
export const PROJECTION_RENEW_LEAD_MS = 20_000;
/** Intervalo entre tentativas quando a renovação não trouxe números novos. */
export const PROJECTION_RENEW_RETRY_MS = 10_000;

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

const REFRESH_LABEL = "Atualizar os números";
const STALE_ON_SERVER_DETAIL =
  "Nada foi salvo: os números desta tela passaram do prazo antes de o pedido chegar.";
const REFRESHED_CONFIRM_AGAIN = "Os números já foram atualizados — confira e confirme de novo.";
const UNREACHABLE_DETAIL =
  "Nada foi salvo: não foi possível buscar os números atuais desta tela. O que você digitou continua aqui.";
const CHANGED_ELSEWHERE_DETAIL =
  "Nada foi salvo: outra tela alterou esta fornada enquanto você decidia. Os números já foram atualizados — confira e confirme de novo.";
const NOT_PROJECTED_AFTER_REFRESH_DETAIL =
  "Nada foi salvo: esta linha mudou em outra tela enquanto você decidia. Os números já foram atualizados — confira e confirme de novo.";

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
        : STALE_ON_SERVER_DETAIL,
    recovery: {
      action: recovery?.action === "retry" ? "retry" : "refresh",
      label:
        typeof recovery?.label === "string" && recovery.label
          ? recovery.label
          : REFRESH_LABEL,
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
 *
 * O vencimento é medido no relógio DESTE dispositivo a partir de quando a
 * projeção chegou (chegada + validade que o servidor deu), e não comparando o
 * `fresh_until` do servidor com o relógio local: um tablet com o relógio 40 s
 * adiantado recusava quase metade das ações com a tela recém-atualizada. O
 * servidor continua sendo a autoridade (409 `stale_projection`).
 */
export function useProductionMutationGuard<T extends FreshProjection>(
  projection: MaybeRefOrGetter<T | null | undefined>,
  refreshProjection: () => unknown,
  now: () => number = Date.now,
) {
  const { isOnline } = useConnectivity();

  // Chegada de cada projeção, pela identidade que o servidor assinou.
  let receivedKey = "";
  let receivedAt = 0;
  const identity = (current: T | null | undefined) =>
    current ? `${current.generated_at}|${current.source_revision}` : "";
  function markReceived(current: T | null | undefined) {
    const key = identity(current);
    if (key && key !== receivedKey) {
      receivedKey = key;
      receivedAt = now();
    }
  }
  let mounted = false;
  let disposed = false;
  let renewTimer: ReturnType<typeof setTimeout> | null = null;
  watch(
    () => identity(toValue(projection)),
    () => {
      markReceived(toValue(projection));
      if (mounted) scheduleRenewal();
    },
    { immediate: true },
  );

  /** Instante local (ms) em que a projeção vence, ou null se ela é inválida. */
  function localDeadline(current: T | null | undefined): number | null {
    const generatedAt = projectionFreshUntilMs(current?.generated_at);
    const freshUntil = projectionFreshUntilMs(current?.fresh_until);
    if (generatedAt === null || freshUntil === null) return null;
    const lifetime = freshUntil - generatedAt;
    if (lifetime <= 0) return null;
    markReceived(current);
    return receivedAt + lifetime;
  }

  async function refreshSafely() {
    try {
      await refreshProjection();
    } catch (error) {
      useSonner.error(
        httpErrorMessage(error, "Não foi possível buscar os números atuais. Tente de novo."),
      );
    }
  }

  function notify(block: ProductionMutationBlock) {
    const label =
      block.recovery.action === "refresh"
        ? block.recovery.label
        : REFRESH_LABEL;
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
        detail: "Sem conexão. Nada foi enviado, e o que você digitou continua aqui.",
        recovery: { action: "refresh", label: "Atualizar ao reconectar" },
      };
    }

    const current = toValue(projection);
    const deadline = localDeadline(current);
    if (
      deadline === null ||
      typeof current?.source_revision !== "string" ||
      !current.source_revision.trim() ||
      !Number.isInteger(current.contract_version) ||
      current.contract_version < 1 ||
      deadline <= now()
    ) {
      return {
        code: "stale_projection",
        detail: UNREACHABLE_DETAIL,
        recovery: { action: "refresh", label: "Tentar de novo" },
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
    return authorizeProjectedAction(actionRef, false);
  }

  function authorizeProjectedAction(
    actionRef: string,
    refreshed: boolean,
  ): ProductionMutationAuthorization {
    const current = toValue(projection)!;
    const action = current.actions.find((candidate) => candidate.ref === actionRef);
    if (!action) {
      const unavailable: ProductionMutationBlock = {
        code: "action_not_projected",
        detail: refreshed
          ? NOT_PROJECTED_AFTER_REFRESH_DETAIL
          : "Nada foi salvo: esta ação não está disponível nos números desta tela. Atualize e confira.",
        recovery: { action: "refresh", label: REFRESH_LABEL },
      };
      notify(unavailable);
      return { ok: false, blocked: unavailable };
    }
    if (!action.enabled) {
      const disabled: ProductionMutationBlock = {
        code: "action_disabled",
        detail: action.reason || "Esta ação está indisponível no contexto atual.",
        recovery: { action: "refresh", label: REFRESH_LABEL },
      };
      notify(disabled);
      return { ok: false, blocked: disabled };
    }
    if (!action.proof.trim()) {
      const unavailable: ProductionMutationBlock = {
        code: "action_not_projected",
        detail: "Nada foi salvo: a autorização desta ação não veio nos números desta tela. Atualize e confira.",
        recovery: { action: "refresh", label: REFRESH_LABEL },
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

  /**
   * Autoriza a ação do toque, buscando números novos primeiro quando os da
   * tela venceram — o operador não deve ser mandado "atualizar" por uma coisa
   * que a própria tela resolve sozinha.
   *
   * `seenRev` é a revisão da fornada que o operador tinha diante dos olhos ao
   * decidir (a do diálogo aberto). Se a projeção atual traz outra revisão,
   * outra tela mexeu na fornada: a ação é recusada com esse motivo, em vez de
   * mandar a revisão nova e sobrescrever em silêncio o que a outra tela fez.
   */
  async function authorizeFreshMutation(
    actionRef: string,
    seenRev: number | null = null,
  ): Promise<ProductionMutationAuthorization> {
    let refreshed = false;
    const block = currentBlock();
    if (block?.code === "stale_projection") {
      try {
        await refreshProjection();
        refreshed = true;
      } catch {
        // A recusa abaixo diz o que houve; o poll continua tentando.
      }
    }
    const remaining = currentBlock();
    if (remaining) {
      notify(remaining);
      return { ok: false, blocked: remaining };
    }
    const authorization = authorizeProjectedAction(actionRef, refreshed);
    if (!authorization.ok) return authorization;
    if (seenRev !== null && authorization.action.expected_rev !== null
      && authorization.action.expected_rev !== seenRev) {
      const changed: ProductionMutationBlock = {
        code: "changed_elsewhere",
        detail: CHANGED_ELSEWHERE_DETAIL,
        recovery: { action: "refresh", label: REFRESH_LABEL },
      };
      useSonner.error(changed.detail);
      return { ok: false, blocked: changed };
    }
    return authorization;
  }

  // ── Renovação: a tela visível nunca deveria chegar vencida ao toque ───────
  function scheduleRenewal(delay?: number) {
    if (renewTimer) clearTimeout(renewTimer);
    renewTimer = null;
    if (disposed) return;
    const deadline = localDeadline(toValue(projection));
    if (deadline === null) return;
    const wait =
      delay ?? Math.max(deadline - PROJECTION_RENEW_LEAD_MS - now(), 0);
    renewTimer = setTimeout(() => void renew(), wait);
  }

  async function renew() {
    renewTimer = null;
    if (disposed) return;
    const before = identity(toValue(projection));
    if (!document.hidden && isOnline.value) {
      try {
        await refreshProjection();
      } catch {
        // Silencioso: quem avisa é o toque do operador, se ainda vencida.
      }
    }
    // Números novos chegaram → o watch já reagendou pela nova validade.
    if (!disposed && identity(toValue(projection)) === before) {
      scheduleRenewal(PROJECTION_RENEW_RETRY_MS);
    }
  }

  onMounted(() => {
    mounted = true;
    scheduleRenewal();
  });
  onBeforeUnmount(() => {
    disposed = true;
    if (renewTimer) clearTimeout(renewTimer);
    renewTimer = null;
  });

  function handleMutationError(error: unknown): boolean {
    const block = staleRecovery(error);
    if (block) {
      // O servidor recusou por prazo: busca os números já, sem esperar o
      // toque — o operador só precisa conferir e confirmar de novo.
      useSonner.error(block.detail, { description: REFRESHED_CONFIRM_AGAIN });
      void refreshSafely();
      return true;
    }
    const forbidden = forbiddenRecovery(error);
    if (!forbidden) return false;
    useSonner.error(forbidden.detail, { description: forbidden.label });
    return true;
  }

  return {
    currentBlock,
    authorizeMutation,
    authorizeFreshMutation,
    handleMutationError,
    refreshSafely,
  };
}
