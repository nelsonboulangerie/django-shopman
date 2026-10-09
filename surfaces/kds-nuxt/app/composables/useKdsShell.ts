// O que o shell da Cozinha (barra lateral, barra inferior, Ajustes) sabe das telas.
//
// - As estações da casa, do índice do servidor: cada uma é um item da navegação, pelo
//   nome, levando à sua bancada. Não há item genérico "Preparo" (dono, 09/10/2026).
// - A estação deste dispositivo: a aberta agora, ou a última aberta (lembrada por
//   dispositivo). Ela vai à frente na barra inferior.
// - O quadro conta ao shell quantos pedidos tem (selo da estação aberta) e aos Ajustes
//   como a estação se mostra (densidade e som, guardados no cadastro da estação). Fora
//   do quadro os números vêm do índice das estações.
// - A Saída é a coluna do Gestor (SUITE-UX §15): o item é um atalho para lá, com o selo
//   dos pedidos prontos para sair que o índice já conta.
import type { KDSIndexResponse, KDSStationSettingsResponse } from "~/types/kds";
import type { KDSDensity } from "~/presentation/board";
import { EXIT_STATION_TYPE, gestorExitUrl } from "~/presentation/exitStation";
import { kdsSections, stationSectionKey } from "~/presentation/sections";

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
      // Sem storage ou valor estranho: a barra segue a ordem do cadastro.
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

  // O mesmo índice da tela de estações (mesma chave): a lista das estações e os selos
  // fora do quadro. Relido a cada 30 s para o selo não envelhecer (só pelo rail, que
  // fica montado em todos os tamanhos: um relógio só). Vem no payload do servidor, então
  // o servidor e a hidratação desenham a MESMA lista.
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

  // ⚠️ A estação ABERTA é a da ROTA, não a memória. A memória só se preenche no cliente
  // (o quadro grava ao montar; o localStorage se lê no `onMounted`), e o servidor
  // desenha a barra sem ela. Se a memória decidisse a ordem ou o item atual no primeiro
  // desenho, a hidratação montaria outra barra sobre o HTML do servidor: o Vue corrige o
  // texto mas não os atributos, e um item ficava com o `href` do vizinho (#1563). A rota
  // é a mesma nos dois lados; a memória só reordena a barra depois de montar, fora do
  // quadro (reatividade comum, não hidratação).
  const routeStation = computed(() => (route.name === "ref" ? String(route.params.ref || "") : ""));
  const priorityRef = computed(() => routeStation.value || station.value.ref);

  const instances = computed(() => index.value?.instances ?? []);
  const exitCount = computed(() =>
    instances.value
      .filter((inst) => inst.type === EXIT_STATION_TYPE)
      .reduce((sum, inst) => sum + (inst.active_count || 0), 0),
  );
  // A estação de Saída vira o item Saída (Gestor). Sem a URL do Gestor ela segue como
  // estação comum, para não perder o acesso à tela dela.
  const stations = computed(() =>
    instances.value
      .filter((inst) => !(exitUrl && inst.type === EXIT_STATION_TYPE))
      .map((inst) => ({
        ref: inst.ref,
        name: inst.name,
        type: inst.type,
        count:
          board.value.onBoard && board.value.stationRef === inst.ref && inst.ref === routeStation.value
            ? board.value.total
            : inst.active_count || 0,
      })),
  );

  const sections = computed(() =>
    kdsSections({
      stations: stations.value,
      priorityRef: priorityRef.value,
      exitUrl,
      exitCount: exitCount.value,
      place,
    }),
  );
  // A estação da rota é a atual. Fora de uma bancada (a tela de escolher a estação),
  // nenhum item é o atual: "" (não `undefined`) para a barra não adivinhar pela rota.
  const current = computed(() => (routeStation.value ? stationSectionKey(routeStation.value) : ""));
  return { sections, current };
}
