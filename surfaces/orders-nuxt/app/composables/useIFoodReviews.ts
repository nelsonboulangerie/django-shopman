// Avaliações do iFood: a fonte da verdade é o iFood, e a tela relê a cada gesto
// (filtrar, paginar, abrir, responder). Sem poll: a avaliação aparece no iFood de
// 24 a 48 h depois do pedido, e quem abre a tela quer a leitura de agora.
// A recusa do iFood chega com a mensagem dele (`ifood_message`) e fica na tela.
import { httpError } from "../../../operator-kit/app/utils/httpError";
import { reviewErrorText, type ReviewErrorText } from "~/presentation/ifoodReviews";
import type {
  IFoodReview,
  IFoodReviewError,
  IFoodReviewList,
  IFoodReviewSummary,
} from "~/types/ifoodReviews";

const BASE = "/api/v1/backstage/ifood/reviews/";

function errorOf(error: unknown, fallback: string): ReviewErrorText {
  return reviewErrorText(httpError(error).data as IFoodReviewError | null, fallback);
}

export function useIFoodReviews() {
  const page = ref(1);
  const pageSize = ref(10);
  const dateFrom = ref("");
  const dateTo = ref("");

  const list = ref<IFoodReviewList | null>(null);
  const listError = ref<ReviewErrorText | null>(null);
  const loading = ref(false);
  const summary = ref<IFoodReviewSummary | null>(null);

  const detail = ref<IFoodReview | null>(null);
  const detailId = ref("");
  const detailError = ref<ReviewErrorText | null>(null);
  const detailLoading = ref(false);

  const replying = ref(false);
  const replyError = ref<ReviewErrorText | null>(null);
  const replyDone = ref("");

  async function load() {
    loading.value = true;
    listError.value = null;
    const query: Record<string, string | number> = {
      page: page.value,
      page_size: pageSize.value,
    };
    if (dateFrom.value) query.date_from = dateFrom.value;
    if (dateTo.value) query.date_to = dateTo.value;
    try {
      list.value = await $fetch<IFoodReviewList>(BASE, { query });
    } catch (error) {
      listError.value = errorOf(error, "Não foi possível ler as avaliações do iFood.");
    } finally {
      loading.value = false;
    }
  }

  async function loadSummary() {
    try {
      summary.value = await $fetch<IFoodReviewSummary>(`${BASE}summary/`);
    } catch {
      summary.value = null; // a nota é complemento: a lista segue sem ela
    }
  }

  async function open(id: string) {
    const clean = id.trim();
    if (!clean) return;
    detailId.value = clean;
    detail.value = null;
    detailError.value = null;
    replyError.value = null;
    replyDone.value = "";
    detailLoading.value = true;
    try {
      detail.value = await $fetch<IFoodReview>(`${BASE}${encodeURIComponent(clean)}/`);
    } catch (error) {
      detailError.value = errorOf(error, "Não foi possível abrir esta avaliação.");
    } finally {
      detailLoading.value = false;
    }
  }

  function close() {
    detailId.value = "";
    detail.value = null;
    detailError.value = null;
    replyError.value = null;
    replyDone.value = "";
  }

  async function reply(text: string): Promise<boolean> {
    const id = detailId.value;
    if (!id || replying.value) return false;
    replying.value = true;
    replyError.value = null;
    replyDone.value = "";
    try {
      await $fetch(`${BASE}${encodeURIComponent(id)}/reply/`, {
        method: "POST",
        body: { text },
      });
      // A situação muda no iFood (Aguardando resposta → Respondida): relê os dois.
      await Promise.all([open(id), load()]);
      replyDone.value = "Resposta enviada ao iFood.";
      return true;
    } catch (error) {
      replyError.value = errorOf(error, "O iFood não recebeu a resposta.");
      return false;
    } finally {
      replying.value = false;
    }
  }

  function search() {
    page.value = 1;
    void load();
  }

  function goTo(next: number) {
    page.value = next;
    void load();
  }

  return {
    page,
    pageSize,
    dateFrom,
    dateTo,
    list,
    listError,
    loading,
    summary,
    detail,
    detailId,
    detailError,
    detailLoading,
    replying,
    replyError,
    replyDone,
    load,
    loadSummary,
    open,
    close,
    reply,
    search,
    goTo,
  };
}
