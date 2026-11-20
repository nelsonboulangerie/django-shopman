// JORNADA J5 — encomenda de outro dia acima do plano (EXCELENCIA-PDV WP-E2, D-041).
//
// A Caixa (Fran) monta uma encomenda de 200 Baguette de Tradition para amanhã, com
// 22 planejadas no seed. A linha mostra a fornada da data; o Validar fica travado com
// os dois números e pede o gerente; sem a assinatura nada fecha; a Gerente (Joyce),
// escolhida da lista, vê os dois números no diálogo e assina com o próprio PIN; "Na
// retirada" não aparece para outro dia. Tudo pela tela, no celular (375 px) e no
// balcão (1366 px). Como rodar: README.md desta pasta.
//
// O seed planeja 22 Baguette de Tradition para amanhã. A régua é o lote planejado PARA
// a data; a sobra de hoje (que o seed deixa na vitrine) não entra em nenhum número.
import { capture, cast, expect, settled, test, type Page } from "./support/operator";

const PRODUCT = process.env.PDV_LIVE_OVER_PLAN_PRODUCT || "Baguette de Tradition";
const PLANNED = process.env.PDV_LIVE_OVER_PLAN_PLANNED || "22";
const CUSTOMER = process.env.PDV_LIVE_OVER_PLAN_CUSTOMER || "Ana Ferreira";
const CUSTOMER_PHONE = process.env.PDV_LIVE_OVER_PLAN_PHONE || "43995555555";
const QTY = "200";

function exact(text: string) {
  return new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
}

/** Amanhã no relógio da loja (o navegador roda em America/Sao_Paulo): `19/11`. */
function tomorrow(): string {
  const now = new Date(new Date().toLocaleString("en-US", { timeZone: "America/Sao_Paulo" }));
  now.setDate(now.getDate() + 1);
  return `${String(now.getDate()).padStart(2, "0")}/${String(now.getMonth() + 1).padStart(2, "0")}`;
}

async function opensOrder(page: Page) {
  // A porta da encomenda é a seção Encomendas (rail no balcão, barra de baixo no
  // celular), e de lá "Nova encomenda".
  await page.getByRole("link", { name: /^Encomendas/ }).locator("visible=true").first().click();
  await settled(page);
  await page.getByRole("button", { name: /^Nova( encomenda)?$/ }).locator("visible=true").first().click({ timeout: 30_000 });
  // "Iniciar nova encomenda?": a próxima comanda livre fica em uso para montá-la.
  const start = page.getByRole("dialog", { name: "Iniciar nova encomenda?" });
  const heading = page.getByRole("heading", { name: /Nova encomenda|Preparar encomenda/ });
  await expect(async () => {
    if (await start.isVisible().catch(() => false)) {
      await start.getByRole("button", { name: "Iniciar encomenda", exact: true }).click({ timeout: 2000 });
    }
    await expect(heading).toBeVisible({ timeout: 2000 });
  }).toPass({ timeout: 60_000 });
}

async function identifiesCustomer(page: Page) {
  await page.getByRole("button", { name: "Identificar cliente" }).locator("visible=true").first().click();
  const search = page.getByRole("combobox", { name: "Buscar cliente" }).locator("visible=true").first();
  await search.click();
  await search.pressSequentially(CUSTOMER_PHONE);
  const dialog = page.getByRole("dialog").filter({ has: page.getByRole("combobox", { name: "Buscar cliente" }) });
  await dialog.getByRole("option", { name: exact(CUSTOMER) }).first().click({ timeout: 30_000 });
  // Escolher o cadastro pode fechar o diálogo sozinho; se não fechar, "Concluir".
  const done = dialog.getByRole("button", { name: "Concluir", exact: true });
  await expect(async () => {
    if (await done.isVisible().catch(() => false)) await done.click({ timeout: 2000 });
    await expect(dialog).toBeHidden({ timeout: 2000 });
  }).toPass({ timeout: 30_000 });
}

// A ordem do funil (WP-E13, #2754): depois do cliente vem "para quando", e só
// então o recebimento.
async function schedulesTomorrowPickup(page: Page) {
  await page.getByRole("radio", { name: /^Amanhã/ }).locator("visible=true").first().click();
  const slot = page
    .locator('[data-order-step="schedule"]')
    .getByRole("button")
    .filter({ hasText: /\d{1,2}h|\d{2}:\d{2}/ })
    .and(page.locator(":enabled"))
    .first();
  await slot.click({ timeout: 30_000 });
  await page.getByRole("button", { name: "Continuar", exact: true }).click();
  await page.locator("[data-order-fulfillment-options]").getByRole("radio", { name: /^Retirada/ }).click();
  await page.getByRole("button", { name: /Montar encomenda/ }).click();
  await expect(page.getByPlaceholder(/Buscar produto/).locator("visible=true").first()).toBeVisible({ timeout: 30_000 });
}

/** Lança o produto e digita a quantidade no editor da linha. */
async function ordersQuantity(page: Page) {
  const search = page.getByPlaceholder(/Buscar produto/).locator("visible=true").first();
  await search.click();
  await search.pressSequentially(PRODUCT);
  await page.locator("button[data-pos-product]").filter({ hasText: exact(PRODUCT) }).first().click({ timeout: 30_000 });
  // A baguete fica pronta mais tarde que o turno escolhido: a tela oferece o turno
  // dela, e a Fran aceita (é o que o cliente ouviria).
  const later = page.getByRole("button", { name: /^Mudar para/ }).locator("visible=true").first();
  if (await later.waitFor({ timeout: 5000 }).then(() => true, () => false)) await later.click();
  // No celular a comanda é a folha de baixo: abre para ver a linha.
  const sheet = page.getByRole("button", { name: "Ver a comanda" }).locator("visible=true").first();
  if (await sheet.isVisible().catch(() => false)) await sheet.click();
  await page.locator("[data-item-select]").locator("visible=true").first().click();
  const touch = page.locator("[data-pos-touch-editor]").locator("visible=true").first();
  if (await touch.waitFor({ timeout: 3000 }).then(() => true, () => false)) {
    // Toque: o numérico da linha escreve a quantidade, e "Pronto" fecha.
    const editor = page.locator("[data-pos-line-editor]").locator("visible=true").first();
    for (const digit of QTY) await editor.getByRole("button", { name: `Dígito ${digit}`, exact: true }).click();
    await editor.locator("[data-pos-line-editor-close]").click();
  } else {
    // Balcão: o teclado físico digita a quantidade da linha aberta.
    await page.keyboard.type(QTY);
    await page.keyboard.press("Enter");
  }
}

/**
 * A AUDITORIA da prévia (regra da casa, 16/11): contraste do texto contra o fundo
 * efetivo, tamanho da letra, caixa dentro da tela e sem texto cortado. Mede o que
 * este WP pôs na tela e reprova abaixo de 4,5:1, abaixo de 12 px ou fora da tela.
 */
async function audits(page: Page, label: string, selector: string) {
  const report = await page.evaluate((sel) => {
    const unparsed: string[] = [];
    const parse = (value: string) => {
      // `bg-warning/10` sai como `color(srgb r g b / a)`, com canais de 0 a 1.
      const srgb = value.match(/color\(srgb ([^)]+)\)/);
      if (srgb) {
        const [r, g, b, a = "1"] = srgb[1]!.split(/[\s/]+/).filter(Boolean);
        return [Number(r) * 255, Number(g) * 255, Number(b) * 255, Number(a)];
      }
      // Os tokens de cor da suíte saem em OKLab/OKLCH (`bg-warning/10`): converte
      // para sRGB pela matriz de Björn Ottosson.
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
    const rows = Array.from(document.querySelectorAll(sel))
      .filter((el) => (el as HTMLElement).offsetParent !== null)
      .map((el) => {
        const style = getComputedStyle(el);
        const fg = parse(style.color)!;
        // A opacidade do elemento (e dos pais) também clareia a letra: `opacity-80`.
        for (let node: Element | null = el; node; node = node.parentElement) fg[3] = fg[3]! * Number(getComputedStyle(node).opacity);
        const bg = background(el);
        const blended = fg.slice(0, 3).map((v, i) => v * fg[3]! + bg[i]! * (1 - fg[3]!));
        const [l1, l2] = [luminance(blended), luminance(bg)].sort((x, y) => y - x);
        const box = el.getBoundingClientRect();
        return {
          text: (el.textContent || "").trim().slice(0, 70),
          contrast: Math.round(((l1! + 0.05) / (l2! + 0.05)) * 100) / 100,
          fontPx: Number.parseFloat(style.fontSize),
          color: style.color,
          background: `rgb(${bg.map(Math.round).join(", ")})`,
          left: Math.round(box.left),
          right: Math.round(box.right),
          clipped: (el as HTMLElement).scrollWidth > (el as HTMLElement).clientWidth + 1,
          inside: box.left >= 0 && box.right <= window.innerWidth + 0.5,
        };
      });
    return { rows, unparsed: [...new Set(unparsed)] };
  }, selector).then(({ rows, unparsed }) => {
    // Cor que o parser não lê seria um fundo ignorado: a auditoria não pode passar por omissão.
    expect(unparsed, `cores não lidas pela auditoria: ${unparsed.join(" | ")}`).toEqual([]);
    return rows;
  });
  console.log(`AUDITORIA ${label}: ${JSON.stringify(report)}`);
  expect(report.length, `${label}: nada medido`).toBeGreaterThan(0);
  for (const row of report) {
    expect(row.contrast, `${label}: contraste de "${row.text}"`).toBeGreaterThanOrEqual(4.5);
    expect(row.fontPx, `${label}: letra de "${row.text}"`).toBeGreaterThanOrEqual(12);
    expect(row.inside, `${label}: "${row.text}" fora da tela`).toBe(true);
    expect(row.clipped, `${label}: "${row.text}" cortado`).toBe(false);
  }
  return report;
}

test.describe.configure({ mode: "serial" });

for (const device of ["phone", "counter"] as const) {
  test.describe(`J5 Encomenda acima do plano · ${device === "phone" ? "375 px" : "1366 px"}`, () => {
    test.use({ device });

    test("200 baguetes para amanhã contra 22 planejadas: só o gerente libera", async ({ cashierAtCounter: page }, testInfo) => {
      test.setTimeout(8 * 60_000);
      const day = tomorrow();

      await opensOrder(page);
      await identifiesCustomer(page);
      await schedulesTomorrowPickup(page);
      await capture(page, testInfo, "encomenda-para-amanha");

      await ordersQuantity(page);
      // 1 · A linha mostra a fornada da data e que o pedido passa dela.
      const fact = page.locator('[data-pos-line-plan="over"]').locator("visible=true").first();
      await expect(fact).toContainText(`Passa do plano: ${PLANNED} planejadas para ${day}`, { timeout: 30_000 });
      // A sobra de hoje não lastreia encomenda (dono, 18/11/2026): nenhum número além do plano.
      await expect(fact).not.toContainText("livres");
      await audits(page, "linha", '[data-pos-line-plan="over"] > span');
      await capture(page, testInfo, "linha-passa-do-plano");

      // 2 · No Pagamento: o aviso que trava diz os dois números; "Na retirada" não existe.
      // O Pagamento de sempre (no celular, "Outras formas" da folha da comanda).
      await page.getByRole("button", { name: /^Pagamento|^Outras formas/ }).locator("visible=true").first().click();
      await expect(page.getByRole("button", { name: /^Dinheiro/ }).locator("visible=true").first()).toBeVisible({ timeout: 30_000 });
      await expect(page.getByRole("button", { name: "Na retirada" })).toHaveCount(0);
      await page.getByRole("button", { name: /^Dinheiro/ }).and(page.locator(":enabled")).locator("visible=true").first().click();
      // Escolhida a forma, o que segura o botão é o plano, com os dois números.
      const block = page.getByText("A encomenda passa do plano. Só o gerente libera.").locator("visible=true").first();
      await expect(block).toBeVisible({ timeout: 30_000 });
      await expect(page.getByText(`${PRODUCT}: ${QTY} pedidas, ${PLANNED} planejadas para ${day}`).locator("visible=true").first()).toBeVisible();
      const ask = page.getByRole("button", { name: /^Pedir autorização/ }).locator("visible=true").first();
      await expect(ask).toBeEnabled({ timeout: 30_000 });
      await audits(page, "aviso", "li.border-warning > span > span");
      await capture(page, testInfo, "validar-travado");

      // 3 · Sem a assinatura não fecha: o diálogo abre, a Fran fecha, nada muda.
      await ask.click();
      const dialog = page.getByRole("dialog", { name: "Autorizar a venda" });
      await expect(dialog).toBeVisible({ timeout: 30_000 });
      await expect(dialog.locator("[data-over-plan-context]")).toContainText(`${QTY} pedidas, ${PLANNED} planejadas para ${day}`);
      // A captura espera a animação de entrada do diálogo terminar.
      await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"));
      const context = await audits(page, "dialogo", "[data-over-plan-context] p");
      // Alinhamento: o quadro dos números bate borda com o aviso "Você continua como".
      const edges = await page.evaluate(() => {
        const ctx = document.querySelector("[data-over-plan-context]")!.getBoundingClientRect();
        const sibling = (document.querySelector("[data-over-plan-context]")!.parentElement!.firstElementChild as HTMLElement).getBoundingClientRect();
        return { ctx: [Math.round(ctx.left), Math.round(ctx.right)], alert: [Math.round(sibling.left), Math.round(sibling.right)] };
      });
      console.log(`AUDITORIA alinhamento do diálogo: ${JSON.stringify(edges)}`);
      expect(edges.ctx).toEqual(edges.alert);
      void context;
      await capture(page, testInfo, "gerente-ve-os-numeros");
      await page.keyboard.press("Escape");
      await expect(dialog).toBeHidden();
      await expect(block).toBeVisible();
      await expect(ask).toBeVisible();

      // 4 · A Gerente, escolhida da lista, assina com o próprio PIN, e a encomenda fecha.
      await ask.click();
      await expect(dialog).toBeVisible({ timeout: 30_000 });
      await dialog.getByRole("button", { name: new RegExp(cast.manager.name) }).first().click();
      for (const digit of cast.manager.pin) {
        await dialog.getByRole("button", { name: digit, exact: true }).click();
      }
      const confirm = dialog.getByRole("button", { name: /^Confirmar|^Autorizar/ }).first();
      if (await confirm.isVisible({ timeout: 2000 }).catch(() => false)) await confirm.click();
      await expect(dialog).toBeHidden({ timeout: 60_000 });
      await expect(page.getByText(/Encomenda registrada|CONFIRME COM O CLIENTE|Confirme com o cliente/).locator("visible=true").first())
        .toBeVisible({ timeout: 60_000 });
      await capture(page, testInfo, "encomenda-registrada");
    });
  });
}
