import { useOrderIntention } from "./useOrderIntention";
import type { ChannelSwitchOutcome, ChannelSwitchRequest } from "./useFeedBoard";
import type { ChannelSwitchProjection } from "~/types/feeds";

const MANAGER_CODES = new Set(["manager_approval_required", "manager_approval_invalid"]);

/**
 * O interruptor de um canal FORA da aba Canais (G09: "iFood ligado · desligar pede
 * gerente" na coluna da Fila). O mesmo endpoint, a mesma intenção por canal e o mesmo
 * desfecho do toggle de Canais (`useFeedBoard.switchChannel`): falta de gerente é o
 * próximo passo do `ChannelSwitchDialog`, não erro para o toast.
 */
export function useChannelSwitch(
  switchFor: (ref: string) => ChannelSwitchProjection | null | undefined,
  refresh: () => Promise<unknown> | unknown,
) {
  const intentions = useOrderIntention();
  const busy = ref<Set<string>>(new Set());
  const isSwitching = (ref_: string) => busy.value.has(ref_);

  async function switchChannel(
    ref_: string,
    request: ChannelSwitchRequest,
    approval?: Record<string, string>,
  ): Promise<ChannelSwitchOutcome> {
    if (busy.value.has(ref_)) return { ok: false, code: "busy", message: "" };
    const current = switchFor(ref_);
    const action = current
      ? { enabled: current.enabled, reason: current.disabled_reason,
          payload_schema: { base_revision: current.base_revision, expected_actor_id: current.expected_actor_id } }
      : undefined;
    busy.value = new Set(busy.value).add(ref_);
    try {
      await intentions.executePath(`feed:${ref_}:switch`, "/api/v1/backstage/feeds/switch/", action, { ref: ref_, ...request }, approval);
      try { await refresh(); } catch { /* a leitura seguinte acerta; o gesto já foi confirmado */ }
      return { ok: true, code: "", message: "" };
    } catch (error) {
      const code = httpErrorCode(error);
      const message = httpErrorMessage(error, error instanceof Error ? error.message : "Não foi possível mudar o canal.");
      if (!MANAGER_CODES.has(code)) useSonner.error(message);
      if (httpError(error).status === 409) {
        try { await refresh(); } catch { /* o conflito já foi dito */ }
      }
      return { ok: false, code, message };
    } finally {
      const next = new Set(busy.value);
      next.delete(ref_);
      busy.value = next;
    }
  }

  return { switchChannel, isSwitching };
}
