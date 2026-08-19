// Cenários com IA: lista versionada + "gerar" (POST síncrono, leva segundos).
// A tela só oferece o botão se o servidor disser `configured` — oferecer e
// falhar depois ensina o gestor a não confiar no recurso.
import type { BIScenarioReportView, BIScenariosPage } from "~/types/bi";

export function useBiScenarios() {
  const { data, pending, error, refresh } = useFetch<{ bi: BIScenariosPage }>(
    "/api/v1/backstage/bi/scenarios/",
    { key: "bi-scenarios", server: true, onResponseError: operatorSessionOnError },
  );
  const page = computed(() => data.value?.bi ?? null);
  const generating = ref(false);

  async function generate(focus: string): Promise<BIScenarioReportView | null> {
    generating.value = true;
    try {
      const response = await $fetch<{ bi: BIScenarioReportView }>("/api/v1/backstage/bi/scenarios/", {
        method: "POST",
        body: { focus },
      });
      await refresh();
      if (response.bi.status === "failed") {
        useSonner.error("A IA não respondeu no formato esperado; o registro ficou salvo com o motivo.");
      } else {
        useSonner.success("Cenários gerados.");
      }
      return response.bi;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não deu para gerar os cenários."));
      return null;
    } finally {
      generating.value = false;
    }
  }

  return { page, pending, error, refresh, generate, generating };
}
