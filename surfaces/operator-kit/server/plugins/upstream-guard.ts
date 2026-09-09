import {
  assertProductionDjangoConfiguration,
  isExplicitTestRuntime,
} from "../utils/djangoBaseUrl";

// Config de build não substitui secret/config de runtime. Apps que ativam o gate
// abortam o boot se ambiente ou upstream HTTPS não forem fornecidos. O opt-in evita
// mudar o release contract dos demais consumidores do layer no mesmo deploy; cada
// superfície pode migrar com seu próprio WP. Test/e2e é o único bypass do app opt-in.
export default defineNitroPlugin(() => {
  const config = useRuntimeConfig();
  if (config.operatorUpstreamFailFast === true && !import.meta.dev && !isExplicitTestRuntime()) {
    assertProductionDjangoConfiguration();
  }
});
