import { toast } from "vue-sonner";

import type { DayClosingResponse } from "~/types/closing";

/** A liberação do fechamento com produção aberta: o porquê e a assinatura do gerente. */
export interface ProductionRelease {
  reason: string;
  manager_approval: { username?: string; pin?: string; badge?: string };
}

interface DayClosingDeps {
  action: { call: (path: string, opts?: { body?: Record<string, unknown> }) => Promise<unknown> };
}

/**
 * Fechamento do DIA na antesala: leitura da projection (mesma
 * `build_day_closing` da retaguarda) e o comando de registrar a contagem
 * cega. Gate é da API (`backstage.perform_closing`): 401/403 viram
 * `accessDenied` e a página explica em vez de quebrar. O POST idempotente
 * responde 409 quando o dia já fechou — o refresh resolve a tela sozinho.
 */
export async function useDayClosing({ action }: DayClosingDeps) {
  const requestHeaders = import.meta.server ? useRequestHeaders(["cookie"]) : undefined;

  const { data, pending, error, refresh } = await useFetch<DayClosingResponse>(
    "/api/v1/backstage/closing/",
    { key: "day-closing", credentials: "include", headers: requestHeaders },
  );

  const closing = computed(() => data.value?.closing ?? null);
  const accessDenied = computed(() => {
    const status = (error.value as { statusCode?: number } | null)?.statusCode;
    return status === 401 || status === 403;
  });

  const submitting = ref(false);

  // Produção aberta IMPEDE selar o dia (decisão do dono, 05/11/2026): o servidor
  // recusa com 409 `pending_production`, e a página abre a liberação (motivo +
  // gerente da lista com PIN). A assinatura recusada (`manager_approval_*`) volta
  // ao diálogo do gerente, não a um toast: a saída É assinar de novo.
  const productionBlock = ref("");
  const releaseChallenge = ref<{ code: string; message: string } | null>(null);

  async function submit(
    quantities: Record<string, string>,
    release: ProductionRelease | null = null,
  ): Promise<boolean> {
    if (submitting.value) return false;
    submitting.value = true;
    const body: Record<string, unknown> = { quantities };
    if (release) body.production_release = release;
    try {
      await action.call("/api/v1/backstage/closing/", { body });
      productionBlock.value = "";
      releaseChallenge.value = null;
      await refresh();
      toast.success(release ? "Fechamento do dia registrado, com a liberação do gerente." : "Fechamento do dia registrado.");
      return true;
    } catch (err) {
      const code = httpErrorCode(err);
      if (code === "pending_production") {
        productionBlock.value = httpErrorMessage(err, "Há produção aberta.");
        await refresh();
        return false;
      }
      if (code === "manager_approval_required" || code === "manager_approval_invalid") {
        releaseChallenge.value = { code, message: httpErrorMessage(err, "Revise o gerente e o PIN.") };
        return false;
      }
      toast.error(`${httpErrorMessage(err, "A contagem do fechamento não foi registrada.")} Os números seguem na tela. Tente de novo.`);
      // 409 (dia já fechado) ou validação: a projection manda na tela.
      await refresh();
      return false;
    } finally {
      submitting.value = false;
    }
  }

  // "Explicar o dia estranho" (V4-PDV): o sistema notou um sinal (o episódio) e quem
  // fecha diz o que houve, escolhendo no catálogo; `kindRef` vazio é "não houve nada".
  // O serviço e a rota já existiam (`closing/episodes/<id>/`); faltava a tela.
  const answering = ref<number | null>(null);
  async function answerEpisode(episodeId: number, kindRef: string, note = ""): Promise<boolean> {
    if (answering.value !== null) return false;
    answering.value = episodeId;
    try {
      await action.call(`/api/v1/backstage/closing/episodes/${episodeId}/`, { body: { kind_ref: kindRef, note } });
      await refresh();
      toast.success(kindRef ? "Resposta registrada. O dia fica marcado para o B.I. e para o plano." : "Registrado: não houve nada.");
      return true;
    } catch (err) {
      toast.error(`${httpErrorMessage(err, "A resposta não foi registrada.")} Tente de novo.`);
      return false;
    } finally {
      answering.value = null;
    }
  }

  return {
    closing,
    pending,
    error,
    accessDenied,
    refresh,
    submitting,
    submit,
    productionBlock,
    releaseChallenge,
    answering,
    answerEpisode,
  };
}
