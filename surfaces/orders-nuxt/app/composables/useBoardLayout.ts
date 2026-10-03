// A arrumação das colunas do quadro (Entrada, Preparo, Saída) NESTE posto.
//
// SUITE-UX §16 e lei L7: recolher e ajustar a largura é do posto, e fica no servidor
// (`orders/board-layout/`, que guarda no `Terminal.metadata` da estação confiável).
// O tablet do passe abre só com a Saída mesmo depois de recarregar ou trocar de
// navegador. Sem posto (o navegador não é estação confiável) ou sem servidor, a tela
// abre com as três colunas e o que o operador mudar vale até recarregar.
//
// As regras (o que recolhe, quanto alarga, o que nunca pode sumir) são do kit
// (`operator-kit/app/presentation/queueColumns.ts`); aqui fica só o transporte.
import {
  allQueueColumnsOpen,
  defaultQueueLayout,
  nextOpenQueueKey,
  normalizeQueueLayout,
  openQueueColumn,
  openQueueKeys,
  queueGridTemplate,
  queueViewLabel,
  resizeQueueColumns,
  showAllQueueColumns,
  toggleQueueColumn,
  type QueueColumnLayout,
} from "../../../operator-kit/app/presentation/queueColumns";

export const BOARD_ZONE_KEYS = ["intake", "prep", "expedition"] as const;
export const BOARD_LAYOUT_PATH = "/api/v1/backstage/orders/board-layout/";
/** Espera depois do último gesto antes de gravar (arrastar e apertar 1/2/3 em sequência). */
export const BOARD_LAYOUT_SAVE_DELAY_MS = 600;

interface BoardLayoutResponse {
  station?: string;
  columns?: unknown;
}

interface ResizeStart {
  layout: QueueColumnLayout;
  left: string;
  right: string;
  leftPx: number;
  rightPx: number;
}

export function useBoardLayout(titles: () => Record<string, string>) {
  const keys = BOARD_ZONE_KEYS as readonly string[];
  const layout = ref<QueueColumnLayout>(defaultQueueLayout(keys));
  const station = ref("");
  const saveFailed = ref(false);
  let touched = false;
  let saveTimer: ReturnType<typeof setTimeout> | null = null;
  let resize: ResizeStart | null = null;

  async function load() {
    try {
      const response = await $fetch<BoardLayoutResponse>(BOARD_LAYOUT_PATH);
      station.value = String(response?.station || "");
      // O operador mexeu antes da resposta chegar: vale o gesto, e ele é que vai ao posto.
      if (touched) scheduleSave();
      else layout.value = normalizeQueueLayout(keys, response?.columns);
    } catch {
      // silêncio-deliberado: sem leitura, a tela fica com as três colunas (o padrão).
    }
  }

  async function save() {
    saveTimer = null;
    if (!station.value) return;
    try {
      await $fetch(BOARD_LAYOUT_PATH, { method: "PUT", body: { columns: layout.value } });
      saveFailed.value = false;
    } catch {
      saveFailed.value = true;
    }
  }

  function scheduleSave() {
    if (!station.value) return;
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => { void save(); }, BOARD_LAYOUT_SAVE_DELAY_MS);
  }

  function commit(next: QueueColumnLayout) {
    touched = true;
    if (next === layout.value) return;
    layout.value = next;
    scheduleSave();
  }

  const isOpen = (key: string) => Boolean(layout.value[key]?.open);
  const toggle = (key: string) => commit(toggleQueueColumn(layout.value, keys, key));
  const open = (key: string) => commit(openQueueColumn(layout.value, key));
  const showAll = () => commit(showAllQueueColumns(keys));
  const canCollapse = (key: string) => isOpen(key) && openQueueKeys(layout.value, keys).length > 1;
  const nextOpen = (key: string) => nextOpenQueueKey(layout.value, keys, key);

  /** Começo do arraste da alça de `left`: o pai mede as duas colunas. */
  function startResize(left: string, leftPx: number, rightPx: number) {
    const right = nextOpen(left);
    resize = right ? { layout: layout.value, left, right, leftPx, rightPx } : null;
  }
  /** Prévia: a largura acompanha o dedo, sem gravar. */
  function dragResize(deltaPx: number) {
    if (!resize) return;
    layout.value = resizeQueueColumns(resize.layout, keys, { ...resize, deltaPx, final: false });
  }
  /** Soltou: decide (inclusive recolher) e grava. */
  function endResize(deltaPx: number) {
    if (!resize) return;
    const start = resize;
    resize = null;
    commit(resizeQueueColumns(start.layout, keys, { ...start, deltaPx, final: true }));
  }

  const gridTemplate = computed(() => queueGridTemplate(layout.value, keys));
  const allOpen = computed(() => allQueueColumnsOpen(layout.value, keys));
  const viewLabel = computed(() => queueViewLabel(layout.value, keys, titles()));
  /** De quem é a arrumação: o posto lembra, ou ela vale só até recarregar. */
  const memoryText = computed(() => {
    if (!station.value) return "Este dispositivo não é um posto: a arrumação vale até recarregar a tela.";
    if (saveFailed.value) return "Não deu para guardar a arrumação neste posto: ela vale até recarregar a tela.";
    return "Arrumação lembrada neste posto, no servidor.";
  });

  onMounted(() => { void load(); });
  onBeforeUnmount(() => {
    if (!saveTimer) return;
    clearTimeout(saveTimer);
    void save();
  });

  return {
    keys,
    layout,
    station,
    saveFailed,
    load,
    isOpen,
    toggle,
    open,
    showAll,
    canCollapse,
    nextOpen,
    startResize,
    dragResize,
    endResize,
    gridTemplate,
    allOpen,
    viewLabel,
    memoryText,
  };
}
