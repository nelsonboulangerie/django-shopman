import type { CashSessionReportResponse } from "~/types/cashReport";

/**
 * Relatório da sessão de caixa na antesala (/session/report): leitura X do
 * turno ABERTO do operador, leituras Z dos turnos FECHADOS do dia e o
 * histórico agregado. Read-only — a projection é a fonte da verdade e nunca
 * expõe o esperado da gaveta (blind count). Gate é da API
 * (`cashman.audit_shift`): a tela mostra FATURAMENTO do dia, e quem opera não
 * audita — nem o gerente. 401/403 viram `accessDenied` e a página explica em
 * vez de quebrar.
 */
export async function useCashReport(options: { terminalRef?: () => string } = {}) {
  const requestHeaders = import.meta.server ? useRequestHeaders(["cookie"]) : undefined;

  // O X é da GAVETA desta superfície: sem `terminal_ref` o servidor cai no
  // primeiro terminal ativo — exato com uma gaveta só, e errado no dia em que
  // houver balcão + totem (a projection documenta o defeito; a query o fecha).
  const { data, pending, error, refresh } = await useFetch<CashSessionReportResponse>(
    () => {
      const terminalRef = options.terminalRef?.() || "";
      return terminalRef
        ? `/api/v1/backstage/pos/cash/report/?terminal_ref=${encodeURIComponent(terminalRef)}`
        : "/api/v1/backstage/pos/cash/report/";
    },
    { key: "cash-session-report", credentials: "include", headers: requestHeaders },
  );

  const report = computed(() => data.value?.report ?? null);
  const accessDenied = computed(() => {
    const status = (error.value as { statusCode?: number } | null)?.statusCode;
    return status === 401 || status === 403;
  });

  return { report, pending, error, accessDenied, refresh };
}
