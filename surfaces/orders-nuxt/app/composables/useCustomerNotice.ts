import type {
  CustomerNoticeOptions,
  CustomerNoticePreview,
} from "~/presentation/customerNotice";

/**
 * A leitura do "Avisar o cliente" (WP-G07): as três escolhas ao abrir e a mensagem de
 * cada escolha completa. Nada aqui envia: o envio é a ação do detalhe
 * (`useOrderDetail().notifyCustomer`), no protocolo de intenção de sempre.
 *
 * Cada abertura lê de novo (as horas prontas são as de agora). A resposta que chega
 * depois de outra leitura começar é descartada; a leitura tem prazo e, pendurada, vira
 * `error` com "Tentar de novo".
 */
const READ_TIMEOUT_MS = 8000;

const previewPath = (ref_: string) =>
  `/api/v1/backstage/orders/${encodeURIComponent(ref_)}/customer-notice/preview/`;

export type CustomerNoticeRead = "idle" | "loading" | "ready" | "error";

export function useCustomerNotice() {
  const options = shallowRef<CustomerNoticeOptions | null>(null);
  const state = ref<CustomerNoticeRead>("idle");
  const message = ref("");
  const preview = shallowRef<CustomerNoticePreview | null>(null);
  /** A recusa da prévia (hora que passou, item que saiu do pedido), com a frase do servidor. */
  const previewError = ref("");
  const previewing = ref(false);
  let latestRead = 0;
  let latestPreview = 0;

  async function read(ref_: string): Promise<void> {
    const mine = ++latestRead;
    options.value = null;
    message.value = "";
    state.value = "loading";
    try {
      const response = await $fetch<CustomerNoticeOptions>(previewPath(ref_), {
        timeout: READ_TIMEOUT_MS,
      });
      if (mine !== latestRead) return;
      options.value = response;
      state.value = "ready";
    } catch (error) {
      if (mine !== latestRead) return;
      message.value = httpErrorMessage(error, "");
      state.value = "error";
    }
  }

  async function show(ref_: string, inputs: Record<string, unknown> | null): Promise<void> {
    const mine = ++latestPreview;
    preview.value = null;
    previewError.value = "";
    if (!inputs) {
      previewing.value = false;
      return;
    }
    previewing.value = true;
    try {
      const response = await $fetch<CustomerNoticePreview>(previewPath(ref_), {
        method: "POST",
        body: inputs,
        timeout: READ_TIMEOUT_MS,
      });
      if (mine !== latestPreview) return;
      preview.value = response;
    } catch (error) {
      if (mine !== latestPreview) return;
      previewError.value = httpErrorMessage(error, "Não deu para montar a mensagem. Tente de novo.");
    } finally {
      if (mine === latestPreview) previewing.value = false;
    }
  }

  function clear() {
    latestRead += 1;
    latestPreview += 1;
    options.value = null;
    preview.value = null;
    previewError.value = "";
    previewing.value = false;
    message.value = "";
    state.value = "idle";
  }

  return { options, state, message, preview, previewError, previewing, read, show, clear };
}
