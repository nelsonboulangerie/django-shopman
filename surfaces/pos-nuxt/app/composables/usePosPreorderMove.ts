import type { ComputedRef } from "vue";
import { toast } from "vue-sonner";

import { moveConfirmLabel, moveDescription, moveQuestion } from "~/presentation/preorders";
import { dateLabel } from "~/presentation/schedule";
import type { PreorderCard, PreorderDetail, PreorderDetailResponse } from "~/types/preorders";
import type { POSProjection } from "~/types/pos";

/**
 * Mudar uma encomenda de dia a partir da LISTA (arrastar o card na semana, ou o
 * menu do card, que é o mesmo gesto por teclado e toque).
 *
 * Não há rota nova: é o Reagendar do detalhe (`usePosPreorderActions.reschedule`,
 * a rota do Gestor `/orders/<ref>/reschedule/`). A lista não carrega a revisão da
 * data nem a janela combinada, então o gesto lê o detalhe da encomenda primeiro
 * (a régua `counter.reschedule`: pode, por que não, a janela, a revisão) e só
 * então pergunta, no diálogo da casa (`useConfirm`), com o aviso ao cliente dito.
 *
 * - Soltar num dia: a janela combinada vai junto. Se o servidor recusa (a janela
 *   não cabe no dia novo, falta estoque), o toast diz o motivo e o diálogo do
 *   Reagendar abre já no dia escolhido, para escolher outro horário ou outro dia.
 * - "Outra data ou horário…": o diálogo do Reagendar direto, como no detalhe.
 */
export function usePosPreorderMove(options: {
  pos: ComputedRef<POSProjection | null>;
  today: ComputedRef<string> | { value: string };
  refresh: () => Promise<unknown>;
}) {
  const apiPath = useApiPath();
  const confirm = useConfirm();
  const detail = ref<PreorderDetail | null>(null);
  const actions = usePosPreorderActions({ detail, pos: options.pos, refresh: options.refresh });
  const loading = ref("");

  // O diálogo do Reagendar, com o dia em que ele abre.
  const dialogOpen = ref(false);
  const dialogDate = ref("");

  /** A régua do servidor para esta encomenda; `null` quando não pode (e o toast já disse). */
  async function prepare(ref: string): Promise<PreorderDetail | null> {
    if (loading.value || actions.busy.value) return null;
    loading.value = ref;
    try {
      const response = await $fetch<PreorderDetailResponse>(
        apiPath(`/api/v1/backstage/pos/preorders/${encodeURIComponent(ref)}/`),
        { credentials: "include" },
      );
      detail.value = response.order;
    } catch (error) {
      toast.error(`${httpErrorMessage(error, "Não deu para ler a encomenda.")} Tente de novo, ou reagende pelo detalhe da encomenda.`);
      return null;
    } finally {
      loading.value = "";
    }
    const rule = detail.value.counter.reschedule;
    if (!rule.allowed) {
      toast.error(rule.block_reason || "Esta encomenda não pode mudar de data.");
      return null;
    }
    return detail.value;
  }

  function openDialog(date: string) {
    dialogDate.value = date;
    dialogOpen.value = true;
  }

  /** Soltar o card num dia (ou escolher o dia no menu). `true` quando mudou. */
  async function moveTo(card: Pick<PreorderCard, "ref" | "customer_name" | "commitment_date" | "window_label">, date: string): Promise<boolean> {
    if (!date || date === card.commitment_date) return false;
    const ready = await prepare(card.ref);
    if (!ready) return false;
    const rule = ready.counter.reschedule;
    const day = dateLabel(date, options.today.value);
    const agreed = await confirm({
      title: moveQuestion(card.customer_name, day),
      description: moveDescription(card.window_label),
      confirmLabel: moveConfirmLabel(day),
      cancelLabel: "Manter a data",
    });
    if (!agreed) return false;
    const done = await actions.reschedule({ date, slot: rule.slot, reason: "" });
    if (!done) openDialog(date);
    return done;
  }

  /** "Outra data ou horário…": o diálogo do Reagendar, como no detalhe. */
  async function chooseOther(card: Pick<PreorderCard, "ref">) {
    const ready = await prepare(card.ref);
    if (ready) openDialog(ready.counter.reschedule.date);
  }

  async function confirmDialog(choice: { date: string; slot: string; reason: string }) {
    if (await actions.reschedule(choice)) dialogOpen.value = false;
  }

  return {
    detail,
    loading,
    busy: actions.busy,
    dialogOpen,
    dialogDate,
    moveTo,
    chooseOther,
    confirmDialog,
  };
}
