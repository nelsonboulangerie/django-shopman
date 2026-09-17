import { onBeforeUnmount, onMounted, readonly, ref } from "vue";

import { crossAppLinkAttrs, type CrossAppLinkAttrs } from "../presentation/appLaunch";
import { isInstalledDisplay } from "../utils/displayMode";

/**
 * Atributos de link de um app de operador para outro — ver `presentation/appLaunch.ts`
 * para POR QUE eles mudam quando o app está instalado.
 *
 * O modo de exibição muda em runtime (o operador instala o app com a janela aberta, ou
 * entra/sai de tela cheia), então a leitura é reativa: um `<a>` já renderizado passa a
 * abrir na janela certa sem recarregar a página.
 */
export function useOperatorAppLink() {
  const installed = ref(false);
  let cleanup: (() => void) | null = null;

  function attrsFor(href: string): CrossAppLinkAttrs {
    return crossAppLinkAttrs({
      installed: installed.value,
      href,
      currentOrigin: import.meta.client ? window.location.origin : "",
    });
  }

  onMounted(() => {
    installed.value = isInstalledDisplay();
    const queries = ["standalone", "fullscreen", "minimal-ui"]
      .map((mode) => window.matchMedia?.(`(display-mode: ${mode})`))
      .filter(Boolean) as MediaQueryList[];
    const sync = () => { installed.value = isInstalledDisplay(); };
    for (const query of queries) query.addEventListener?.("change", sync);
    cleanup = () => { for (const query of queries) query.removeEventListener?.("change", sync); };
  });

  onBeforeUnmount(() => cleanup?.());

  return { installed: readonly(installed), attrsFor };
}
