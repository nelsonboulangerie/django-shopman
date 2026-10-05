import type { Directive } from "vue";

const names: Record<string, string> = {
  day: "Dia",
  month: "Mês",
  year: "Ano",
  hour: "Hora",
  minute: "Minuto",
  second: "Segundo",
  dayPeriod: "Período do dia",
};

const observers = new WeakMap<HTMLElement, MutationObserver>();

function localize(root: HTMLElement) {
  for (const segment of root.querySelectorAll<HTMLElement>("[data-slot='segment'][role='spinbutton']")) {
    const part = segment.dataset.segment ?? "";
    const name = names[part];
    if (!name) continue;
    if (segment.getAttribute("aria-label") !== name) segment.setAttribute("aria-label", name);
    const value = segment.hasAttribute("data-placeholder")
      ? "Vazio"
      : segment.textContent?.trim() || "Vazio";
    if (segment.getAttribute("aria-valuetext") !== value) segment.setAttribute("aria-valuetext", value);
  }
}

/** Adaptador de a11y para os segmentos gerados internamente pelo Nuxt UI/Reka.
 *  A versão atual publica nomes e valores vazios em inglês sem prop de tradução.
 */
export const vLocalizedSegments: Directive<HTMLElement> = {
  mounted(root) {
    localize(root);
    const observer = new MutationObserver(() => localize(root));
    observer.observe(root, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["aria-label", "aria-valuetext", "data-placeholder"],
    });
    observers.set(root, observer);
  },
  updated: localize,
  unmounted(root) {
    observers.get(root)?.disconnect();
    observers.delete(root);
  },
};
