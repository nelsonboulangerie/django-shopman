// O que o shell da Cozinha (rail, barra do polegar, Ajustes) sabe das telas.
//
// - A estação deste dispositivo: a aberta agora, ou a última aberta (lembrada por
//   dispositivo). É ela que o item "Preparo" do rail abre.
// - O quadro conta ao rail quantos pedidos tem (selo do Preparo) e aos Ajustes como a
//   estação se mostra (densidade e som, guardados no cadastro da estação). Fora do
//   quadro os números vêm do índice das estações.
// - A Saída é a coluna do Gestor (SUITE-UX §15): o item do rail é um atalho para lá,
//   com o selo dos pedidos prontos para sair que o índice já conta.
import type { KDSIndexResponse, KDSStationSettingsResponse } from "~/types/kds";
import type { KDSDensity } from "~/presentation/board";
import { EXIT_STATION_TYPE, gestorExitUrl } from "~/presentation/exitStation";
import { kdsSections } from "~/presentation/sections";

export interface KdsStationMemory {
  ref: string;
  name: string;
}

export interface KdsBoardState {
  onBoard: boolean;
  total: number;
  /** A estação do quadro aberto (os Ajustes gravam nela). */
  stationRef: string;
  stationName: string;
  /** Como a estação provisionada se mostra (prévia v4, nota 1). */
  density: KDSDensity;
  soundEnabled: boolean;
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
    stationRef: "",
    stationName: "",
    density: "cozy",
    soundEnabled: true,
  }));
}

/** Ajustes abre como painel (densidade e som da estação), do rail e da barra do polegar. */
export function useKdsStationSettings() {
  const board = useKdsBoardState();
  const busy = useState<boolean>("kds-station-settings-busy", () => false);

  /** Grava densidade e/ou som no cadastro da estação aberta. Otimista: o quadro muda
   *  na hora; recusa volta ao que era e avisa. As outras telas da estação releem pelo
   *  SSE que o servidor manda. */
  async function save(change: { density?: KDSDensity; sound_enabled?: boolean }): Promise<boolean> {
    const ref = board.value.stationRef;
    if (!ref || busy.value) return false;
    const before = { density: board.value.density, soundEnabled: board.value.soundEnabled };
    board.value = {
      ...board.value,
      density: change.density ?? board.value.density,
      soundEnabled: change.sound_enabled ?? board.value.soundEnabled,
    };
    busy.value = true;
    try {
      const saved = (await ($fetch as (
        path: string,
        opts: { method: string; body: Record<string, unknown> },
      ) => Promise<unknown>)(`/api/v1/backstage/kds/${encodeURIComponent(ref)}/settings/`, {
        method: "PATCH",
        body: change,
      })) as KDSStationSettingsResponse;
      board.value = {
        ...board.value,
        density: saved.density === "compact" || saved.density === "roomy" ? saved.density : "cozy",
        soundEnabled: saved.sound_enabled,
      };
      await refreshNuxtData(`kds-board-${ref}`);
      return true;
    } catch (err) {
      board.value = { ...board.value, ...before };
      useSonner.error(httpErrorMessage(err, "Não deu para gravar os ajustes da estação. Tente de novo."));
      return false;
    } finally {
      busy.value = false;
    }
  }

  return { busy, save };
}

/** Ajustes abre como painel (densidade e som da estação), do rail e da barra do polegar. */
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
