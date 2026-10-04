import { posLiveStatus, type PosRealtimeState } from "~/presentation/events";

/** Estado do tempo real do balcão, escrito pelo shell de operador. */
export function usePosLiveState() {
  return useState<{ realtime: PosRealtimeState; lastRead: string }>("pos-live", () => ({
    realtime: "polling",
    lastRead: "",
  }));
}

/** O que o `OperatorLiveStatus` dos cabeçalhos mostra: tom, rótulo e a hora da última leitura. */
export function usePosLiveStatus() {
  const live = usePosLiveState();
  const { isOnline } = useConnectivity();
  const view = computed(() => posLiveStatus({ online: isOnline.value, realtime: live.value.realtime }));
  const time = computed(() => {
    if (!live.value.lastRead) return "";
    const date = new Date(live.value.lastRead);
    return Number.isNaN(date.getTime())
      ? ""
      : date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  });
  return { view, time };
}
