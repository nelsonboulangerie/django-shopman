// Regras de campanha — listagem, liga/desliga e o CRUD leve do formulário.
//
// As "options" (gatilhos, plataformas, modelos, variáveis) vêm do backend em vez
// de hardcoded na tela: gatilho novo no domínio aparece no formulário sem deploy
// de front, e a lista nunca diverge da que o serviço aceita.
import type {
  Campaign,
  OptionsResponse,
  RulesResponse,
} from "~/types/campaign";

export function useCampaigns() {
  const { data, refresh, pending, error } = useFetch<RulesResponse>(
    "/api/v1/backstage/marketing/rules/",
    {
      key: "marketing-list",
      server: true,
      onResponseError: operatorSessionOnError,
    },
  );
  const { data: optionsData } = useFetch<OptionsResponse>(
    "/api/v1/backstage/marketing/options/",
    {
      key: "marketing-options",
      server: true,
      onResponseError: operatorSessionOnError,
    },
  );

  const rules = computed<Campaign[]>(() => data.value?.rules ?? []);
  const actions = computed(() => data.value?.actions ?? []);
  const options = computed(() => optionsData.value?.options);
  const templates = computed(() => options.value?.templates ?? []);
  const triggers = computed(() => options.value?.triggers ?? []);
  const platforms = computed(() => options.value?.platforms ?? []);
  const variables = computed(() => options.value?.variables ?? []);
  const priceTiers = computed(() => options.value?.price_tiers ?? []);
  const tags = computed(() => options.value?.tags ?? []);
  const rfmSegments = computed(() => options.value?.rfm_segments ?? []);
  // Só ofertas que montam sacola chegam aqui — o servidor já filtrou.
  const offers = computed(() => options.value?.offers ?? []);
  const shopTimezone = computed(() => options.value?.shop_timezone ?? "UTC");

  /** Rótulo por ref de plataforma — o que `platformsSummary` espera. */
  const platformLabels = computed<Record<string, string>>(() =>
    Object.fromEntries(
      platforms.value.map((choice) => [choice.value, choice.label]),
    ),
  );

  async function toggle(rule: Campaign): Promise<void> {
    await patch(rule.pk, { is_active: !rule.is_active });
  }

  async function patch(
    pk: number,
    body: Partial<Campaign> & Record<string, unknown>,
  ) {
    const current = rules.value.find((rule) => rule.pk === pk);
    const payload = current?.updated_at
      ? { ...body, base_updated_at: current.updated_at }
      : body;
    try {
      await $fetch(`/api/v1/backstage/marketing/rules/${pk}/`, {
        method: "PATCH",
        body: payload,
      });
      useSonner.success("Regra salva.");
      await refresh();
      return true;
    } catch (err) {
      flagMarketingSessionError(err);
      if (httpError(err).status === 409) {
        useSonner.warning(
          "A campanha mudou em outra sessão. Compare as versões no formulário.",
        );
        await refresh();
      } else {
        useSonner.error(
          httpErrorMessage(err, "Não foi possível salvar a regra."),
        );
      }
      return false;
    }
  }

  async function create(body: Record<string, unknown>) {
    try {
      await $fetch("/api/v1/backstage/marketing/rules/", {
        method: "POST",
        body,
      });
      useSonner.success("Regra criada.");
      await refresh();
      return true;
    } catch (err) {
      flagMarketingSessionError(err);
      useSonner.error(httpErrorMessage(err, "Não foi possível criar a regra."));
      return false;
    }
  }

  return {
    rules,
    actions,
    options,
    templates,
    triggers,
    platforms,
    platformLabels,
    variables,
    priceTiers,
    tags,
    rfmSegments,
    offers,
    shopTimezone,
    loading: pending,
    error,
    refresh,
    toggle,
    patch,
    create,
  };
}
