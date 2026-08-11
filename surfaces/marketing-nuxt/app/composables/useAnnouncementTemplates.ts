// Modelos de anúncio, criados e editados AQUI.
//
// ⚠️ Existiam só no Admin, e a tela de regra mandava o gestor para lá: "Crie um no Admin
// antes de criar a regra". Sem nenhum modelo, era impossível criar campanha pelo app — a
// operação inteira travava numa porta que não é a dele. A API sempre existiu
// (`marketing/templates/`); faltava a tela.
//
// A regra do dono: config inseparável da operação mora onde a operação acontece. Escrever
// o texto que vai para o cliente é isso.
import type { AnnouncementTemplate } from "~/types/campaign";

export function useAnnouncementTemplates() {
  const { data, refresh, pending } = useFetch<{ templates: AnnouncementTemplate[] }>(
    "/api/v1/backstage/marketing/templates/",
    { key: "marketing-templates" },
  );

  const templates = computed(() => data.value?.templates ?? []);

  async function create(payload: Record<string, unknown>): Promise<boolean> {
    return write("POST", "/api/v1/backstage/marketing/templates/", payload, "Modelo criado.");
  }

  async function patch(pk: number, payload: Record<string, unknown>): Promise<boolean> {
    return write(
      "PATCH", `/api/v1/backstage/marketing/templates/${pk}/`, payload, "Modelo salvo.",
    );
  }

  async function remove(pk: number): Promise<boolean> {
    // O backend recusa apagar modelo em uso (PROTECT) e explica; a tela mostra a razão
    // dele em vez de inventar uma.
    return write(
      "DELETE", `/api/v1/backstage/marketing/templates/${pk}/`, undefined, "Modelo apagado.",
    );
  }

  async function write(
    method: "POST" | "PATCH" | "DELETE",
    url: string,
    body: Record<string, unknown> | undefined,
    okMessage: string,
  ): Promise<boolean> {
    try {
      await $fetch(url, { method, body });
      useSonner.success(okMessage);
      await refresh();
      return true;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não foi possível salvar o modelo."));
      return false;
    }
  }

  return { templates, loading: pending, load: refresh, create, patch, remove };
}
