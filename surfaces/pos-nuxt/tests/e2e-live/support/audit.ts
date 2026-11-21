// A régua da prévia, para as sondas que precisam dela (#2726).
//
// Mesma auditoria da J5 e da J7 (contraste do texto contra o fundo efetivo, letra,
// caixa dentro da tela, nada cortado, nada encoberto), extraída para cá para a
// sonda do erro dentro do diálogo da antessala. A J5 e a J7 seguem com a cópia
// delas; trazê-las para cá é limpeza à parte.
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

/**
 * A AUDITORIA da prévia (regra da casa, 16/11): contraste do texto contra o fundo
 * efetivo (com a opacidade do texto e dos pais), tamanho da letra, caixa dentro da
 * tela e sem texto cortado. Reprova abaixo de 4,5:1, abaixo de 12 px ou fora da tela.
 * Mesma régua da J5 (`j5-encomenda-acima-do-plano.live.spec.ts`).
 */
export async function measure(page: Page, selector: string) {
  return page.evaluate((sel) => {
    const unparsed: string[] = [];
    const parse = (value: string) => {
      const srgb = value.match(/color\(srgb ([^)]+)\)/);
      if (srgb) {
        const [r, g, b, a = "1"] = srgb[1]!.split(/[\s/]+/).filter(Boolean);
        return [Number(r) * 255, Number(g) * 255, Number(b) * 255, Number(a)];
      }
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
    const rows = Array.from(document.querySelectorAll(sel))
      .filter((el) => (el as HTMLElement).offsetParent !== null)
      .map((el) => {
        const style = getComputedStyle(el);
        const fg = parse(style.color)!;
        for (let node: Element | null = el; node; node = node.parentElement) fg[3] = fg[3]! * Number(getComputedStyle(node).opacity);
        const bg = background(el);
        const blended = fg.slice(0, 3).map((v, i) => v * fg[3]! + bg[i]! * (1 - fg[3]!));
        const [l1, l2] = [luminance(blended), luminance(bg)].sort((x, y) => y - x);
        const box = el.getBoundingClientRect();
        return {
          text: (el.textContent || "").trim().slice(0, 70),
          contrast: Math.round(((l1! + 0.05) / (l2! + 0.05)) * 100) / 100,
          fontPx: Number.parseFloat(style.fontSize),
          weight: style.fontWeight,
          color: style.color,
          background: `rgb(${bg.map(Math.round).join(", ")})`,
          left: Math.round(box.left),
          right: Math.round(box.right),
          clipped: (el as HTMLElement).scrollWidth > (el as HTMLElement).clientWidth + 1,
          inside: box.left >= 0 && box.right <= window.innerWidth + 0.5,
          // Nenhuma camada por cima (véu de diálogo, toast, banner): o ponto do meio
          // do texto, na tela, é o próprio texto.
          covered: (() => {
            const top = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
            return !(top && (top === el || el.contains(top)));
          })(),
        };
      });
    return { rows, unparsed: [...new Set(unparsed)] };
  }, selector);
}

export async function audits(page: Page, label: string, selector: string) {
  const { rows, unparsed } = await measure(page, selector);
  expect(unparsed, `cores não lidas pela auditoria: ${unparsed.join(" | ")}`).toEqual([]);
  console.log(`AUDITORIA ${label}: ${JSON.stringify(rows)}`);
  expect(rows.length, `${label}: nada medido`).toBeGreaterThan(0);
  for (const row of rows) {
    expect(row.contrast, `${label}: contraste de "${row.text}"`).toBeGreaterThanOrEqual(4.5);
    expect(row.fontPx, `${label}: letra de "${row.text}"`).toBeGreaterThanOrEqual(12);
    expect(row.inside, `${label}: "${row.text}" fora da tela`).toBe(true);
    expect(row.clipped, `${label}: "${row.text}" cortado`).toBe(false);
    expect(row.covered, `${label}: "${row.text}" encoberto por outra camada`).toBe(false);
  }
  return rows;
}

