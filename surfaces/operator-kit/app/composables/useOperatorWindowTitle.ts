import {
  OPERATOR_APP_NAME_STATE,
  operatorAppName,
  windowTitle,
  type OperatorAppName,
} from "../presentation/windowTitle";

interface OperatorPwaTitleConfig {
  manifest?: { label?: string };
}

/**
 * Nome do app de operador já resolvido: `{ prefix: "Nelson", label: "PDV", name:
 * "Nelson · PDV" }`.
 *
 * Uma fonte só para os dois lados do nome: o rótulo que o app declara em
 * `definePwaCapability(...)` (`manifest.label`) e a casa (`Shop.short_name`), que o
 * plugin `operatorAppName` do kit lê do Django no SSR e deixa no `useState`. É o MESMO
 * nome que o `/manifest.webmanifest` serve. `fallbackLabel` cobre o app sem a
 * capability (ou o harness de teste sem plugin); não é um segundo nome.
 */
export function useOperatorAppName(fallbackLabel = ""): OperatorAppName {
  const resolved = useState<OperatorAppName | null>(OPERATOR_APP_NAME_STATE, () => null).value;
  if (resolved?.name) return resolved;
  const config = (useRuntimeConfig().public?.operatorPwa || {}) as OperatorPwaTitleConfig;
  return operatorAppName("", config.manifest?.label || fallbackLabel);
}

/**
 * Instala o `titleTemplate` do app de operador: `"<Casa> · <App> · <Página>"`.
 *
 * O plugin do kit já instala o mesmo template para toda renderização (inclusive a
 * página de erro padrão do Nuxt); chamar aqui, no `app.vue` e no `error.vue`, declara
 * a intenção no shell e cobre o app sem a capability. As páginas passam só o próprio
 * título (`useHead({ title: "Filipetas" })`) — a regra em `presentation/windowTitle.ts`
 * monta o resto.
 */
export function useOperatorWindowTitle(fallbackLabel = "") {
  const app = useOperatorAppName(fallbackLabel);
  useHead({
    titleTemplate: (pageTitle?: string | null) => windowTitle(app, pageTitle),
  });
  return { appName: app.name, label: app.label, prefix: app.prefix };
}
