// O aviso padrão da suíte, medido no navegador (#2746).
//
// Duas grandezas que só o navegador diz de verdade, com o CSS que a tela aplica:
//   - a ÁREA DE TOQUE do X de fechar: pelo menos 44 px (o X desenhado tem 20 px);
//   - o CONTRASTE do texto sobre o fundo do aviso, nos quatro tons e nos dois temas:
//     pelo menos 4,5:1 (WCAG AA).
// A auditoria de capturas que abriu a #2746 leu 3,6:1 no âmbar do tema claro; medido
// pela cor que o CSS aplica, dá 5,11:1 (pixel de texto suavizado numa captura não é a
// cor do texto). A conta estática mora no kit (`tests/alertCloseTarget.test.ts` e
// `tests/alertContrast.test.ts`); esta é a prova na tela.
//
// O aviso medido é o do detalhe da corrida (`CourierRideDetail`), o `NuxtAlert` padrão
// com fechar. A resposta do servidor de mentira é alterada para a corrida ter aviso.
import { expect, test } from "@playwright/test";
import { writeFileSync } from "node:fs";

const OUT = process.env.AVISO_OUT || "";
const SHOT = process.env.AVISO_SHOT || "";
const MIN_TARGET_PX = 44;
const MIN_CONTRAST = 4.5;

test.use({ viewport: { width: 1366, height: 900 } });

test("o fechar do aviso tem 44 px de área de toque e o texto passa de 4,5:1", async ({ page }) => {
  await page.route("**/api/v1/backstage/**", async (route) => {
    const response = await route.fetch();
    let body: unknown;
    try { body = await response.json(); } catch { return route.fulfill({ response }); }
    const walk = (node: any) => {
      if (!node || typeof node !== "object") return;
      if (Array.isArray(node.rides) && node.rides[0]) {
        node.rides[0].state = "reopened";
        node.rides[0].reopened_at = new Date(Date.now() - 4 * 60_000).toISOString();
        node.rides[0].reopened_driver = "Diego";
      }
      for (const value of Object.values(node)) walk(value);
    };
    walk(body);
    return route.fulfill({ response, json: body });
  });
  await page.goto("/delivery?ride=776753357");
  const notice = page.locator("[data-ride-notice]");
  await notice.waitFor({ timeout: 20000 });
  // O painel do detalhe entra deslizando: medir no meio do movimento dá uma área
  // torta (o centro do X muda entre uma leitura e outra). Espera a posição parar.
  await expect
    .poll(async () => {
      const first = await notice.boundingBox();
      await page.waitForTimeout(150);
      const second = await notice.boundingBox();
      return Boolean(first && second && first.x === second.x && first.y === second.y);
    }, { timeout: 10000 })
    .toBe(true);
  const measure = async (dark: boolean) => page.evaluate((dark) => {
    document.documentElement.classList.toggle("dark", dark);
    const lum = (rgb: number[]) => { const [r, g, b] = rgb.map((c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
    const parse = (value: string) => { const probe = document.createElement("canvas").getContext("2d")!; probe.fillStyle = value; probe.fillRect(0, 0, 1, 1); return Array.from(probe.getImageData(0, 0, 1, 1).data); };
    const over = (top: number[], bottom: number[]) => { const a = top[3] / 255; return [0, 1, 2].map((i) => Math.round(a * top[i] + (1 - a) * bottom[i])); };
    const contrast = (a: number[], b: number[]) => { const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x); return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100; };
    const root = document.querySelector("[data-ride-notice]") as HTMLElement;
    // O fundo de quem está atrás do aviso (para compor fundo translúcido, se houver).
    const backdrop = (el: HTMLElement | null): number[] => { let node = el?.parentElement ?? null; let acc = [255, 255, 255]; const chain: number[][] = []; while (node) { chain.push(parse(getComputedStyle(node).backgroundColor)); node = node.parentElement; } for (const c of chain.reverse()) acc = over(c, acc); return acc; };
    const tones = ["info", "success", "warning", "error"] as const;
    const token: Record<string, string> = { info: "info", success: "success", warning: "warning", error: "destructive" };
    const base = root.className;
    const out: Record<string, unknown> = {};
    for (const tone of tones) {
      const clone = root.cloneNode(true) as HTMLElement;
      clone.removeAttribute("data-ride-notice");
      clone.className = base.replace(/\b(text|ring)-info\b/g, `$1-${tone}`).replace(/ring-info\//g, `ring-${tone}/`).replace(/var\(--info\)/g, `var(--${token[tone]})`).replace(/text-info/g, `text-${tone}`);
      root.parentElement!.appendChild(clone);
      const bg = over(parse(getComputedStyle(clone).backgroundColor), backdrop(clone));
      const title = clone.querySelector('[data-slot="title"]') as HTMLElement;
      const description = clone.querySelector('[data-slot="description"]') as HTMLElement;
      const ink = (el: HTMLElement) => { const style = getComputedStyle(el); const c = parse(style.color); const opacity = Number(style.opacity); return over([c[0], c[1], c[2], Math.round((c[3] / 255) * opacity * 255)], bg); };
      out[tone] = {
        classe: clone.className.split(/\s+/).filter((c) => /warning|info|success|error|destructive/.test(c)).join(" "),
        fundo: bg, titulo: ink(title), descricao: ink(description),
        contrasteTitulo: contrast(ink(title), bg), contrasteDescricao: contrast(ink(description), bg),
        tamanhoTitulo: getComputedStyle(title).fontSize, pesoTitulo: getComputedStyle(title).fontWeight,
      };
      clone.remove();
    }
    const close = root.querySelector('[data-slot="close"]') as HTMLElement;
    const box = close.getBoundingClientRect();
    const cx = box.left + box.width / 2; const cy = box.top + box.height / 2;
    const hits = (dx: number, dy: number) => { const el = document.elementFromPoint(cx + dx, cy + dy); return Boolean(el && (el === close || close.contains(el))); };
    // Até onde o toque ainda cai no botão, de meio em meio pixel, para cada lado do
    // centro: a área de toque é a menor das duas extensões (largura e altura).
    const reach = (dx: number, dy: number) => { let far = 0; for (let d = 0; d <= 40; d += 0.5) { if (hits(dx * d, dy * d)) far = d; else break; } return far; };
    const alvo = Math.min(reach(-1, 0) + reach(1, 0), reach(0, -1) + reach(0, 1)) + 0.5;
    return { tema: dark ? "escuro" : "claro", tons: out, fechar: { largura: Math.round(box.width), altura: Math.round(box.height), alvoEfetivo: alvo, classe: close.className } };
  }, dark);
  const claro = await measure(false);
  if (SHOT) await page.screenshot({ path: SHOT + "-claro.png" });
  const escuro = await measure(true);
  if (SHOT) await page.screenshot({ path: SHOT + "-escuro.png" });
  if (OUT) writeFileSync(OUT, JSON.stringify({ claro, escuro }, null, 2));

  for (const reading of [claro, escuro]) {
    expect(reading.fechar.alvoEfetivo, `área de toque do fechar no tema ${reading.tema}`).toBeGreaterThanOrEqual(MIN_TARGET_PX);
    for (const [tone, value] of Object.entries(reading.tons as Record<string, { contrasteTitulo: number; contrasteDescricao: number }>)) {
      expect(value.contrasteTitulo, `título do aviso ${tone} no tema ${reading.tema}`).toBeGreaterThanOrEqual(MIN_CONTRAST);
      expect(value.contrasteDescricao, `descrição do aviso ${tone} no tema ${reading.tema}`).toBeGreaterThanOrEqual(MIN_CONTRAST);
    }
  }
});
