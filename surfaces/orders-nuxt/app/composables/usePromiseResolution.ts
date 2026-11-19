import { uncertainOutcomeMessage, useOrderIntention } from "./useOrderIntention";
import {
  NOT_AT_RISK,
  type PromiseResolution,
  type PromiseResolutionConclude,
  type PromiseResolutionRead,
} from "~/presentation/promiseResolution";

/**
 * A leitura e a gravação do diálogo "Resolver" da promessa em risco (WP-G08).
 *
 * **Leitura** (`read`): `GET orders/<ref>/promise-resolution/`. O cartão do painel não
 * leva o contato do cliente nem as escolhas (regra #2434): o diálogo lê ao abrir, e
 * cada abertura lê de novo (as sugestões são recalculadas na hora). A resposta que
 * chega depois de o diálogo fechar, ou de outro pedido abrir, é descartada. A leitura
 * tem prazo: pendurada, vira `error`, com "Tentar de novo". O 409 é o servidor dizendo
 * que o pedido não está mais em risco (`gone`), com a frase dele.
 *
 * **Gravação** (`removeMissing`): só "Tirar o item" grava daqui, pela edição do pedido
 * que já existe (`POST orders/<ref>/edit/`), no protocolo de intenção das outras ações
 * do Gestor (`useOrderIntention`: quem a tela leu, a revisão que ela leu e uma chave
 * por gesto). A lista final (`conclude.items`) e o que a rota exige
 * (`conclude.payload_schema`: `base_revision` e `expected_actor_id`) vêm prontos da
 * leitura. Trocar e remarcar abrem o PDV; cancelar abre o diálogo de cancelar.
 */
const READ_TIMEOUT_MS = 8000;
/** O que fica incerto quando a resposta não volta: "se o item saiu do pedido". */
const REMOVED_SUBJECT = "o item saiu do pedido";

export interface PromiseResolutionOutcome {
  ok: boolean;
  /** `manager_approval_required` / `manager_approval_invalid` sobem o PIN do gerente. */
  code: string;
  /** A frase da recusa, para ficar escrita no diálogo. */
  message: string;
}

const resolutionPath = (ref_: string) =>
  `/api/v1/backstage/orders/${encodeURIComponent(ref_)}/promise-resolution/`;
const editPath = (ref_: string) =>
  `/api/v1/backstage/orders/${encodeURIComponent(ref_)}/edit/`;

export function usePromiseResolution() {
  const intentions = useOrderIntention();
  const resolution = shallowRef<PromiseResolution | null>(null);
  const state = ref<PromiseResolutionRead>("idle");
  /** A frase do estado: a falha da leitura (`error`) ou a do 409 (`gone`). */
  const message = ref("");
  const busy = ref(false);
  let latest = 0;

  async function read(ref_: string): Promise<void> {
    const mine = ++latest;
    resolution.value = null;
    message.value = "";
    state.value = "loading";
    try {
      const response = await $fetch<PromiseResolution>(resolutionPath(ref_), {
        timeout: READ_TIMEOUT_MS,
      });
      if (mine !== latest) return;
      resolution.value = response;
      state.value = "ready";
    } catch (error) {
      if (mine !== latest) return;
      if (httpError(error).status === 409) {
        message.value = httpErrorMessage(error, NOT_AT_RISK);
        state.value = "gone";
        return;
      }
      message.value = httpErrorMessage(error, "");
      state.value = "error";
    }
  }

  function clear() {
    latest += 1;
    resolution.value = null;
    message.value = "";
    state.value = "idle";
  }

  /**
   * Tira do pedido o que falta, com a lista final que o servidor montou. `approval` é
   * a assinatura do gerente (PIN ou crachá) quando a escolha a pede.
   */
  async function removeMissing(
    ref_: string,
    conclude: PromiseResolutionConclude,
    approval?: Record<string, string>,
  ): Promise<PromiseResolutionOutcome> {
    if (busy.value) return { ok: false, code: "", message: "" };
    busy.value = true;
    try {
      await intentions.executePath(
        `${ref_}:edit`,
        editPath(ref_),
        {
          enabled: true,
          reason: "",
          method: "POST",
          payload_schema: conclude.payload_schema,
        },
        { items: conclude.items },
        approval,
        { subject: REMOVED_SUBJECT, where: "o pedido" },
      );
      return { ok: true, code: "", message: "" };
    } catch (error) {
      // A recusa do servidor vem com a frase dele. A do protocolo de intenção (a
      // identificação mudou, o resultado ficou incerto) é um `Error` simples, com a
      // frase pronta. O resto (rede, resposta sem frase) não prova que nada mudou.
      const own = error instanceof Error && error.name === "Error" ? error.message : "";
      return {
        ok: false,
        code: httpErrorCode(error),
        message: httpErrorMessage(error, own || uncertainOutcomeMessage(REMOVED_SUBJECT, "o pedido")),
      };
    } finally {
      busy.value = false;
    }
  }

  return { resolution, state, message, busy, read, clear, removeMissing };
}
