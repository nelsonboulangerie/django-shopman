// Preparação: a lista do dia e o "Separado" da bancada.
//
// Leitura da lista (GET /api/v1/backstage/production/mise-en-place/):
//   - expand=false (padrão): ingredientes imediatos, com a quebra por receita;
//   - expand=true: pré-preparos abertos até a matéria-prima.
//
// O "Separado" mora no servidor e vale para a bancada inteira (D-042, item 5;
// WP-F09a): GET/POST em /production/mise-en-place/marks/. A marca é presa ao item,
// à data e à quantidade que a pessoa viu; mudou a quantidade daquele item, ela cai
// no servidor, e só então. Nada de "Separado" no dispositivo.
//   - item de "Por insumo": `<sku>`;
//   - ingrediente de "Por preparo": `<recipe_ref>/<sku>`.
// A tela marca na hora (otimista) e desfaz com aviso se o servidor recusar.
//
// Tempo real (ADR-016, WP-F15): a lista e as marcas ouvem o MESMO canal da Produção
// (`useProductionLive`, uma conexão por app). Outro tablet marca, ou a Cozinha
// planeja e muda a quantidade, e a tela relê as duas leituras; o poll de 60 s fica de
// reserva.
import type { Ref } from "vue";
import type { MiseEnPlaceLineProjection, MiseEnPlaceResponse } from "~/types/production";
import { formatClock } from "../../../operator-kit/app/presentation/clock";
import { useProductionLive } from "~/composables/useProductionLive";

export const PREP_MARKS_PATH = "/api/v1/backstage/production/mise-en-place/marks/";
/** A cadência da Preparação enquanto o canal não está aberto. */
const PREP_POLL_MS = 60_000;

export interface PrepMark {
  item_ref: string;
  quantity: string;
  marked_by: string;
  marked_at: string;
}

export interface PrepMarksResponse {
  date: string;
  marks: PrepMark[];
}

interface PrepMarkWriteResponse extends PrepMarksResponse {
  mark: PrepMark | null;
}

/** A chave do item numa linha de "Por insumo". */
export function lineItemRef(sku: string): string {
  return sku;
}

/** A chave do ingrediente de um preparo ("Por preparo"). */
export function prepIngredientItemRef(recipeRef: string, sku: string): string {
  return `${recipeRef}/${sku}`;
}

/** A marca que vale para o item na quantidade que a tela mostra, ou `null`. */
export function markFor(
  marks: readonly PrepMark[],
  itemRef: string,
  quantity: string,
): PrepMark | null {
  return marks.find((mark) => mark.item_ref === itemRef && mark.quantity === quantity) ?? null;
}

/** "Separado por Ana às 5h40": quem e quando, como o servidor gravou. */
export function markAuthorLine(mark: PrepMark | null): string {
  if (!mark) return "";
  const time = formatClock(mark.marked_at);
  const who = mark.marked_by ? ` por ${mark.marked_by}` : "";
  return `Separado${who}${time ? ` às ${time}` : ""}`;
}

export function useMiseEnPlace(selectedDate: Ref<string>) {
  const expand = ref(false);

  const { data, pending, error, refresh } = useFetch<MiseEnPlaceResponse>(
    "/api/v1/backstage/production/mise-en-place/",
    {
      key: "production-mise-en-place",
      server: true,
      query: computed(() => ({ expand: expand.value ? "1" : "", date: selectedDate.value })),
    },
  );

  const projection = computed(() => data.value?.mise_en_place ?? null);
  const lines = computed<MiseEnPlaceLineProjection[]>(() => projection.value?.lines ?? []);

  const { realtime, fallbackPollMs } = useProductionLive(refresh, () => PREP_POLL_MS);

  return { projection, lines, expand, pending, error, refresh, realtime, fallbackPollMs };
}

export function usePrepMarks(selectedDate: Ref<string>, onQuantityChanged: () => unknown = () => {}) {
  const { data, error, refresh } = useFetch<PrepMarksResponse>(PREP_MARKS_PATH, {
    key: "production-prep-marks",
    server: true,
    query: computed(() => ({ date: selectedDate.value })),
    onResponseError: operatorSessionOnError,
  });

  const marks = computed<PrepMark[]>(() => data.value?.marks ?? []);

  // O gesto em voo: a tela já mostra o resultado, o servidor ainda não respondeu.
  const optimistic = ref<Map<string, boolean>>(new Map());
  const inFlight = new Set<string>();

  function isMarked(itemRef: string, quantity: string): boolean {
    const pendingState = optimistic.value.get(itemRef);
    if (pendingState !== undefined) return pendingState;
    return markFor(marks.value, itemRef, quantity) !== null;
  }

  function markOf(itemRef: string, quantity: string): PrepMark | null {
    if (optimistic.value.has(itemRef)) return null;
    return markFor(marks.value, itemRef, quantity);
  }

  function setOptimistic(itemRef: string, state: boolean | undefined) {
    const next = new Map(optimistic.value);
    if (state === undefined) next.delete(itemRef);
    else next.set(itemRef, state);
    optimistic.value = next;
  }

  async function toggle(itemRef: string, quantity: string, name: string): Promise<boolean> {
    if (inFlight.has(itemRef)) return false;
    const checked = !isMarked(itemRef, quantity);
    inFlight.add(itemRef);
    setOptimistic(itemRef, checked);
    try {
      const response = await $fetch<PrepMarkWriteResponse>(PREP_MARKS_PATH, {
        method: "POST",
        body: { date: selectedDate.value, item_ref: itemRef, quantity, checked },
      });
      data.value = { date: response.date, marks: response.marks };
      return true;
    } catch (err) {
      const status = httpError(err).status;
      const fallback = checked
        ? `Não deu para marcar ${name} como separado. Marque de novo.`
        : `Não deu para desmarcar ${name}. Tente de novo.`;
      useSonner.error(httpErrorMessage(err, fallback));
      // 409: a quantidade mudou desde que a lista abriu; a tela relê para mostrar a de agora.
      if (status === 409) onQuantityChanged();
      refresh();
      return false;
    } finally {
      setOptimistic(itemRef, undefined);
      inFlight.delete(itemRef);
    }
  }

  // SSE primeiro (ADR-016): outro tablet marcou, esta tela relê as marcas. O poll de
  // reserva cobre o canal caído.
  useProductionLive(refresh, () => PREP_POLL_MS);

  return { marks, error, refresh, isMarked, markOf, toggle };
}
