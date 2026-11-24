// Paginação de painel de aeroporto: o quadro tem as linhas que CABEM (medidas na
// tela — kiosk não rola) e o conteúdo excedente vira páginas em ciclo. A
// virada re-monta as linhas → as palhetas cascateiam de novo: a "tempestade
// de clacs" que os painéis mecânicos fazem ao virar a página.
//
// Linha de nome longo ocupa duas linhas de palhetas (WP-F04). Com `lines(item)`,
// a página soma a altura real de cada linha até encher a área; sem ele, todas as
// linhas têm a mesma altura e a página é um tamanho fixo.
import type { Ref } from "vue";

const ROTATE_MS = 12_000;
const ROW_GAP_PX = 6; // vão padrão; a régua medida traz o vão real da tela

/** A régua medida na tela: altura útil, linha de uma linha de nome, o acréscimo
 *  de cada linha de nome a mais e o vão entre linhas. */
export interface BoardPageFit {
  capacity: number;
  base: number;
  extra: number;
  gap?: number;
}

/** Fatia os itens em páginas que cabem na régua, em ordem (nunca reordena). */
export function boardPageStarts(lines: readonly number[], fit: BoardPageFit): number[] {
  const starts = [0];
  const gap = fit.gap ?? ROW_GAP_PX;
  let used = 0;
  lines.forEach((count, index) => {
    const height = fit.base + Math.max(0, count - 1) * fit.extra;
    const next = used === 0 ? height : used + gap + height;
    if (used > 0 && next > fit.capacity) {
      starts.push(index);
      used = height;
    } else {
      used = next;
    }
  });
  return starts;
}

export function useBoardPages<T>(items: Ref<T[]>, lines?: (item: T) => number) {
  const listEl = ref<HTMLElement | null>(null);
  const pageSize = ref(8);
  const fit = ref<BoardPageFit | null>(null);
  const page = ref(0);
  let rotateTimer: ReturnType<typeof setInterval> | null = null;
  let observer: ResizeObserver | null = null;

  const starts = computed<number[]>(() => {
    const total = items.value.length;
    if (lines && fit.value) return boardPageStarts(items.value.map(lines), fit.value);
    const size = Math.max(1, pageSize.value);
    const fixed: number[] = [];
    for (let index = 0; index < Math.max(1, total); index += size) fixed.push(index);
    return fixed;
  });
  const pageCount = computed(() => Math.max(1, starts.value.length));
  const visible = computed(() => {
    const current = Math.min(page.value, pageCount.value - 1);
    const from = starts.value[current] ?? 0;
    const to = starts.value[current + 1] ?? items.value.length;
    return items.value.slice(from, to);
  });

  function measure() {
    const list = listEl.value;
    const rows = list ? [...list.querySelectorAll<HTMLElement>("[data-board-row]")] : [];
    if (!list || !rows.length) return;
    if (lines) {
      // A régua sai de uma linha qualquer: altura, menos o acréscimo das linhas de
      // nome que ela tem a mais. O acréscimo é uma palheta do nome mais o vão.
      const row = rows[0]!;
      const name = row.querySelector<HTMLElement>("[data-board-name]");
      const flap = name?.firstElementChild as HTMLElement | null;
      const count = Number(row.dataset.boardLines || "1") || 1;
      if (!name || !flap || !row.offsetHeight) return;
      const gap = Number.parseFloat(getComputedStyle(name).rowGap) || 0;
      const extra = flap.offsetHeight + gap;
      const rowGap = row.parentElement
        ? Number.parseFloat(getComputedStyle(row.parentElement).rowGap)
        : Number.NaN;
      fit.value = {
        capacity: list.clientHeight,
        base: row.offsetHeight - (count - 1) * extra,
        extra,
        gap: Number.isFinite(rowGap) ? rowGap : ROW_GAP_PX,
      };
      return;
    }
    const tallest = Math.max(0, ...rows.map((row) => row.offsetHeight));
    if (!tallest) return;
    const fits = Math.floor((list.clientHeight + ROW_GAP_PX) / (tallest + ROW_GAP_PX));
    pageSize.value = Math.max(3, fits);
  }

  function goTo(target: number) {
    page.value = ((target % pageCount.value) + pageCount.value) % pageCount.value;
  }

  onMounted(() => {
    void nextTick(measure);
    observer = new ResizeObserver(() => measure());
    if (listEl.value) observer.observe(listEl.value);
    rotateTimer = setInterval(() => {
      if (pageCount.value > 1) goTo(page.value + 1);
    }, ROTATE_MS);
  });

  onUnmounted(() => {
    if (rotateTimer) clearInterval(rotateTimer);
    observer?.disconnect();
  });

  // A lista só nasce quando chega o primeiro lote: observa quando ela aparece.
  watch(listEl, (el, previous) => {
    if (previous) observer?.unobserve(previous);
    if (el) {
      observer?.observe(el);
      void nextTick(measure);
    }
  });

  watch(pageCount, (count) => {
    if (page.value >= count) page.value = 0;
  });
  watch(
    () => items.value.length,
    () => void nextTick(measure),
  );

  return { listEl, visible, page, pageCount, pageSize, goTo };
}
