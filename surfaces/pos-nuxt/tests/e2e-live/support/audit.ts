// A régua da prévia, num lugar só (#2954).
//
// Contraste do texto contra o fundo efetivo, letra, caixa dentro da tela, nada
// cortado, nada encoberto. A J5, a J6, a J7, a J11 e a J12 carregavam cada uma a sua
// cópia, e as cópias tinham divergido: a J5 não olhava camada por cima, a J6 rolava
// cada texto até a área visível, a J11 e a J12 cobravam a escala de letra e a coluna
// esmagada. Aqui a medição é uma só, a mais completa, e o que cada jornada cobra a
// mais vira uma regra com nome (`AuditRule`), escrita na chamada.
import { expect, type Page } from "@playwright/test";

/** Espera o diálogo parar de animar antes de medir ou capturar. */
export async function still(page: Page) {
  // Só as animações que terminam: um spinner infinito (o "Ao vivo") nunca para.
  await page.waitForFunction(() =>
    document.getAnimations().every(
      (animation) => animation.playState !== "running" || animation.effect?.getTiming().iterations === Infinity,
    ),
  );
}

/** O que uma jornada cobra além do mínimo da casa (contraste, letra, tela, corte, camada). */
export interface AuditRule {
  /**
   * Mede cada texto onde o operador o lê: rolado até o meio da área visível (no
   * celular a página rola; na mesa, a coluna). Abaixo da dobra não é defeito;
   * encoberto pela barra de baixo depois de rolar, é. A dica "tem mais abaixo"
   * (`MoreBelow`) flutua por cima enquanto há o que rolar e não conta como camada.
   */
  scroll?: boolean;
  /** Reprova o texto encoberto por outra camada (véu, toast, barra). Padrão: sim. */
  covered?: boolean;
  /** Só a escala de letra da casa: 12, 14, 16, 18 e 20 px. */
  fontScale?: boolean;
  /** Reprova a frase esmagada numa coluna estreita (uma palavra por linha). */
  crushed?: boolean;
}

export interface AuditRow {
  text: string;
  contrast: number;
  fontPx: number;
  weight: string;
  /** A cor da letra já misturada ao fundo, com a opacidade do texto e dos pais. */
  color: string;
  background: string;
  left: number;
  right: number;
  top: number;
  height: number;
  visible: boolean;
  clipped: boolean;
  inside: boolean;
  crushed: boolean;
  covered: boolean;
  coveredBy: string;
  underScrollHint: boolean;
}

/**
 * Mede os textos de `selector` sem reprovar nada: devolve as linhas e as cores que
 * o parser não leu. Elementos sem texto (só ícone) ficam de fora.
 */
export async function measure(
  page: Page,
  selector: string,
  rule: Pick<AuditRule, "scroll"> = {},
): Promise<{ rows: AuditRow[]; unparsed: string[] }> {
  return page.evaluate(({ sel, scroll }) => {
    const unparsed: string[] = [];
    const parse = (value: string) => {
      // `bg-warning/10` sai como `color(srgb r g b / a)`, com canais de 0 a 1.
      const srgb = value.match(/color\(srgb ([^)]+)\)/);
      if (srgb) {
        const [r, g, b, a = "1"] = srgb[1]!.split(/[\s/]+/).filter(Boolean);
        return [Number(r) * 255, Number(g) * 255, Number(b) * 255, Number(a)];
      }
      // Os tokens de cor da suíte saem em OKLab/OKLCH: converte para sRGB pela matriz
      // de Björn Ottosson.
      const ok = value.match(/okl(ab|ch)\(([^)]+)\)/);
      if (ok) {
        const [p0, p1, p2, alpha = "1"] = ok[2]!.split(/[\s/]+/).filter(Boolean);
        const L = Number.parseFloat(p0!) / (p0!.endsWith("%") ? 100 : 1);
        let A = Number(p1);
        let B = Number(p2);
        if (ok[1] === "ch") {
          const h = (Number.parseFloat(p2!) * Math.PI) / 180;
          [A, B] = [Number(p1) * Math.cos(h), Number(p1) * Math.sin(h)];
        }
        const l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3;
        const m2 = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3;
        const s2 = (L - 0.0894841775 * A - 1.291485548 * B) ** 3;
        const linear = [
          4.0767416621 * l - 3.3077115913 * m2 + 0.2309699292 * s2,
          -1.2684380046 * l + 2.6097574011 * m2 - 0.3413193965 * s2,
          -0.0041960863 * l - 0.7034186147 * m2 + 1.707614701 * s2,
        ];
        const encoded = linear.map((c) => {
          const v = Math.min(1, Math.max(0, c));
          return 255 * (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055);
        });
        return [...encoded, Number.parseFloat(alpha) / (alpha.endsWith("%") ? 100 : 1)];
      }
      const m = value.match(/rgba?\(([^)]+)\)/);
      if (!m) {
        if (value && value !== "transparent") unparsed.push(value);
        return null;
      }
      const [r, g, b, a = "1"] = m[1]!.split(/[\s,/]+/).filter(Boolean);
      return [Number(r), Number(g), Number(b), Number(a)];
    };
    const luminance = ([r, g, b]: number[]) => {
      const [R, G, B] = [r, g, b].map((c) => {
        const v = c! / 255;
        return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * R! + 0.7152 * G! + 0.0722 * B!;
    };
    // O fundo efetivo: as camadas de baixo para cima, com a transparência de cada uma.
    const background = (el: Element) => {
      const layers: number[][] = [];
      for (let node: Element | null = el; node; node = node.parentElement) {
        const c = parse(getComputedStyle(node).backgroundColor);
        if (c && c[3]! > 0) {
          layers.push(c);
          if (c[3] === 1) break;
        }
      }
      let out = [255, 255, 255];
      for (const layer of layers.reverse()) {
        const alpha = layer[3]!;
        out = out.map((v, i) => layer[i]! * alpha + v * (1 - alpha));
      }
      return out;
    };
    // O que está no ponto do meio do texto é ele mesmo, um filho dele ou um pai (texto
    // que não recebe ponteiro): nenhuma outra camada por cima.
    const topAt = (box: DOMRect) => document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
    const isSelf = (el: Element, top: Element | null) => Boolean(top && (top === el || el.contains(top) || top.contains(el)));
    const rows = Array.from(document.querySelectorAll(sel))
      .filter((el) => (el as HTMLElement).offsetParent !== null && (el.textContent || "").trim())
      .map((el) => {
        const style = getComputedStyle(el);
        const fg = parse(style.color)!;
        // A opacidade do elemento (e dos pais) também clareia a letra: `opacity-80`.
        for (let node: Element | null = el; node; node = node.parentElement) fg[3] = fg[3]! * Number(getComputedStyle(node).opacity);
        const bg = background(el);
        const blended = fg.slice(0, 3).map((v, i) => v * fg[3]! + bg[i]! * (1 - fg[3]!));
        const [l1, l2] = [luminance(blended), luminance(bg)].sort((x, y) => y - x);
        if (scroll) (el as HTMLElement).scrollIntoView({ block: "center", behavior: "instant" });
        const box = el.getBoundingClientRect();
        const visible = box.bottom > 0 && box.top < window.innerHeight;
        const top = topAt(box);
        const underScrollHint = Boolean(top?.closest("[data-more-below]"));
        // Sem rolar, o texto fora da área visível conta como encoberto (o meio dele não
        // está na tela); rolando, só conta o que está à vista, e a dica de rolagem não.
        const covered = scroll ? visible && !underScrollHint && !isSelf(el, top) : !isSelf(el, top);
        return {
          text: (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 70),
          contrast: Math.round(((l1! + 0.05) / (l2! + 0.05)) * 100) / 100,
          fontPx: Number.parseFloat(style.fontSize),
          weight: style.fontWeight,
          color: `rgb(${blended.map(Math.round).join(", ")})`,
          background: `rgb(${bg.map(Math.round).join(", ")})`,
          left: Math.round(box.left),
          right: Math.round(box.right),
          top: Math.round(box.top),
          height: Math.round(box.height),
          visible,
          clipped: (el as HTMLElement).scrollWidth > (el as HTMLElement).clientWidth + 1,
          inside: box.left >= 0 && box.right <= window.innerWidth + 0.5,
          // Coluna esmagada: a frase virou uma palavra por linha num espaço estreito.
          crushed: box.width < 140 && box.height / (Number.parseFloat(style.lineHeight) || Number.parseFloat(style.fontSize) * 1.4) >= 3.5,
          covered,
          coveredBy: isSelf(el, top) || !top
            ? ""
            : `${top.tagName.toLowerCase()} ${(top.getAttribute("class") || "").slice(0, 60)} ${(top.textContent || "").trim().slice(0, 40)}`,
          underScrollHint,
        };
      });
    return { rows, unparsed: [...new Set(unparsed)] };
  }, { sel: selector, scroll: Boolean(rule.scroll) });
}

/**
 * A AUDITORIA da prévia (regra da casa, 16/11): mede, registra (`AUDITORIA <rótulo>`,
 * para o `auditoria.txt` do PR) e reprova abaixo de 4,5:1, abaixo de 12 px, fora da
 * tela, cortado ou encoberto, mais o que a `rule` pedir. Cor que o parser não lê
 * seria um fundo ignorado: a auditoria não passa por omissão.
 */
export async function audits(page: Page, label: string, selector: string, rule: AuditRule = {}) {
  const { rows, unparsed } = await measure(page, selector, rule);
  expect(unparsed, `cores não lidas pela auditoria: ${unparsed.join(" | ")}`).toEqual([]);
  console.log(`AUDITORIA ${label}: ${JSON.stringify(rows)}`);
  expect(rows.length, `${label}: nada medido`).toBeGreaterThan(0);
  for (const row of rows) {
    expect(row.contrast, `${label}: contraste de "${row.text}"`).toBeGreaterThanOrEqual(4.5);
    expect(row.fontPx, `${label}: letra de "${row.text}"`).toBeGreaterThanOrEqual(12);
    if (rule.fontScale) expect([12, 14, 16, 18, 20], `${label}: letra de "${row.text}" fora da escala`).toContain(row.fontPx);
    expect(row.inside, `${label}: "${row.text}" fora da tela`).toBe(true);
    expect(row.clipped, `${label}: "${row.text}" cortado`).toBe(false);
    if (rule.covered !== false) expect(row.covered, `${label}: "${row.text}" encoberto por outra camada`).toBe(false);
    if (rule.crushed) expect(row.crushed, `${label}: "${row.text}" esmagado numa coluna estreita`).toBe(false);
  }
  return rows;
}
