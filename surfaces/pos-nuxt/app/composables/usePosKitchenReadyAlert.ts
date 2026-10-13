// "Comanda pronta" no balcão: quando a cozinha termina tudo o que foi disparado de
// uma comanda, o PDV toca (decisão do dono, 13/10/2026: selo, topo da lista e som).
//
// O sinal chega pelo aviso de comanda (SSE `/sse/tabs`, que a cozinha emite a cada
// ticket que muda) e o fetch canônico relê as comandas; aqui só se compara a leitura
// nova com a anterior. O que já estava pronto quando a tela abriu não toca.
import { newlyReadyTabs } from "~/presentation/tabBoard";
import { POS_READY_NOTES } from "~/presentation/readySound";
import type { POSTabProjection } from "~/types/pos";

export function usePosKitchenReadyAlert(tabs: Ref<POSTabProjection[]>) {
  const { beep } = useAlertSound("pos_kitchen_ready_sound", { notes: POS_READY_NOTES });
  let known: Set<string> | null = null;

  watch(
    tabs,
    (value) => {
      if (import.meta.server) return;
      const { ready, fresh } = newlyReadyTabs(known, value ?? []);
      known = ready;
      if (fresh.length) beep();
    },
    { immediate: true },
  );
}
