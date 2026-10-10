import type { Page } from "@playwright/test";

export type OperatorGeometryFindingKind =
  | "horizontal-overflow"
  | "outside-viewport"
  | "covered-by-chrome"
  | "text-clipping"
  | "control-text-overflow"
  | "control-overlap"
  | "fixed-text"
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
  /** Só estes tipos de achado (as matrizes que ainda não passam a varredura inteira
   *  ligam só a trava do rótulo, `OPERATOR_LABEL_FINDINGS`). */
  only?: readonly OperatorGeometryFindingKind[];
  touch?: boolean;
  minTouchTarget?: number;
  minTargetSpacing?: number;
}

/** A trava do rótulo que cabe (dono, 10/10/2026): texto de controle que vaza ou corta,
 *  controles sobrepostos e texto de peça fixa que não reserva as linhas. */
export const OPERATOR_LABEL_FINDINGS: readonly OperatorGeometryFindingKind[] = [
  "control-text-overflow",
  "control-overlap",
  "fixed-text",
];

export async function scanOperatorGeometry(
  page: Page,
  options: OperatorGeometryOptions = {},
): Promise<OperatorGeometryFinding[]> {
  const findings = await page.evaluate((input) => {
    const findings: OperatorGeometryFinding[] = [];
    // Alvo de toque = altura `md` (32 px, o `--spacing-control`), decisão do dono de
    // 09/10/2026: campos e botões em 32 px em todos os apps, inclusive no toque.
    // Fica acima do piso WCAG 2.2 AA (2.5.8, 24 px).
    const minTarget = input.minTouchTarget ?? 32;
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
      return (
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        Number(style.opacity) > 0 &&
        rect.width > 0 &&
        rect.height > 0
      );
    }
    function selector(element: Element): string {
      const marked = element.closest<HTMLElement>("[data-operator-audit-id]");
      if ((element as HTMLElement).id)
        return `#${CSS.escape((element as HTMLElement).id)}`;
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
    function add(
      kind: OperatorGeometryFindingKind,
      element: Element,
      message: string,
    ) {
      if (element.closest("[data-operator-audit-ignore]")) return;
      findings.push({
        kind,
        selector: selector(element),
        message,
        rect: rectOf(element),
      });
    }
    function clippedByAncestor(element: Element): boolean {
      // O handle oficial vive no root com overflow hidden, mas o wrapper põe o
      // outline para dentro. O envelope de foco não ultrapassa o recorte.
      if (element.matches('[data-slot="handle"][role="separator"]'))
        return false;
      // Barras compactas usam deliberadamente o anel interno: ele permanece
      // inteiro mesmo quando o item precisa recortar label/ícone nas bordas. O
      // contorno puxado para dentro (`-outline-offset-*`, o da linha ativa da
      // tabela e do item da barra inferior) vale o mesmo.
      if (
        [...element.classList].some(
          (name) => name.includes("ring-inset") || name.includes("-outline-offset-"),
        )
      )
        return false;
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
        const clippedX =
          !scrollableX &&
          /(hidden|clip)/.test(overflowX) &&
          (rect.left - 3 < frame.left - 1 || rect.right + 3 > frame.right + 1);
        const clippedY =
          !scrollableY &&
          /(hidden|clip)/.test(overflowY) &&
          (rect.top - 3 < frame.top - 1 || rect.bottom + 3 > frame.bottom + 1);
        if (clippedX || clippedY) return true;
        parent = parent.parentElement;
      }
      return false;
    }
    function pointVisibleThroughAncestors(
      element: Element,
      x: number,
      y: number,
    ): boolean {
      let parent = element.parentElement;
      while (parent && parent !== document.body) {
        const style = getComputedStyle(parent);
        const overflowX = style.overflowX || style.overflow;
        const overflowY = style.overflowY || style.overflow;
        const frame = parent.getBoundingClientRect();
        if (/(auto|scroll|hidden|clip)/.test(overflowX) && (x < frame.left || x > frame.right))
          return false;
        if (/(auto|scroll|hidden|clip)/.test(overflowY) && (y < frame.top || y > frame.bottom))
          return false;
        parent = parent.parentElement;
      }
      return true;
    }
    function distance(a: DOMRect, b: DOMRect): number {
      const dx = Math.max(a.left - b.right, b.left - a.right, 0);
      const dy = Math.max(a.top - b.bottom, b.top - a.bottom, 0);
      return Math.hypot(dx, dy);
    }

    const root = document.documentElement;
    if (root.scrollWidth > root.clientWidth + 1) {
      add(
        "horizontal-overflow",
        root,
        `Documento mede ${root.scrollWidth}px para viewport de ${root.clientWidth}px.`,
      );
    }
    for (const pane of document.querySelectorAll<HTMLElement>(
      "[data-operator-pane]",
    )) {
      const style = getComputedStyle(pane);
      const hasLimits =
        pane.hasAttribute("data-pane-min") ||
        pane.hasAttribute("data-pane-max");
      if (style.minWidth !== "0px" || !hasLimits)
        add(
          "pane-constraints",
          pane,
          "Pane precisa de min-width: 0 e limites declarados.",
        );
      if (
        pane.dataset.overflow !== "horizontal" &&
        pane.scrollWidth > pane.clientWidth + 1
      ) {
        add(
          "horizontal-overflow",
          pane,
          `Pane mede ${pane.scrollWidth}px para caixa de ${pane.clientWidth}px.`,
        );
      }
    }

    const interactives = [
      ...document.querySelectorAll<HTMLElement>(interactiveSelector),
    ].filter(visible);
    const chrome = [
      ...document.querySelectorAll<HTMLElement>(
        "[data-focus-obstruction], [data-operator-fixed-chrome]",
      ),
    ].filter(visible);
    // Faixa que rola de lado (abas, filtros rápidos): o que está fora da tela se alcança
    // rolando a faixa, não é controle perdido.
    const inHorizontalScroller = (element: HTMLElement) => {
      for (let node = element.parentElement; node; node = node.parentElement) {
        if (node === document.body || node === document.documentElement) return false;
        const overflowX = getComputedStyle(node).overflowX;
        if ((overflowX === "auto" || overflowX === "scroll") && node.scrollWidth > node.clientWidth + 1) {
          return true;
        }
      }
      return false;
    };
    for (const element of interactives) {
      const envelope =
        element.closest<HTMLElement>("[data-touch-envelope]") ?? element;
      const rect = envelope.getBoundingClientRect();
      const fixedContext = element.closest(
        "[data-operator-fixed-chrome], [role='dialog'], [aria-modal='true']",
      );
      const outsideHorizontal =
        !element.closest('[data-operator-overflow="horizontal"]') &&
        (rect.left < -1 || rect.right > innerWidth + 1) &&
        !inHorizontalScroller(element);
      const outsideFixedVertical =
        fixedContext && (rect.top < -1 || rect.bottom > innerHeight + 1);
      if (outsideHorizontal || outsideFixedVertical) {
        const name =
          element.getAttribute("aria-label") ||
          element.textContent?.trim().replace(/\s+/g, " ").slice(0, 60) ||
          "sem nome";
        add(
          "outside-viewport",
          element,
          `Controle “${name}” fica fora do viewport (${Math.round(rect.x)},${Math.round(rect.y)} ${Math.round(rect.width)}×${Math.round(rect.height)} em ${innerWidth}×${innerHeight}).`,
        );
      }
      const resizeHandle =
        element.matches('[data-slot="handle"][role="separator"]') ||
        /(col|row|ew|ns)-resize/.test(getComputedStyle(element).cursor);
      const hitArea = getComputedStyle(element, "::after");
      const hasExtendedTarget =
        hitArea.content !== "none" &&
        hitArea.position === "absolute" &&
        getComputedStyle(element).overflow !== "hidden";
      const targetWidth = hasExtendedTarget
        ? Math.max(rect.width, Number.parseFloat(hitArea.width) || 0)
        : rect.width;
      const targetHeight = hasExtendedTarget
        ? Math.max(rect.height, Number.parseFloat(hitArea.height) || 0)
        : rect.height;
      if (
        input.touch &&
        !resizeHandle &&
        !element.closest("[data-touch-target-exempt]") &&
        // Meio pixel de folga: `2rem` sai 31,98 px no layout fracionário do
        // navegador, e um campo de 32 px não é alvo pequeno.
        (targetWidth < minTarget - 0.5 || targetHeight < minTarget - 0.5)
      ) {
        add(
          "touch-target",
          envelope,
          `Envelope operacional ${Math.round(rect.width)}×${Math.round(rect.height)}; mínimo ${minTarget}×${minTarget}.`,
        );
      }
      if (clippedByAncestor(element))
        add(
          "focus-clipping",
          element,
          `Controle “${
            element.getAttribute("aria-label") ||
            element.textContent?.trim().replace(/\s+/g, " ").slice(0, 60) ||
            "sem nome"
          }” ou seu foco é cortado por ancestral com overflow.`,
        );
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      // Um controle abaixo/acima da área visível pertence ao fluxo rolável; não
      // está "coberto" pelo chrome só porque o ponto foi artificialmente preso à
      // borda do viewport. O teste de obstrução só faz sentido quando o centro do
      // próprio controle está realmente visível.
      const centerVisible =
        centerX >= 0 &&
        centerX < innerWidth &&
        centerY >= 0 &&
        centerY < innerHeight &&
        pointVisibleThroughAncestors(element, centerX, centerY);
      const top = centerVisible ? document.elementFromPoint(centerX, centerY) : null;
      if (top && !element.contains(top) && !top.contains(element)) {
        // Controles que pertencem ao próprio chrome fixo (por exemplo, itens da
        // navegação inferior) não podem ser diagnosticados como cobertos por
        // esse mesmo chrome. Portais e wrappers internos do Nuxt UI podem fazer
        // elementFromPoint devolver um irmão visual em vez do botão original.
        const ownChrome = element.closest(
          "[data-focus-obstruction], [data-operator-fixed-chrome]",
        );
        const obstruction = chrome.find(
          (candidate) => candidate === top || candidate.contains(top),
        );
        if (obstruction && !ownChrome && !obstruction.contains(element))
          add(
            "covered-by-chrome",
            element,
            `Controle “${
              element.getAttribute("aria-label") ||
              element.textContent?.trim().replace(/\s+/g, " ").slice(0, 60) ||
              "sem nome"
            }” está coberto pelo chrome fixo.`,
          );
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
              `Ações independentes têm ${gap.toFixed(1)}px de distância; mínimo ${minSpacing}px ` +
                `(A ${Math.round(firstRect.x)},${Math.round(firstRect.y)} ${Math.round(firstRect.width)}×${Math.round(firstRect.height)}; ` +
                `B ${Math.round(secondRect.x)},${Math.round(secondRect.y)} ${Math.round(secondRect.width)}×${Math.round(secondRect.height)}).`,
            );
          }
        }
      }
    }

    for (const element of document.querySelectorAll<HTMLElement>(
      "[data-operator-text], p, h1, h2, h3, label",
    )) {
      if (!visible(element) || element.closest("[data-clipping-allowed]"))
        continue;
      const style = getComputedStyle(element);
      // Fontes podem arredondar 2–4 px acima do line box, especialmente com
      // zoom CSS. Overflow horizontal é exato; clipping vertical exige folga
      // maior para não confundir métrica tipográfica com corte visível.
      const clipped =
        element.scrollWidth > element.clientWidth + 1 ||
        element.scrollHeight > element.clientHeight + 4;
      if (
        clipped &&
        /(hidden|clip)/.test(
          `${style.overflow}${style.overflowX}${style.overflowY}`,
        ) &&
        !element.title &&
        !element.getAttribute("aria-label")
      ) {
        add(
          "text-clipping",
          element,
          "Texto cortado sem expansão, title ou nome acessível completo.",
        );
      }
    }

    // O rótulo que cabe (dono, 10/10/2026). Dentro de um controle, nenhum texto passa
    // da caixa: nem vazando (o filho mais largo que o botão), nem cortado seco
    // (scrollWidth > clientWidth sem reticência declarada). Reticência só vale com o
    // texto completo na dica ou no nome acessível.
    // Só controle de verdade tem rótulo: o painel de aba, a faixa de abas que rola e a
    // região com `tabindex` são contêineres, e o que vive dentro deles é checado como
    // controle próprio.
    const labelControlSelector = [
      "button",
      "a[href]",
      "summary",
      "[role='button']",
      "[role='link']",
      "[role='tab']",
      "[role='radio']",
      "[role='checkbox']",
      "[role='switch']",
      "[role='menuitem']",
      "[role='option']",
    ].join(",");
    const labelControls = interactives.filter(
      (element) =>
        element.matches(labelControlSelector) &&
        !element.matches("[role='tablist'], [role='tabpanel'], [role='region'], [role='grid'], [role='listbox']"),
    );
    for (const control of labelControls) {
      if (control.closest("[data-clipping-allowed]")) continue;
      if (control.closest('[data-operator-overflow="horizontal"]') === control) continue;
      const box = control.getBoundingClientRect();
      const named =
        Boolean(control.title) || Boolean(control.getAttribute("aria-label"));
      const label =
        control.getAttribute("aria-label") ||
        control.textContent?.trim().replace(/\s+/g, " ").slice(0, 60) ||
        "sem nome";
      for (const node of [control, ...control.querySelectorAll<HTMLElement>("*")]) {
        if (node !== control && !visible(node)) continue;
        if (node.matches("svg, svg *, img, input, textarea, select")) continue;
        const style = getComputedStyle(node);
        if (style.position === "absolute" || style.position === "fixed") continue;
        const rect = node.getBoundingClientRect();
        if (
          node !== control &&
          rect.width > 0 &&
          (rect.right > box.right + 1 || rect.left < box.left - 1)
        ) {
          add(
            "control-text-overflow",
            control,
            `Texto do controle “${label}” passa da caixa (${Math.round(rect.width)}px num controle de ${Math.round(box.width)}px).`,
          );
          break;
        }
        const ownText = [...node.childNodes].some(
          (child) => child.nodeType === Node.TEXT_NODE && child.textContent?.trim(),
        ) || (node.dataset.opFitShort !== undefined);
        if (!ownText || node.clientWidth === 0) continue;
        if (node.scrollWidth > node.clientWidth + 1) {
          const ellipsis = style.textOverflow === "ellipsis";
          // O completo pode morar no próprio trecho cortado (`title` no nome do cliente
          // dentro de um cartão-botão), além do nome acessível do controle.
          const nodeNamed = Boolean(node.closest<HTMLElement>("[title]")?.title) &&
            control.contains(node.closest("[title]"));
          if (!ellipsis || !(named || nodeNamed)) {
            add(
              "control-text-overflow",
              control,
              ellipsis
                ? `Rótulo “${label}” termina em reticência sem o texto completo na dica ou no nome acessível.`
                : `Rótulo “${label}” cortado sem reticência (${node.scrollWidth}px de texto em ${node.clientWidth}px).`,
            );
            break;
          }
        }
      }
    }

    // Controles que se sobrepõem: um cobre o outro (rótulo que empurra o vizinho, barra
    // que não cabe). Pai e filho não contam; o que mora em overlay aberto também não, nem
    // o que está inerte atrás de um modal. Só se comparam controles da MESMA camada: o
    // conteúdo que rola por baixo de uma barra fixa ou grudada é o `covered-by-chrome`,
    // não sobreposição.
    const flat = labelControls.filter(
      (element) =>
        !element.closest(
          "[role='dialog'], [role='alertdialog'], [role='menu'], [role='listbox'], [inert], [aria-hidden='true'], [data-operator-overlap-allowed]",
        ),
    );
    const layerOf = (element: HTMLElement) => {
      for (let node: HTMLElement | null = element; node; node = node.parentElement) {
        const position = getComputedStyle(node).position;
        if (position === "fixed" || position === "sticky") return node;
      }
      return null;
    };
    const layers = new Map(flat.map((element) => [element, layerOf(element)]));
    // A caixa que de fato aparece: o retângulo recortado por todo ancestral que corta o
    // que passa dele (lista que rola por baixo do rodapé não é sobreposição).
    const shownRect = (element: HTMLElement) => {
      const rect = element.getBoundingClientRect();
      let { left, top, right, bottom } = rect;
      for (let node = element.parentElement; node; node = node.parentElement) {
        const style = getComputedStyle(node);
        const clipsX = !["", "visible"].includes(style.overflowX);
        const clipsY = !["", "visible"].includes(style.overflowY);
        if (!clipsX && !clipsY) continue;
        const clip = node.getBoundingClientRect();
        if (clipsX) {
          left = Math.max(left, clip.left);
          right = Math.min(right, clip.right);
        }
        if (clipsY) {
          top = Math.max(top, clip.top);
          bottom = Math.min(bottom, clip.bottom);
        }
      }
      return { left, top, right, bottom };
    };
    const shown = new Map(flat.map((element) => [element, shownRect(element)]));
    for (let index = 0; index < flat.length; index += 1) {
      const a = flat[index]!;
      const ra = shown.get(a)!;
      for (let other = index + 1; other < flat.length; other += 1) {
        const b = flat[other]!;
        if (a.contains(b) || b.contains(a)) continue;
        if (layers.get(a) !== layers.get(b)) continue;
        const rb = shown.get(b)!;
        const ix = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left);
        const iy = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
        if (ix > 2 && iy > 2) {
          const name = (element: HTMLElement) =>
            element.getAttribute("aria-label") ||
            element.textContent?.trim().replace(/\s+/g, " ").slice(0, 40) ||
            element.tagName.toLowerCase();
          add(
            "control-overlap",
            b,
            `Controles “${name(a)}” e “${name(b)}” se sobrepõem em ${Math.round(ix)}×${Math.round(iy)}px.`,
          );
        }
      }
    }

    // Texto de peça fixa (`op-fixed-lines`): reserva sempre as linhas declaradas
    // (o cartão não muda de altura com 1, 2 ou 3 linhas) e, cortado, leva o texto
    // completo na dica ou no nome acessível.
    for (const element of document.querySelectorAll<HTMLElement>(".op-fixed-lines")) {
      if (!visible(element)) continue;
      const style = getComputedStyle(element);
      const lines = Number(style.getPropertyValue("--op-lines")) || 2;
      const lineHeight = Number.parseFloat(style.lineHeight);
      if (Number.isFinite(lineHeight) && Math.abs(element.clientHeight - lines * lineHeight) > 1.5) {
        add(
          "fixed-text",
          element,
          `Texto de peça fixa mede ${element.clientHeight}px; reserva ${lines} linhas de ${lineHeight}px.`,
        );
      }
      if (
        element.scrollHeight > element.clientHeight + 1 &&
        !element.title &&
        !element.getAttribute("aria-label")
      ) {
        add(
          "fixed-text",
          element,
          "Texto de peça fixa cortado sem o completo na dica ou no nome acessível.",
        );
      }
    }

    for (const overlay of document.querySelectorAll<HTMLElement>(
      "[role='dialog'], [role='alertdialog'], [role='menu'], [role='listbox']",
    )) {
      if (!visible(overlay)) continue;
      const rect = overlay.getBoundingClientRect();
      const top = document.elementFromPoint(
        Math.max(0, rect.left + rect.width / 2),
        Math.max(0, rect.top + rect.height / 2),
      );
      if (top && !overlay.contains(top))
        add(
          "overlay-layer",
          overlay,
          "Overlay não está na camada superior no próprio centro.",
        );
    }

    for (const skeleton of document.querySelectorAll<HTMLElement>(
      "[data-skeleton-for]",
    )) {
      const target = document.querySelector<HTMLElement>(
        skeleton.dataset.skeletonFor || "",
      );
      if (!target) continue;
      const a = skeleton.getBoundingClientRect();
      const b = target.getBoundingClientRect();
      if (
        Math.abs(a.width - b.width) > 2 ||
        Math.abs(a.height - b.height) > 2
      ) {
        add("skeleton-shape", skeleton, "Skeleton não preserva a forma final.");
      }
    }

    const safeBottom =
      Number.parseFloat(
        getComputedStyle(root).getPropertyValue("--op-safe-bottom"),
      ) || 0;
    for (const bar of chrome.filter(
      (element) =>
        getComputedStyle(element).position === "fixed" &&
        element.getBoundingClientRect().bottom >= innerHeight - 1,
    )) {
      const content = document.querySelector<HTMLElement>(
        "[data-operator-scroll-content]",
      );
      if (
        content &&
        Number.parseFloat(getComputedStyle(content).paddingBottom) + 1 <
          bar.getBoundingClientRect().height + safeBottom
      ) {
        add(
          "safe-area",
          content,
          "Conteúdo não reserva a barra fixa e a área segura inferior.",
        );
      }
    }
    return findings;
  }, options);
  const only = options.only ? new Set(options.only) : null;
  return only ? findings.filter((finding) => only.has(finding.kind)) : findings;
}
