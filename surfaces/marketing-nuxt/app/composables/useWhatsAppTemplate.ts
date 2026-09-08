// O template aprovado do WhatsApp, escolhido aqui — onde o anúncio é operado.
//
// "Admin = só config" limita o Admin; não exila configuração do app de operador. Escolher
// o template com que o anúncio sai é inseparável de operar o anúncio, então quem decide
// publicar muda isso sem trocar de aplicativo.
import type {
  MarketingTestReceipt,
  WhatsAppTemplateResponse,
} from "~/types/campaign";

export function useWhatsAppTemplate() {
  const { data, refresh, pending } = useFetch<WhatsAppTemplateResponse>(
    "/api/v1/backstage/marketing/whatsapp-template/",
    { key: "marketing-wa-template", server: false, immediate: false },
  );

  const current = computed(() => data.value?.current ?? "");
  const available = computed(() => data.value?.available ?? []);
  const testTargets = computed(() => data.value?.test_targets ?? []);
  const canSendTest = computed(() => data.value?.can_send_test ?? false);
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
      useSonner.error(
        httpErrorMessage(err, "Não foi possível escolher o template."),
      );
      return false;
    }
  }

  /** Campos que o teste enviou, para a tela mostrar o que o template recebeu. */
  const testFields = ref<Record<string, string>>({});
  const testReceipt = ref<MarketingTestReceipt | null>(null);
  const testing = ref(false);

  /**
   * Manda UM teste para uma ref verificada. O recipient real nunca entra no browser.
   */
  async function sendTest(
    targetRef: string,
    options: { sku?: string; body?: string } = {},
  ) {
    testing.value = true;
    try {
      const response = await $fetch<MarketingTestReceipt>(
        "/api/v1/backstage/marketing/whatsapp-template/test/",
        {
          method: "POST",
          headers: { "Idempotency-Key": crypto.randomUUID() },
          body: {
            target_ref: targetRef,
            sku: options.sku || "",
            body: options.body || "",
          },
        },
      );
      testFields.value = response.fields || {};
      testReceipt.value = response;
      if (response.ok) {
        useSonner.success(
          "Sandbox aceitou. Confira o aparelho; aceite ainda não é entrega.",
        );
      } else {
        useSonner.error(
          "O sandbox não confirmou aceite. O receipt ficou guardado.",
        );
      }
      return response.ok;
    } catch (err) {
      useSonner.error(
        httpErrorMessage(err, "Não foi possível enviar o teste."),
      );
      return false;
    } finally {
      testing.value = false;
    }
  }

  return {
    current,
    available,
    testTargets,
    canSendTest,
    canList,
    loading: pending,
    load: refresh,
    choose,
    sendTest,
    testing,
    testFields,
    testReceipt,
  };
}
