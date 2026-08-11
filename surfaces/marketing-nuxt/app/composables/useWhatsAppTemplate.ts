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

  /** Campos que o teste enviou, para a tela mostrar o que o template recebeu. */
  const testFields = ref<Record<string, string>>({});
  const testing = ref(false);

  /**
   * Manda UM teste para UM número. Não resolve audiência nem consentimento: é o gestor
   * conferindo o próprio WhatsApp, e é por isso que o destinatário é digitado.
   */
  async function sendTest(recipient: string, options: { sku?: string; name?: string } = {}) {
    testing.value = true;
    try {
      const response = await $fetch<{
        ok: boolean; backend: string; fields: Record<string, string>; detail: string;
      }>("/api/v1/backstage/marketing/whatsapp-template/test/", {
        method: "POST",
        body: { recipient, sku: options.sku || "", name: options.name || "" },
      });
      testFields.value = response.fields || {};
      if (response.ok) {
        // Aceito pelo provedor ≠ entregue no aparelho. Dizer isso evita o gestor
        // concluir que está tudo bem quando o celular não vibrou.
        useSonner.success(`Enviado por ${response.backend}. Confira o aparelho.`);
      } else {
        useSonner.error(response.detail || "O transporte não aceitou o envio.");
      }
      return response.ok;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não foi possível enviar o teste."));
      return false;
    } finally {
      testing.value = false;
    }
  }

  return {
    current, available, canList, loading: pending, load: refresh, choose,
    sendTest, testing, testFields,
  };
}
