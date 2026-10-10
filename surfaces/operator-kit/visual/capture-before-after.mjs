// Harness de captura ANTES/DEPOIS da migração Nuxt UI (WP-OPERADOR-NUXTUI-ONDAS, §7).
// Não é baseline: retrato de regressão por PR, para ver com os olhos o que mudou.
// Build de produção do app contra o mock dele; 5 larguras × claro/escuro; cenários com
// passos (abrir popover, diálogo); um JSON com o console de cada captura.
//
// Uso (uma worktree por lado; a de "antes" pode ligar os node_modules por symlink):
//   node surfaces/operator-kit/visual/capture-before-after.mjs <raiz-da-worktree> <app> <antes|depois> <porta-app> <porta-mock> <pasta-saída>
//   python3 surfaces/operator-kit/visual/capture-diff.py <pasta-saída>   # ordena os pares pelo que mudou
// REBUILD=1 força o `nuxt build`. Rode UM build por vez: builds simultâneos dividem
// caches (o Kitchen Sink builda em node_modules/.cache) e o retrato sai misturado.
// Um app entra no CONFIG com o mock dele e os cenários; mock incompleto esconde defeito.
// A configuração por app mora em CONFIG abaixo.
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createRequire } from "node:module";

const [tree, app, side, appPort, mockPort, outDir] = process.argv.slice(2);
const require = createRequire(join(tree, "surfaces/orders-nuxt/package.json"));
const { chromium } = require("playwright");

const WIDTHS = [390, 768, 1024, 1280, 1440];
const THEMES = ["light", "dark"];
const authed = [{ name: "e2e_session", value: "authed" }];

// Cada cenário: rota, cookies, passos (lista de {click|wait|press}).
const CONFIG = {
  "hub-nuxt": { mock: "tests/e2e/mockBackend.mjs", scenarios: [{ id: "home", route: "/" }] },
  "pos-nuxt": {
    mock: "tests/visual/mockBackend.mjs",
    env: { POS_VISUAL_CLIENT_ONLY: "1" },
    scenarios: [
      { id: "preorders", route: "/preorders" },
      { id: "preorders-filtro", route: "/preorders", steps: [{ click: "[data-filter-trigger]" }] },
    ],
  },
  "pos-nuxt:login": { dir: "pos-nuxt", mock: "tests/e2e/mockBackend.mjs", scenarios: [{ id: "login", route: "/" }] },
  "kds-nuxt": {
    mock: "tests/e2e/mockBackend.mjs",
    scenarios: [{ id: "stations", route: "/", cookies: authed }, { id: "login", route: "/" }],
  },
  "production-nuxt": {
    mock: "tests/e2e/mockBackend.mjs",
    scenarios: [
      { id: "abertura", route: "/", cookies: authed },
      { id: "plan", route: "/plan", cookies: authed },
      { id: "login", route: "/" },
    ],
  },
  "orders-nuxt": {
    mock: "tests/visual/mockBackend.mjs",
    scenarios: [{ id: "board", route: "/" }, { id: "history", route: "/history" }, { id: "catalog", route: "/catalog" }],
  },
  "marketing-nuxt": {
    mock: "tests/visual/mock_backend.py",
    scenarios: [{ id: "home", route: "/" }, { id: "campaigns", route: "/campaigns" }],
  },
  "bi-nuxt": { mock: "../pos-nuxt/tests/e2e/mockBackend.mjs", scenarios: [{ id: "login", route: "/" }] },
  "purchase-nuxt": { mock: "../pos-nuxt/tests/e2e/mockBackend.mjs", scenarios: [{ id: "login", route: "/" }] },
  "kitchensink-nuxt": { mock: "../pos-nuxt/tests/e2e/mockBackend.mjs", scenarios: [{ id: "catalog", route: "/" }] },
};

const cfg = CONFIG[app];
const dir = join(tree, "surfaces", cfg.dir ?? app);
const env = {
  ...process.env,
  NUXT_APP_BASE_URL: "/",
  NUXT_DJANGO_BASE_URL: `http://127.0.0.1:${mockPort}`,
  NUXT_PUBLIC_DJANGO_BASE_URL: `http://127.0.0.1:${mockPort}`,
  SHOPMAN_ENVIRONMENT: "test",
  SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM: "1",
  NUXT_IGNORE_LOCK: "1",
  MOCK_PORT: String(mockPort),
  ...(cfg.env ?? {}),
};

function log(msg) { console.log(`[${side}:${app}] ${msg}`); }

if (!existsSync(join(dir, ".output/server/index.mjs")) || process.env.REBUILD) {
  log("build");
  const b = spawnSync("npx", ["nuxt", "build"], { cwd: dir, env, encoding: "utf8" });
  if (b.status !== 0) { console.error(b.stdout.slice(-3000), b.stderr.slice(-3000)); process.exit(1); }
}

const mockCmd = cfg.mock.endsWith(".py") ? ["python3", [cfg.mock, String(mockPort)]] : ["node", [cfg.mock]];
const mock = spawn(mockCmd[0], mockCmd[1], { cwd: dir, env, stdio: "ignore" });
const server = spawn("node", [".output/server/index.mjs"], {
  cwd: dir, env: { ...env, PORT: String(appPort), NITRO_PORT: String(appPort), HOST: "127.0.0.1", NITRO_HOST: "127.0.0.1" }, stdio: "ignore",
});
const base = `http://127.0.0.1:${appPort}`;
for (let i = 0; i < 120; i++) {
  try { const r = await fetch(base + "/"); if (r.status < 600) break; } catch { /* sobe */ }
  await new Promise((r) => setTimeout(r, 500));
}

const report = [];
const browser = await chromium.launch();
try {
  for (const sc of cfg.scenarios) {
    for (const theme of THEMES) {
      for (const width of WIDTHS) {
        const ctx = await browser.newContext({
          viewport: { width, height: width < 768 ? 844 : width < 1024 ? 1024 : 900 },
          colorScheme: theme, locale: "pt-BR", timezoneId: "America/Sao_Paulo",
          reducedMotion: "reduce", serviceWorkers: "block",
          hasTouch: width <= 1024, isMobile: width < 768,
        });
        await ctx.addInitScript(([t, key]) => { try { localStorage.setItem("nuxt-color-mode", t); localStorage.setItem(key, t); } catch { /* armazenamento bloqueado: segue claro */ } }, [theme, `${cfg.dir ?? app}-color-mode`]);
        if (sc.cookies) await ctx.addCookies(sc.cookies.map((c) => ({ ...c, url: base })));
        const page = await ctx.newPage();
        const consoleMsgs = [];
        page.on("console", (m) => { if (["error", "warning"].includes(m.type())) consoleMsgs.push(`${m.type()}: ${m.text().slice(0, 300)}`); });
        page.on("pageerror", (e) => consoleMsgs.push(`pageerror: ${String(e).slice(0, 300)}`));
        let status = 0;
        try {
          const resp = await page.goto(base + sc.route, { waitUntil: "networkidle", timeout: 60000 });
          status = resp?.status() ?? 0;
          await page.waitForTimeout(800);
          for (const step of sc.steps ?? []) {
            if (step.click) await page.locator(step.click).first().click({ timeout: 10000 });
            if (step.press) await page.keyboard.press(step.press);
            await page.waitForTimeout(step.wait ?? 600);
          }
        } catch (e) { consoleMsgs.push(`capture-error: ${String(e).slice(0, 300)}`); }
        mkdirSync(outDir, { recursive: true });
        const file = `${app.replace(":", "-")}__${sc.id}__${width}__${theme}__${side}.png`;
        await page.screenshot({ path: join(outDir, file), fullPage: true }).catch(() => {});
        report.push({ app, scenario: sc.id, width, theme, side, status, file, console: consoleMsgs });
        await ctx.close();
      }
    }
  }
} finally {
  await browser.close();
  server.kill(); mock.kill();
}
writeFileSync(join(outDir, `${app.replace(":", "-")}__${side}.json`), JSON.stringify(report, null, 2));
log(`ok ${report.length} capturas`);
