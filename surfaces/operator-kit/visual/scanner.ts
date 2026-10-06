import type { Page } from "@playwright/test";

export type OperatorGeometryFindingKind =
  | "horizontal-overflow"
  | "outside-viewport"
  | "covered-by-chrome"
  | "text-clipping"
  | "focus-clipping"
  | "overlay-layer"
  | "touch-target"
  | "target-spacing"
  | "safe-area"
  | "skeleton-shape"
  | "pane-constraints";

export interface OperatorGeometryFinding {
  kind: OperatorGeometryFindingKind;
  selector: string;
  message: string;
  rect?: { x: number; y: number; width: number; height: number };
}

export interface OperatorGeometryOptions {
  touch?: boolean;
  minTouchTarget?: number;
  minTargetSpacing?: number;
}

export async function scanOperatorGeometry(
  page: Page,
  options: OperatorGeometryOptions = {},
): Promise<OperatorGeometryFinding[]> {
  return page.evaluate((input) => {
    const findings: OperatorGeometryFinding[] = [];
    const minTarget = input.minTouchTarget ?? (innerWidth >= 600 ? 48 : 44);
    const minSpacing = input.minTargetSpacing ?? 8;
    const interactiveSelector = [
      "button",
      "a[href]",
      "input:not([type='hidden'])",
      "select",
      "textarea",
      "[role='button']",
      "[role='link']",
      "[role='checkbox']",
      "[role='radio']",
      "[role='switch']",
      "[tabindex]:not([tabindex='-1'])",
    ].join(",");

    function visible(element: Element): element is HTMLElement {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity) > 0 && rect.width > 0 && rect.height > 0;
    }
    function selector(element: Element): string {
      const marked = element.closest<HTMLElement>("[data-operator-audit-id]");
      if ((element as HTMLElement).id) return `#${CSS.escape((element as HTMLElement).id)}`;
      const role = element.getAttribute("role");
      const local = `${element.tagName.toLowerCase()}${role ? `[role="${role}"]` : ""}`;
      if (marked) {
        const root = `[data-operator-audit-id="${marked.dataset.operatorAuditId}"]`;
        return marked === element ? root : `${root} ${local}`;
      }
      return local;
    }
    function rectOf(element: Element) {
      const rect = element.getBoundingClientRect();
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
    }
    function add(kind: OperatorGeometryFindingKind, element: Element, message: string) {
      if (element.closest("[data-operator-audit-ignore]")) return;
      findings.push({ kind, selector: selector(element), message, rect: rectOf(element) });
    }
    function clippedByAncestor(element: Element): boolean {
      // O handle oficial vive no root com overflow hidden, mas o wrapper põe o
      // outline para dentro. O envelope de foco não ultrapassa o recorte.
      if (element.matches('[data-slot="handle"][role="separator"]')) return false;
      const rect = element.getBoundingClientRect();
      let parent = element.parentElement;
      let scrollableX = false;
      let scrollableY = false;
      while (parent && parent !== document.body) {
        const style = getComputedStyle(parent);
        const overflowX = style.overflowX || style.overflow;
        const overflowY = style.overflowY || style.overflow;
        scrollableX ||= /(auto|scroll)/.test(overflowX);
        scrollableY ||= /(auto|scroll)/.test(overflowY);
        const frame = parent.getBoundingClientRect();
        const clippedX = !scrollableX && /(hidden|clip)/.test(overflowX) && (rect.left - 3 < frame.left - 1 || rect.right + 3 > frame.right + 1);
        const clippedY = !scrollableY && /(hidden|clip)/.test(overflowY) && (rect.top - 3 < frame.top - 1 || rect.bottom + 3 > frame.bottom + 1);
        if (clippedX || clippedY) return true;
        parent = parent.parentElement;
      }
      return false;
    }
    function distance(a: DOMRect, b: DOMRect): number {
      const dx = Math.max(a.left - b.right, b.left - a.right, 0);
      const dy = Math.max(a.top - b.bottom, b.top - a.bottom, 0);
      return Math.hypot(dx, dy);
    }

    const root = document.documentElement;
    if (root.scrollWidth > root.clientWidth + 1) {
      add("horizontal-overflow", root, `Documento mede ${root.scrollWidth}px para viewport de ${root.clientWidth}px.`);
    }
    for (const pane of document.querySelectorAll<HTMLElement>("[data-operator-pane]")) {
      const style = getComputedStyle(pane);
      const hasLimits = pane.hasAttribute("data-pane-min") || pane.hasAttribute("data-pane-max");
      if (style.minWidth !== "0px" || !hasLimits) add("pane-constraints", pane, "Pane precisa de min-width: 0 e limites declarados.");
      if (pane.dataset.overflow !== "horizontal" && pane.scrollWidth > pane.clientWidth + 1) {
        add("horizontal-overflow", pane, `Pane mede ${pane.scrollWidth}px para caixa de ${pane.clientWidth}px.`);
      }
    }

    const interactives = [...document.querySelectorAll<HTMLElement>(interactiveSelector)].filter(visible);
    const chrome = [...document.querySelectorAll<HTMLElement>("[data-focus-obstruction], [data-operator-fixed-chrome]")].filter(visible);
    for (const element of interactives) {
      const envelope = element.closest<HTMLElement>("[data-touch-envelope]") ?? element;
      const rect = envelope.getBoundingClientRect();
      const fixedContext = element.closest("[data-operator-fixed-chrome], [role='dialog'], [aria-modal='true']");
      const outsideHorizontal = !element.closest('[data-operator-overflow="horizontal"]')
        && (rect.left < -1 || rect.right > innerWidth + 1);
      const outsideFixedVertical = fixedContext && (rect.top < -1 || rect.bottom > innerHeight + 1);
      if (outsideHorizontal || outsideFixedVertical) {
        const name = element.getAttribute("aria-label") || element.textContent?.trim().replace(/\s+/g, " ").slice(0, 60) || "sem nome";
        add(
          "outside-viewport",
          element,
          `Controle “${name}” fica fora do viewport (${Math.round(rect.x)},${Math.round(rect.y)} ${Math.round(rect.width)}×${Math.round(rect.height)} em ${innerWidth}×${innerHeight}).`,
        );
      }
      const resizeHandle = element.matches('[data-slot="handle"][role="separator"]') || /(col|row|ew|ns)-resize/.test(getComputedStyle(element).cursor);
      if (input.touch && !resizeHandle && !element.closest("[data-touch-target-exempt]") && (rect.width < minTarget || rect.height < minTarget)) {
        add("touch-target", envelope, `Envelope operacional ${Math.round(rect.width)}×${Math.round(rect.height)}; mínimo ${minTarget}×${minTarget}.`);
      }
      if (clippedByAncestor(element)) add("focus-clipping", element, "Controle ou seu foco é cortado por ancestral com overflow.");
      const centerX = Math.min(innerWidth - 1, Math.max(0, rect.left + rect.width / 2));
      const centerY = Math.min(innerHeight - 1, Math.max(0, rect.top + rect.height / 2));
      const top = document.elementFromPoint(centerX, centerY);
      if (top && !element.contains(top) && !top.contains(element)) {
        const obstruction = chrome.find((candidate) => candidate === top || candidate.contains(top));
        if (obstruction && !obstruction.contains(element)) add("covered-by-chrome", element, "Controle está coberto pelo chrome fixo.");
      }
    }

    const byParent = new Map<Element, HTMLElement[]>();
    for (const element of interactives) {
      const parent = element.closest("[data-action-group]");
      if (!parent) continue;
      byParent.set(parent, [...(byParent.get(parent) ?? []), element]);
    }
    for (const elements of byParent.values()) {
      for (let index = 0; index < elements.length; index += 1) {
        for (let sibling = index + 1; sibling < elements.length; sibling += 1) {
          const firstRect = elements[index]!.getBoundingClientRect();
          const secondRect = elements[sibling]!.getBoundingClientRect();
          const gap = distance(firstRect, secondRect);
          if (gap + 0.5 < minSpacing) {
            add(
              "target-spacing",
              elements[sibling]!,
              `Ações independentes têm ${gap.toFixed(1)}px de distância; mínimo ${minSpacing}px `
                + `(A ${Math.round(firstRect.x)},${Math.round(firstRect.y)} ${Math.round(firstRect.width)}×${Math.round(firstRect.height)}; `
                + `B ${Math.round(secondRect.x)},${Math.round(secondRect.y)} ${Math.round(secondRect.width)}×${Math.round(secondRect.height)}).`,
            );
          }
        }
      }
    }

    for (const element of document.querySelectorAll<HTMLElement>("[data-operator-text], p, h1, h2, h3, label")) {
      if (!visible(element) || element.closest("[data-clipping-allowed]")) continue;
      const style = getComputedStyle(element);
      // Fontes podem arredondar 2–4 px acima do line box, especialmente com
      // zoom CSS. Overflow horizontal é exato; clipping vertical exige folga
      // maior para não confundir métrica tipográfica com corte visível.
      const clipped = element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 4;
      if (clipped && /(hidden|clip)/.test(`${style.overflow}${style.overflowX}${style.overflowY}`) && !element.title && !element.getAttribute("aria-label")) {
        add("text-clipping", element, "Texto cortado sem expansão, title ou nome acessível completo.");
      }
    }

    for (const overlay of document.querySelectorAll<HTMLElement>("[role='dialog'], [role='alertdialog'], [role='menu'], [role='listbox']")) {
      if (!visible(overlay)) continue;
      const rect = overlay.getBoundingClientRect();
      const top = document.elementFromPoint(Math.max(0, rect.left + rect.width / 2), Math.max(0, rect.top + rect.height / 2));
      if (top && !overlay.contains(top)) add("overlay-layer", overlay, "Overlay não está na camada superior no próprio centro.");
    }

    for (const skeleton of document.querySelectorAll<HTMLElement>("[data-skeleton-for]")) {
      const target = document.querySelector<HTMLElement>(skeleton.dataset.skeletonFor || "");
      if (!target) continue;
      const a = skeleton.getBoundingClientRect();
      const b = target.getBoundingClientRect();
      if (Math.abs(a.width - b.width) > 2 || Math.abs(a.height - b.height) > 2) {
        add("skeleton-shape", skeleton, "Skeleton não preserva a forma final.");
      }
    }

    const safeBottom = Number.parseFloat(getComputedStyle(root).getPropertyValue("--op-safe-bottom")) || 0;
    for (const bar of chrome.filter((element) => getComputedStyle(element).position === "fixed" && element.getBoundingClientRect().bottom >= innerHeight - 1)) {
      const content = document.querySelector<HTMLElement>("[data-operator-scroll-content]");
      if (content && Number.parseFloat(getComputedStyle(content).paddingBottom) + 1 < bar.getBoundingClientRect().height + safeBottom) {
        add("safe-area", content, "Conteúdo não reserva a barra fixa e a área segura inferior.");
      }
    }
    return findings;
  }, options);
}
