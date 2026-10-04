// O que o shell da Cozinha (rail, barra do polegar, Ajustes) sabe das telas.
//
// - A estação deste dispositivo: a aberta agora, ou a última aberta (lembrada por
//   dispositivo). É ela que o item "Preparo" do rail abre.
// - O quadro conta ao rail quantos pedidos tem (selo do Preparo) e quais datas de
//   consulta existem (Ajustes). Fora do quadro os números vêm do índice das estações.
// - A Saída é a coluna do Gestor (SUITE-UX §15): o item do rail é um atalho para lá,
//   com o selo dos pedidos prontos para sair que o índice já conta.
import type { KDSIndexResponse } from "~/types/kds";
import { EXIT_STATION_TYPE, gestorExitUrl } from "~/presentation/exitStation";
import { kdsSections } from "~/presentation/sections";

export interface KdsStationMemory {
  ref: string;
  name: string;
}

export interface KdsBoardState {
  onBoard: boolean;
  total: number;
  serviceDate: string;
  today: string;
  availableDates: string[];
}

const STATION_KEY = "kds.station";

export function useKdsStation() {
  const station = useState<KdsStationMemory>("kds-station", () => ({ ref: "", name: "" }));
  function remember(ref: string, name: string) {
    if (!ref) return;
    station.value = { ref, name: name || ref };
    if (!import.meta.client) return;
    try {
      localStorage.setItem(STATION_KEY, JSON.stringify(station.value));
    } catch {
      // Sem storage, vale só nesta montagem.
    }
  }
  function restore() {
    if (station.value.ref || !import.meta.client) return;
    try {
      const parsed = JSON.parse(localStorage.getItem(STATION_KEY) || "null");
      if (parsed && typeof parsed.ref === "string" && parsed.ref) {
        station.value = { ref: parsed.ref, name: String(parsed.name || parsed.ref) };
      }
    } catch {
      // Sem storage ou valor estranho: o rail mostra só Estações.
    }
  }
  return { station, remember, restore };
}

export function useKdsBoardState() {
  return useState<KdsBoardState>("kds-board-state", () => ({
    onBoard: false,
    total: 0,
    serviceDate: "",
    today: "",
    availableDates: [],
  }));
}

/** Ajustes abre como painel (densidade e data), do rail e da barra do polegar. */
export function useKdsSettingsOpen() {
  return useState<boolean>("kds-settings-open", () => false);
}

export function useKdsSections(place: "rail" | "bar") {
  const { station, restore } = useKdsStation();
  const board = useKdsBoardState();
  const route = useRoute();
  const exitUrl = gestorExitUrl(String(useRuntimeConfig().public.ordersUrl || ""));

  // O mesmo índice da tela de estações (mesma chave): o selo da Saída e o do Preparo
  // fora do quadro. Relido a cada 30 s para o selo não envelhecer (só pelo rail, que
  // fica montado em todos os tamanhos: um relógio só).
  const { data: index, refresh } = useFetch<KDSIndexResponse>("/api/v1/backstage/kds/", {
    key: "kds-index",
  });
  let timer: ReturnType<typeof setInterval> | null = null;
  onMounted(() => {
    restore();
    if (place === "rail") timer = setInterval(() => refresh(), 30_000);
  });
  onBeforeUnmount(() => {
    if (timer) clearInterval(timer);
  });

  const instances = computed(() => index.value?.instances ?? []);
  const exitCount = computed(() =>
    instances.value
      .filter((inst) => inst.type === EXIT_STATION_TYPE)
      .reduce((sum, inst) => sum + (inst.active_count || 0), 0),
  );
  const prepCount = computed(() => {
    if (board.value.onBoard) return board.value.total;
    return instances.value.find((inst) => inst.ref === station.value.ref)?.active_count ?? 0;
  });

  const sections = computed(() =>
    kdsSections({
      stationRef: station.value.ref,
      prepCount: prepCount.value,
      exitUrl,
      exitCount: exitCount.value,
      place,
    }),
  );
  const current = computed(() => {
    if (route.path === "/") return "stations";
    if (station.value.ref && route.path.replace(/\/+$/, "") === `/${station.value.ref}`) return "prep";
    return undefined;
  });
  return { sections, current };
}
