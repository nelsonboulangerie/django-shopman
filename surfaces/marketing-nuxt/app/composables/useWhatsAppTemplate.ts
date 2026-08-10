// O template aprovado do WhatsApp, escolhido aqui — onde o anúncio é operado.
//
// "Admin = só config" limita o Admin; não exila configuração do app de operador. Escolher
// o template com que o anúncio sai é inseparável de operar o anúncio, então quem decide
// publicar muda isso sem trocar de aplicativo.
import type { WhatsAppTemplateResponse } from "~/types/campaign";

export function useWhatsAppTemplate() {
  const { data, refresh, pending } = useFetch<WhatsAppTemplateResponse>(
    "/api/v1/backstage/marketing/whatsapp-template/",
    { key: "marketing-wa-template", server: false, immediate: false },
  );

  const current = computed(() => data.value?.current ?? "");
  const available = computed(() => data.value?.available ?? []);
  /** `false` = não consegui perguntar à plataforma. Diferente de "não há template". */
  const canList = computed(() => data.value?.can_list ?? false);

  async function choose(flowNs: string): Promise<boolean> {
    try {
      await $fetch("/api/v1/backstage/marketing/whatsapp-template/", {
        method: "POST",
        body: { flow_ns: flowNs },
      });
      useSonner.success(
        flowNs
          ? "Template escolhido. O anúncio passa a alcançar quem não conversou hoje."
          : "Template removido. O anúncio volta a alcançar só a janela de 24h.",
      );
      await refresh();
      return true;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não foi possível escolher o template."));
      return false;
    }
  }

  return { current, available, canList, loading: pending, load: refresh, choose };
}
