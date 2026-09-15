// Relatórios de produção — read-side da página /reports (persona GESTOR).
// GET /api/v1/backstage/production/reports/ com os filtros da tela; o payload
// traz somente a página da visão selecionada + as opções de filtro
// (fichas/postos). O CSV tem lifecycle explícito e cancelável neste composable.
// 403 é um estado LEGÍTIMO (operador de chão sem a perm fina de gestor) — a
// página o trata com calma; por isso este fetch não aciona operatorSessionOnError.
import type { Ref } from "vue";
import type { ProductionReportsResponse } from "~/types/production";
import {
  type ReportFiltersQuery,
  reportsCsvUrl,
  reportsQuery,
} from "~/presentation/reports";

export type ReportExportStatus =
  | "idle"
  | "pending"
  | "success"
  | "failure"
  | "session_expired"
  | "cancelled";

export function useProductionReports(
  filters: Ref<ReportFiltersQuery>,
  exportEligible: Ref<boolean>,
) {
  const { data, pending, error, refresh } = useFetch<ProductionReportsResponse>(
    "/api/v1/backstage/production/reports/",
    {
      key: "production-reports",
      server: true,
      query: computed(() => reportsQuery(filters.value)),
    },
  );

  const reports = computed(() => data.value?.reports ?? null);
  const pagination = computed(() => data.value?.pagination ?? null);
  const historyRows = computed(() => reports.value?.history_rows ?? []);
  const operatorRows = computed(() => reports.value?.operator_rows ?? []);
  const wasteRows = computed(() => reports.value?.waste_rows ?? []);
  const qualityRows = computed(() => reports.value?.quality_rows ?? []);
  const availableRecipes = computed(
    () => reports.value?.available_recipes ?? [],
  );
  const availablePositions = computed(
    () => reports.value?.available_positions ?? [],
  );
  const forbidden = computed(() => httpError(error.value).status === 403);
  const cursorStale = computed(
    () => httpErrorCode(error.value) === "stale_report_cursor",
  );
  const csvUrl = computed(() => reportsCsvUrl(filters.value));
  const exportStatus = ref<ReportExportStatus>("idle");
  const exportMessage = ref("");
  let exportController: AbortController | null = null;

  const canExport = computed(
    () =>
      exportEligible.value &&
      !cursorStale.value &&
      exportStatus.value !== "pending",
  );

  async function downloadCsv(): Promise<boolean> {
    if (!canExport.value) return false;
    exportController = new AbortController();
    exportStatus.value = "pending";
    exportMessage.value = "Preparando exportação…";
    try {
      const blob = await $fetch<Blob>(csvUrl.value, {
        responseType: "blob",
        signal: exportController.signal,
      });
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = `producao_${filters.value.report_kind}_${filters.value.date_from}_${filters.value.date_to}.csv`;
      link.click();
      URL.revokeObjectURL(objectUrl);
      exportStatus.value = "success";
      exportMessage.value = "Relatório baixado.";
      return true;
    } catch (caught) {
      if ((caught as { name?: string }).name === "AbortError") {
        exportStatus.value = "cancelled";
        exportMessage.value = "Exportação cancelada.";
      } else {
        const status = httpError(caught).status;
        const sessionExpired =
          status === 401 ||
          (status === 403 && httpErrorCode(caught) === "not_authenticated");
        if (sessionExpired) {
          operatorSessionOnError({ response: { status } });
          exportStatus.value = "session_expired";
          exportMessage.value = "Sua sessão expirou. Identifique-se novamente para exportar.";
        } else {
          exportStatus.value = "failure";
          exportMessage.value = "Não foi possível baixar o relatório. Tente novamente.";
        }
      }
      return false;
    } finally {
      exportController = null;
    }
  }

  function cancelExport(): void {
    exportController?.abort();
  }

  watch(
    filters,
    () => {
      if (exportStatus.value === "pending") cancelExport();
      else {
        exportStatus.value = "idle";
        exportMessage.value = "";
      }
    },
    { deep: true },
  );

  return {
    reports,
    pagination,
    historyRows,
    operatorRows,
    wasteRows,
    qualityRows,
    availableRecipes,
    availablePositions,
    forbidden,
    cursorStale,
    canExport,
    exportStatus,
    exportMessage,
    downloadCsv,
    cancelExport,
    pending,
    error,
    refresh,
  };
}
