// O "ao vivo" do cabeçalho de uma tela: a conexão da caixa pessoal (estado do
// `MarketingInboxLive`, no shell) + a hora da leitura desta tela.
import type { Ref } from "vue";

import { NOTIFICATION_REALTIME_STATE } from "~/composables/useMarketingNotificationInbox";
import { marketingLiveStatus, type MarketingRealtime } from "~/presentation/liveStatus";

export function useMarketingLiveStatus(input: {
  generatedAt: Ref<string | null | undefined>;
  failed: Ref<boolean>;
  timeZone: Ref<string>;
}) {
  const realtime = useState<MarketingRealtime>(NOTIFICATION_REALTIME_STATE, () => "connecting");
  return computed(() =>
    marketingLiveStatus({
      // "Conectando" é o instante entre a página abrir e o SSE responder: não vale o
      // alarde de um rótulo por extenso que some meio segundo depois.
      realtime: realtime.value === "connecting" ? "live" : realtime.value,
      failed: input.failed.value,
      generatedAt: input.generatedAt.value,
      timeZone: input.timeZone.value,
    }),
  );
}
