import { toast } from "vue-sonner";

import type { ManagerApproval } from "~/composables/usePosCashSession";
import { swapDoneMessage } from "~/presentation/preorderSwap";
import type { PreorderSwapItem, PreorderSwapOption, PreorderSwapResponse } from "~/types/preorders";

/**
 * Trocar o item que falta na encomenda (#2765).
 *
 * O Gestor abre o detalhe em `?swap=<sku>`; a página passa os SKUs já lidos do
 * endereço (`swapSkusFromQuery`). A leitura é do servidor, na hora
 * (`GET pos/preorders/<ref>/swap/?sku=…`): as alternativas pela mesma régua do
 * aviso e a diferença de preço pela prévia da edição. A troca grava pela edição
 * da encomenda (`POST pos/preorders/<ref>/swap/`), que relê as alternativas: a
 * que deixou de caber recusa com a frase, e a lista é relida.
 */
export function usePosPreorderSwap(options: {
  ref: Ref<string>;
  skus: Ref<string[]>;
  /** Relê o detalhe da encomenda depois da troca. */
  refresh: () => Promise<unknown> | unknown;
}) {
  const apiPath = useApiPath();
  const action = usePosAction();
  const swap = ref<PreorderSwapResponse | null>(null);
  const loading = ref(false);
  const failed = ref(false);
  const busy = ref(false);
  const managerChallenge = ref<{ code: string; message: string } | null>(null);
  let seq = 0;

  async function load(): Promise<void> {
    const skus = options.skus.value;
    const mine = ++seq;
    if (!skus.length || !options.ref.value) {
      swap.value = null;
      failed.value = false;
      return;
    }
    loading.value = true;
    failed.value = false;
    try {
      const query = new URLSearchParams();
      for (const sku of skus) query.append("sku", sku);
      const response = await $fetch<PreorderSwapResponse>(
        apiPath(`/api/v1/backstage/pos/preorders/${encodeURIComponent(options.ref.value)}/swap/?${query.toString()}`),
        { method: "GET", credentials: "include" },
      );
      if (mine === seq) swap.value = response;
    } catch {
      if (mine === seq) {
        swap.value = null;
        failed.value = true;
      }
    } finally {
      if (mine === seq) loading.value = false;
    }
  }

  watch(() => [options.ref.value, options.skus.value.join("\n")], () => void load(), { immediate: true });

  let lastAttempt: { signature: string; key: string } | null = null;
  function gestureKey(signature: string): string {
    if (lastAttempt?.signature === signature) return lastAttempt.key;
    const key = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    lastAttempt = { signature, key };
    return key;
  }

  /** Grava a troca. `true` quando trocou; o PIN do gerente sobe como `managerChallenge`. */
  async function confirm(
    item: PreorderSwapItem,
    option: PreorderSwapOption,
    managerApproval: ManagerApproval | null = null,
  ): Promise<boolean> {
    const read = swap.value;
    if (!read || busy.value) return false;
    busy.value = true;
    const path = `/api/v1/backstage/pos/preorders/${encodeURIComponent(read.order_ref)}/swap/`;
    const payload = {
      sku: item.sku,
      offer: option.sku,
      base_revision: read.base_revision,
      expected_actor_id: read.expected_actor_id,
    };
    try {
      await action.call(path, {
        body: {
          ...payload,
          idempotency_key: gestureKey(`${path}:${JSON.stringify(payload)}`),
          ...(managerApproval ? { manager_approval: managerApproval } : {}),
        },
      });
      lastAttempt = null;
      managerChallenge.value = null;
      toast.success(swapDoneMessage(item, option));
      await options.refresh();
      return true;
    } catch (error) {
      const code = httpErrorCode(error);
      if (code === "manager_approval_required" || code === "manager_approval_invalid") {
        managerChallenge.value = { code, message: httpErrorMessage(error, "Peça a um gerente para autorizar.") };
        return false;
      }
      managerChallenge.value = null;
      // O servidor respondeu e recusou: o próximo toque é um gesto novo (a
      // alternativa pode voltar a caber), não a repetição deste.
      if (httpError(error).status) lastAttempt = null;
      toast.error(httpErrorMessage(error, "Não deu para trocar o item. Nada mudou: confira a encomenda e tente de novo."));
      // A fornada mudou ou a encomenda mudou: relê a lista e o detalhe.
      await Promise.all([load(), options.refresh()]);
      return false;
    } finally {
      busy.value = false;
    }
  }

  function dismissManagerChallenge() {
    managerChallenge.value = null;
  }

  return { swap, loading, failed, busy, managerChallenge, load, confirm, dismissManagerChallenge };
}
