// Captura e auditoria do lugar do aviso de tela (kit-aviso-depois-das-barras).
// Uso: node kitaviso-capture.mjs <tree> <app> <side> <baseURL> <mockURL> <outDir>
import { mkdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";

const [tree, app, side, baseURL, mockURL, outDir] = process.argv.slice(2);
const require = createRequire(join(tree, "surfaces/orders-nuxt/package.json"));
const { chromium } = require("playwright");
mkdirSync(outDir, { recursive: true });

const VIEWPORTS = [
  { id: "375", width: 375, height: 812 },
  { id: "1366", width: 1366, height: 768 },
];
const THEMES = ["light", "dark"];

const APPS = {
  orders: {
    key: "orders-nuxt-color-mode",
    route: "/",
    async before(page) {
      await page.request.get(mockURL + "/__visual/scenario?set=concierge");
    },
    ready: "[data-orders-app]",
    alertText: "Ana espera a resposta da equipe",
  },
  pos: {
    key: "pos-nuxt-color-mode",
    route: "/preorders",
    async before(page) {
      await page.clock.setFixedTime(new Date("2026-09-29T12:00:00"));
    },
    ready: "[data-preorder]:visible",
    alertText: "",
    // No celular a tela abre em Hoje; a encomenda com pagamento a conferir é de amanhã.
    async step(page, vp) {
      if (vp.width < 768) {
        await page.locator("[data-compact-primary] button").last().click();
        await page.waitForTimeout(800);
      }
    },
  },
};

// As barras do topo: as do kit e as que os apps montam (linha do chão, faixa primária do
// celular, as abas do Gestor). O aviso tem de começar depois da base de todas.
const BARS = [
  "[data-compact-bar]",
  "[data-compact-primary]",
  "[data-compact-settings-tabs]",
  "[data-operator-page-header]",
  "[data-page-header-actions]",
  "[data-page-header-filter-line]",
  "[data-page-header-active-filters]",
  "[data-page-header-filters]",
  "[data-page-header-selection]",
  "[data-operator-toolbar]",
  "[data-board-zone-bar]",
];

function audit(bars) {
  const parse = (v) => (v.match(/[\d.]+/g) || []).map(Number);
  const lum = ([r, g, b]) => {
    const c = [r, g, b].map((v) => {
      const x = v / 255;
      return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  };
  const background = (el) => {
    while (el) {
      const rgba = parse(getComputedStyle(el).backgroundColor);
      if (rgba.length >= 3 && (rgba.length < 4 || rgba[3] > 0.5)) return rgba.slice(0, 3);
      el = el.parentElement;
    }
    return [255, 255, 255];
  };
  const ratio = (a, b) => {
    const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
    return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
  };
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.display !== "none" && s.visibility !== "hidden";
  };
  const box = document.querySelector("[data-page-header-alerts]");
  const alert = document.querySelector("[data-page-header-alert]");
  if (!box || !alert) return { error: "sem aviso na tela" };
  const a = alert.getBoundingClientRect();
  const found = [];
  for (const sel of bars) {
    for (const el of document.querySelectorAll(sel)) {
      if (!visible(el) || box.contains(el)) continue;
      const r = el.getBoundingClientRect();
      found.push({ bar: sel, top: Math.round(r.top), bottom: Math.round(r.bottom) });
    }
  }
  const lastBottom = Math.max(0, ...found.map((b) => b.bottom));
  const overlaps = found.filter((b) => b.top < a.bottom && b.bottom > a.top + 0.5).map((b) => b.bar);
  const texts = [];
  for (const el of alert.querySelectorAll("*")) {
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own || !visible(el)) continue;
    const s = getComputedStyle(el);
    texts.push({ text: el.textContent.trim().slice(0, 60), font_px: parseFloat(s.fontSize), contrast: ratio(parse(s.color).slice(0, 3), background(el)) });
  }
  const close = alert.querySelector('[data-slot="close"]');
  let closeTarget = null;
  if (close) {
    const r = close.getBoundingClientRect();
    const after = getComputedStyle(close, "::after");
    const inset = parseFloat(after.top) || 0; // `after:-inset-1.5` → -6px
    const pos = after.position;
    const grow = pos === "absolute" && inset < 0 ? -inset * 2 : 0;
    closeTarget = { box_w: Math.round(r.width), box_h: Math.round(r.height), alvo_w: Math.round(r.width + grow), alvo_h: Math.round(r.height + grow) };
  }
  return {
    alert_title: alert.textContent.trim().slice(0, 80),
    alert_top: Math.round(a.top),
    alert_bottom: Math.round(a.bottom),
    alert_left: Math.round(a.left),
    alert_right: Math.round(a.right),
    viewport_w: innerWidth,
    page_scroll_w: document.documentElement.scrollWidth,
    bars: found,
    last_bar_bottom: lastBottom,
    alert_below_all_bars: a.top + 0.5 >= lastBottom,
    overlaps,
    inside_viewport: a.left >= 0 && a.right <= innerWidth + 0.5 && document.documentElement.scrollWidth <= innerWidth,
    min_contrast: texts.length ? Math.min(...texts.map((t) => t.contrast)) : null,
    texts,
    close_target: closeTarget,
  };
}

const cfg = APPS[app];
const browser = await chromium.launch({ executablePath: process.env.KITAVISO_CHROME });
const summary = [];
for (const vp of VIEWPORTS) {
  for (const theme of THEMES) {
    const context = await browser.newContext({ baseURL, viewport: { width: vp.width, height: vp.height }, colorScheme: theme, reducedMotion: "reduce" });
    const page = await context.newPage();
    await page.addInitScript(([value, key]) => {
      localStorage.setItem("nuxt-color-mode", value);
      localStorage.setItem(key, value);
    }, [theme, cfg.key]);
    await cfg.before(page);
    await page.goto(cfg.route);
    await page.locator(cfg.ready).first().waitFor({ state: "visible", timeout: 30_000 });
    if (cfg.step) await cfg.step(page, vp);
    try {
      await page.locator("[data-page-header-alert]").first().waitFor({ state: "visible", timeout: 15_000 });
    } catch {}
    await page.waitForTimeout(1200);
    await page.evaluate(() => document.fonts.ready);
    const name = `${app}-${vp.id}-${theme}-${side}`;
    await page.screenshot({ path: join(outDir, `${name}.png`) });
    const result = await page.evaluate(audit, BARS);
    writeFileSync(join(outDir, `${name}.audit.json`), JSON.stringify(result, null, 2));
    summary.push({ name, ...result, texts: undefined });
    await context.close();
  }
}
await browser.close();
for (const s of summary) {
  console.log(
    s.name,
    s.error ?? `alert_top=${s.alert_top} last_bar_bottom=${s.last_bar_bottom} below=${s.alert_below_all_bars} overlaps=${JSON.stringify(s.overlaps)} inside=${s.inside_viewport} contrast_min=${s.min_contrast} x=${JSON.stringify(s.close_target)}`,
  );
}
