// Regras de campanha — listagem, liga/desliga e o CRUD leve do formulário.
//
// As "options" (gatilhos, plataformas, modelos, variáveis) vêm do backend em vez
// de hardcoded na tela: gatilho novo no domínio aparece no formulário sem deploy
// de front, e a lista nunca diverge da que o serviço aceita.
import type { Campaign, ChosenAudience, OptionsResponse, RulesResponse } from "~/types/campaign";

export function useCampaigns() {
  const { data, refresh, pending, error } = useFetch<RulesResponse>(
    "/api/v1/backstage/marketing/rules/",
    { key: "marketing-list", server: true },
  );
  const { data: optionsData } = useFetch<OptionsResponse>(
    "/api/v1/backstage/marketing/options/",
    { key: "marketing-options", server: true },
  );

  const rules = computed<Campaign[]>(() => data.value?.rules ?? []);
  const options = computed(() => optionsData.value?.options);
  const templates = computed(() => options.value?.templates ?? []);
  const triggers = computed(() => options.value?.triggers ?? []);
  const platforms = computed(() => options.value?.platforms ?? []);
  const variables = computed(() => options.value?.variables ?? []);
  const customerGroups = computed(() => options.value?.customer_groups ?? []);
  const rfmSegments = computed(() => options.value?.rfm_segments ?? []);
  // Só ofertas que montam sacola chegam aqui — o servidor já filtrou.
  const offers = computed(() => options.value?.offers ?? []);

  /** Rótulo por ref de plataforma — o que `platformsSummary` espera. */
  const platformLabels = computed<Record<string, string>>(() =>
    Object.fromEntries(platforms.value.map((choice) => [choice.value, choice.label])),
  );

  async function toggle(rule: Campaign): Promise<void> {
    await patch(rule.pk, { is_active: !rule.is_active });
  }

  async function patch(pk: number, body: Partial<Campaign> & Record<string, unknown>) {
    try {
      await $fetch(`/api/v1/backstage/marketing/rules/${pk}/`, { method: "PATCH", body });
      useSonner.success("Regra salva.");
      await refresh();
      return true;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não foi possível salvar a regra."));
      return false;
    }
  }

  /** Disparar uma campanha agora, opcionalmente para um público escolhido.
   *
   * O público vale só para ESTE disparo — a campanha salva mantém o dela. Por isso a
   * tela não precisa avisar "isto vai alterar a regra": não vai.
   */
  async function fire(pk: number, request: { body?: string; audience?: ChosenAudience } = {}) {
    try {
      const audience = request.audience;
      const payload: Record<string, unknown> = {};
      if (audience && Object.keys(audience).length) payload.audience_rules = audience;
      if (request.body) payload.body = request.body;
      const res = await $fetch<{ announcement?: { audience_total?: number; status?: string } }>(
        `/api/v1/backstage/marketing/rules/${pk}/fire/`,
        { method: "POST", body: payload },
      );

      // Alcance ZERO não pode passar em silêncio. Quem escolheu um grupo e não
      // alcançou ninguém precisa saber que a razão é consentimento, senão vai
      // concluir que a ferramenta está quebrada e mexer na regra errada.
      const reached = res?.announcement?.audience_total ?? 0;
      // Quem escreveu o texto publica direto, então a frase não pode mandar "conferir no
      // painel" — o anúncio já saiu. Quem decide qual caso é foi o servidor.
      const wentOut = ["published", "publishing", "approved"].includes(
        res?.announcement?.status ?? "",
      );
      if (reached > 0) {
        const people = `${reached} ${reached === 1 ? "pessoa" : "pessoas"}`;
        useSonner.success(
          wentOut
            ? `Anúncio publicado para ${people}.`
            : `Anúncio criado para ${people}. Confira no painel antes de publicar.`,
        );
      } else {
        // O verbo segue o mesmo critério do caso com alcance: dizer "criado" quando o
        // anúncio já saiu seria a mesma imprecisão, só num aviso em vez de num sucesso.
        useSonner.warning(
          `Anúncio ${wentOut ? "publicado" : "criado"}, mas ninguém no público escolhido ` +
            "deu consentimento para receber no WhatsApp. Ele não vai alcançar pessoas.",
        );
      }
      await refresh();
      return true;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não foi possível disparar a campanha."));
      return false;
    }
  }

  async function create(body: Record<string, unknown>) {
    try {
      await $fetch("/api/v1/backstage/marketing/rules/", { method: "POST", body });
      useSonner.success("Regra criada.");
      await refresh();
      return true;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não foi possível criar a regra."));
      return false;
    }
  }

  return {
    rules,
    options,
    templates,
    triggers,
    platforms,
    platformLabels,
    variables,
    customerGroups,
    rfmSegments,
    offers,
    loading: pending,
    error,
    refresh,
    toggle,
    patch,
    create,
    fire,
  };
}
