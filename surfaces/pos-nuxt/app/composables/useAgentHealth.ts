import type { ComputedRef } from "vue";

import type { AgentProbe } from "~/presentation/terminalHealth";
import type { POSProjection } from "~/types/pos";

/**
 * A sonda que a docstring do servidor prometia: quem alcança o agente do balcão
 * é ESTA página, então é ela que pergunta `/health` — ao montar a tela de venda
 * e depois numa cadência calma. O resultado alimenta o card de saúde do
 * terminal via `presentation/terminalHealth`; antes disto, a impressora era
 * "OK" por metadata e a gaveta ficava "verificado na estação" para sempre.
 *
 * 60s porque o alvo é pegar "o agente caiu" antes de a fila do balcão pegar,
 * sem transformar a sonda em ruído: loopback responde em microssegundos, mas o
 * timeout de agente pendurado é 3s, e 3s a cada poucos segundos vira spam.
 */
const PROBE_INTERVAL_MS = 60_000;

export function useAgentHealth(pos: ComputedRef<POSProjection | null>) {
  const agent = useCounterAgent(pos);

  /** `null` = terminal sem agente (nada a sondar); `ok: null` = sonda no ar. */
  const probe = ref<AgentProbe | null>(null);
  const checking = ref(false);

  async function check(): Promise<void> {
    if (!import.meta.client) return;
    if (!agent.canKick.value) {
      probe.value = null;
      return;
    }
    if (checking.value) return;
    checking.value = true;
    if (probe.value === null) probe.value = { ok: null, message: "" };
    try {
      const result = await agent.probe();
      probe.value = { ok: result.ok, message: result.message };
    } finally {
      checking.value = false;
    }
  }

  let timer: ReturnType<typeof setInterval> | null = null;
  onMounted(() => {
    void check();
    timer = setInterval(() => void check(), PROBE_INTERVAL_MS);
  });
  onBeforeUnmount(() => {
    if (timer) clearInterval(timer);
  });
  // A Projection pode chegar depois do mount (fetch em voo): quando o terminal
  // ganhar agente, a primeira sonda sai na hora em vez de esperar o intervalo.
  watch(agent.canKick, (can) => {
    if (can && probe.value === null) void check();
  });

  return { probe, checking, check, agentConfigured: agent.canKick };
}
