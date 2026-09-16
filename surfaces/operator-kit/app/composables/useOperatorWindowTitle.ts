import { windowTitle } from "../presentation/windowTitle";

interface OperatorPwaTitleConfig {
  manifest?: { name?: string };
}

/**
 * Instala o `titleTemplate` do app de operador: `"<App> · <Página>"`.
 *
 * O nome do app é UMA fonte só — o `manifest.name` que o app declara em
 * `definePwaCapability(...)` e que o módulo publica em
 * `runtimeConfig.public.operatorPwa` (o mesmo que o `/manifest.webmanifest` serve).
 * `fallbackName` cobre o app sem a capability (ou o harness de teste sem
 * runtimeConfig); não é um segundo nome.
 *
 * Chamar UMA vez, no `app.vue` (e no `error.vue`, que o Nuxt renderiza NO LUGAR
 * do `app.vue`). As páginas passam só o próprio título
 * (`useHead({ title: "Filipetas" })`) — a regra em `presentation/windowTitle.ts`
 * monta o resto.
 */
export function useOperatorWindowTitle(fallbackName = "") {
  const config = (useRuntimeConfig().public.operatorPwa || {}) as OperatorPwaTitleConfig;
  const appName = (config.manifest?.name || fallbackName).trim();
  useHead({
    titleTemplate: (pageTitle?: string | null) => windowTitle(appName, pageTitle),
  });
  return { appName };
}
