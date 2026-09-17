import {
  OPERATOR_APP_NAME_ROUTE,
  OPERATOR_APP_NAME_STATE,
  operatorAppName,
  windowTitle,
  type OperatorAppName,
} from "../../app/presentation/windowTitle";

interface OperatorPwaLabelConfig {
  manifest?: { label?: string };
}

function sameApp(value: unknown, label: string): OperatorAppName | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Partial<OperatorAppName>;
  if (typeof candidate.prefix !== "string") return null;
  return operatorAppName(candidate.prefix, label);
}

/**
 * Resolve o nome do app (`"<casa> · <App>"`) ANTES da primeira renderização e instala
 * o `titleTemplate` da janela.
 *
 * No servidor pergunta à rota Nitro do próprio app (chamada local, sem rede), que lê o
 * `Shop.short_name` do Django com cache; o resultado viaja no payload, então o cliente
 * hidrata com o mesmo nome sem refazer a pergunta. O template vive aqui, no plugin, e
 * não só no `app.vue`, porque o Nuxt renderiza a página de erro NO LUGAR do `app.vue`
 * — a padrão do Nuxt escreve "404 - Page not found | Nuxt" e, sem template, a janela
 * perdia o nome e ganhava o hífen.
 */
export default defineNuxtPlugin({
  name: "operator-app-name",
  async setup() {
    const config = (useRuntimeConfig().public.operatorPwa || {}) as OperatorPwaLabelConfig;
    const label = config.manifest?.label || "";
    const state = useState<OperatorAppName | null>(OPERATOR_APP_NAME_STATE, () => null);

    if (!state.value) {
      try {
        state.value = sameApp(await useRequestFetch()(OPERATOR_APP_NAME_ROUTE), label);
      } catch {
        // silêncio-deliberado: sem a rota (rede do cliente caiu) a janela mostra só o
        // rótulo; o manifesto e a próxima navegação SSR trazem a casa de volta.
      }
      state.value ||= operatorAppName("", label);
    }

    useHead({
      titleTemplate: (pageTitle?: string | null) => windowTitle(state.value || operatorAppName("", label), pageTitle),
      meta: [{ name: "apple-mobile-web-app-title", content: () => state.value?.name || label }],
    });
  },
});
