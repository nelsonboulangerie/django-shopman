// Production planning read-side. Single source for the planning matrix:
//   - useFetch the production board projection (GET /api/v1/backstage/production/);
//   - poll every 60s (planning changes slowly, manager-paced).
// Writes (plan / start) go through the django proxy (CSRF handled there) and
// reconcile via refresh. Order-coverage shortage surfaces as a structured error.
import type { ProductionBoardProjection, ProductionBoardResponse, ProductionShortageError } from "~/types/production";
import { parseShortage } from "~/presentation/production";

export interface BoardActResult {
  ok: boolean;
  shortage?: ProductionShortageError;
}

/** ISO date default for planning: today's board in the morning, tomorrow's
 *  after noon — o padeiro planeja o dia seguinte na calmaria da tarde. */
export function defaultPlanningDate(now = new Date()): string {
  const target = new Date(now.getFullYear(), now.getMonth(), now.getDate() + (now.getHours() >= 12 ? 1 : 0));
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${target.getFullYear()}-${pad(target.getMonth() + 1)}-${pad(target.getDate())}`;
}

export function useProductionBoard(initialDate: string = defaultPlanningDate()) {
  const path = "/api/v1/backstage/production/";
  const selectedDate = ref(initialDate);

  const { data, pending, error, refresh } = useFetch<ProductionBoardResponse>(path, {
    key: "production-board",
    server: true,
    query: computed(() => ({ date: selectedDate.value })),
    onResponseError: operatorSessionOnError,
  });

  const board = computed<ProductionBoardProjection | null>(() => data.value?.board ?? null);
  const rows = computed(() => board.value?.matrix_rows ?? []);
  const counts = computed(() => board.value?.counts ?? null);
  const dateDisplay = computed(() => board.value?.selected_date_display ?? "");

  useAdaptivePoll(refresh, () => 60_000);

  // a planning POST keys on the output_sku row (one in-flight per row).
  const busy = ref<Set<string>>(new Set());
  const isBusy = (key: string) => busy.value.has(key);

  async function post(key: string, url: string, body: Record<string, unknown>): Promise<BoardActResult> {
    if (busy.value.has(key)) return { ok: false };
    busy.value = new Set(busy.value).add(key);
    try {
      await $fetch(url, { method: "POST", body });
      await refresh();
      return { ok: true };
    } catch (err) {
      const shortage = parseShortage(httpError(err).data);
      if (shortage) return { ok: false, shortage };
      useSonner.error(httpErrorMessage(err, "Falha na ação. Tente de novo."));
      return { ok: false };
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }

  // ⚠️ `expected_rev` é a revisão que ESTE quadro leu, e é o que impede duas bancadas
  // de se sobrescreverem. A bancada A ajusta para 40 enquanto a B ajusta para 25 sobre
  // um quadro de sessenta segundos de idade: sem o número, o último POST vence, sem 409
  // e sem aviso. Com ele, a segunda recebe "a fornada mudou em outra tela".
  //
  // Ausente quando o card não é conhecido (planejar uma linha que ainda não tem
  // fornada): não há revisão anterior para comparar, e mandar zero afirmaria uma coisa
  // falsa. O servidor lê ausência como "não confira".
  function plan(
    key: string,
    payload: { recipe_id: number; quantity: string; target_date: string; position_ref?: string; source?: string; force?: boolean },
    expectedRev?: number,
  ): Promise<BoardActResult> {
    return post(key, "/api/v1/backstage/production/plan/", {
      ...payload,
      ...(expectedRev === undefined ? {} : { expected_rev: expectedRev }),
    });
  }

  function start(
    key: string,
    woPk: number,
    quantity: string,
    expectedRev?: number,
  ): Promise<BoardActResult> {
    return post(key, `/api/v1/backstage/production/${woPk}/start/`, {
      quantity,
      ...(expectedRev === undefined ? {} : { expected_rev: expectedRev }),
    });
  }

  return { board, rows, counts, dateDisplay, selectedDate, pending, error, refresh, isBusy, plan, start };
}
