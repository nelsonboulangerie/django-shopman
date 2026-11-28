#!/usr/bin/env node

import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const root = resolve(import.meta.dirname, "..");
const contract = JSON.parse(readFileSync(resolve(root, "surfaces/contracts.json"), "utf8"));
const registry = JSON.parse(readFileSync(resolve(root, "surfaces/registry.json"), "utf8"));
const entries = Object.entries(contract.surfaces);

function fail(messages) {
  for (const message of messages) console.error(`[surface-contract] ${message}`);
  process.exit(1);
}

function validate() {
  const errors = [];
  const expected = new Set(["operator-kit", ...Object.keys(registry.surfaces)]);
  const actual = new Set(entries.map(([id]) => id));
  for (const id of expected) if (!actual.has(id)) errors.push(`manifesto sem ${id}`);
  for (const id of actual) if (!expected.has(id)) errors.push(`manifesto contém app desconhecido ${id}`);

  for (const [id, surface] of entries) {
    if (id !== "operator-kit" && registry.surfaces[id]?.dir !== surface.dir)
      errors.push(`${id}: diretório diverge de surfaces/registry.json`);
    if (id !== "operator-kit" && registry.surfaces[id]?.kind !== surface.kind)
      errors.push(`${id}: kind diverge de surfaces/registry.json`);
    const pkgPath = resolve(root, "surfaces", surface.dir, "package.json");
    let scripts = {};
    try { scripts = JSON.parse(readFileSync(pkgPath, "utf8")).scripts ?? {}; }
    catch { errors.push(`${id}: package.json ausente ou inválido`); continue; }
    for (const [phase, script] of Object.entries(surface.commands ?? {}))
      if (!scripts[script]) errors.push(`${id}: fase ${phase} aponta para script ausente ${script}`);
    // Retrato de pixel preso a um navegador/SO (`visualRunner`, hoje macos-15)
    // roda fora do check obrigatório, no workflow `surfaces-visual-pinned.yml`.
    if (surface.visualRunner && !surface.capabilities?.visual)
      errors.push(`${id}: visualRunner sem capability visual`);
    if (surface.runner)
      errors.push(`${id}: runner próprio no check obrigatório; retrato preso a SO usa visualRunner (docs/reference/ci-escopo.md)`);
    if (id !== "operator-kit") {
      let hasComponentTests = false;
      try {
        hasComponentTests = readdirSync(
          resolve(root, "surfaces", surface.dir, "tests/components"),
          { recursive: true },
        ).some((name) => String(name).endsWith(".test.ts"));
      } catch {}
      if (Boolean(surface.commands?.component) !== hasComponentTests)
        errors.push(`${id}: fase component deve refletir a existência de tests/components/*.test.ts`);
    }
    for (const [capability, script] of Object.entries(surface.capabilities ?? {}))
      if (typeof script === "string" && !scripts[script])
        errors.push(`${id}: capability ${capability} aponta para script ausente ${script}`);
    for (const exception of surface.exceptions ?? []) {
      if (!exception.reason || !exception.owner || !exception.expires)
        errors.push(`${id}: exceção ${exception.capability} precisa de motivo, owner e expiração`);
      else if (Date.parse(`${exception.expires}T23:59:59Z`) < Date.now())
        errors.push(`${id}: exceção ${exception.capability} venceu em ${exception.expires}`);
    }
    if (surface.capabilities?.visual) {
      const visual = readFileSync(resolve(root, "surfaces", surface.dir, surface.visualConfig ?? "playwright.visual.config.ts"), "utf8");
      const executableVisual = visual.replace(/^\s*\/\/.*$/gm, "");
      if (/\bnuxt\s+dev\b/.test(executableVisual)) errors.push(`${id}: gate visual ainda usa nuxt dev`);
      if (!/\bnuxt\s+build\b/.test(visual) && id !== "operator-kit")
        errors.push(`${id}: gate visual não constrói artefato de produção`);
    }
    errors.push(...validateConcurrent(id, surface, scripts));
    const signatures = surface.signatureViews ?? [];
    if (signatures.length > contract.policy.maxSignatureViews)
      errors.push(`${id}: ${signatures.length} assinaturas excedem o teto ${contract.policy.maxSignatureViews}`);
    const baselineDir = resolve(root, "surfaces", surface.dir, "tests/visual/baselines");
    let baselines = [];
    try { baselines = readdirSync(baselineDir).filter((name) => name.endsWith(".png")); } catch {}
    const declared = new Set(signatures);
    for (const baseline of baselines)
      if (!declared.has(baseline)) errors.push(`${id}: baseline sem assinatura declarada ${baseline}`);
    for (const signature of declared)
      if (!baselines.includes(signature)) errors.push(`${id}: assinatura declarada sem baseline ${signature}`);
  }
  const workflow = readFileSync(resolve(root, ".github/workflows/surfaces-gate.yml"), "utf8");
  for (const match of workflow.matchAll(/matrix\.(?:app|surface)\s*(?:==|!=)\s*['"][^'"]+['"]/g))
    errors.push(`workflow condiciona por nome: ${match[0]}`);
  if (errors.length) fail(errors);
  console.log(`[surface-contract] ${entries.length} superfícies válidas; visual sempre usa build de produção`);
}

// ── Fases de navegador AO MESMO TEMPO (DEV-2026-098) ─────────────────────
// Medido em 25/11/2026: o `pos-nuxt` é o caminho crítico do Surfaces Gate (14,6 min),
// com geometria (6,2) e navegador (3,9) uma depois da outra. Cada uma sobe o PRÓPRIO
// mock e o PRÓPRIO app, em portas próprias: podem correr juntas. O app declara
// `concurrentPhases`, e a declaração só vale se for segura por construção:
//   * toda fase é capability com script próprio (e de navegador);
//   * as portas padrão dos configs do Playwright não se repetem entre as fases;
//   * os `outputDir` não se repetem nem se aninham (o Playwright LIMPA o seu ao começar).
// Fase sem config legível, ou config sem porta declarada, reprova: segurança
// que não se prova não se declara.
const BROWSER_PHASES = new Set(["geometry", "browser", "a11y", "security"]);

function playwrightConfigFor(dir, script) {
  const match = /playwright\s+test(?:.*?\s-c\s+(\S+))?/.exec(script ?? "");
  if (!match) return null;
  return resolve(root, "surfaces", dir, match[1] ?? "playwright.config.ts");
}

function concurrencyFootprint(dir, script) {
  const path = playwrightConfigFor(dir, script);
  if (!path) return null;
  let text;
  try { text = readFileSync(path, "utf8"); } catch { return null; }
  const code = text.replace(/^\s*\/\/.*$/gm, "");
  const ports = [...code.matchAll(/\|\|\s*(\d{4,5})\b/g)].map((m) => m[1]);
  const out = /outputDir:\s*["'`]([^"'`]+)["'`]/.exec(code)?.[1] ?? "test-results";
  return { ports, outputDir: out.replace(/^\.\//, "").replace(/\/$/, "") };
}

function validateConcurrent(id, surface, scripts) {
  const phases = surface.concurrentPhases;
  if (!phases) return [];
  const errors = [];
  if (!Array.isArray(phases) || phases.length < 2) return [`${id}: concurrentPhases precisa de duas fases ou mais`];
  const seen = [];
  for (const phase of phases) {
    const script = surface.capabilities?.[phase];
    if (!BROWSER_PHASES.has(phase)) { errors.push(`${id}: concurrentPhases só aceita fases de navegador (${phase})`); continue; }
    if (typeof script !== "string") { errors.push(`${id}: concurrentPhases ${phase} sem capability com script`); continue; }
    const footprint = concurrencyFootprint(surface.dir, scripts[script]);
    if (!footprint || footprint.ports.length === 0) {
      errors.push(`${id}: concurrentPhases ${phase}: não consigo provar as portas do config do Playwright`);
      continue;
    }
    for (const other of seen) {
      const shared = footprint.ports.filter((p) => other.ports.includes(p));
      if (shared.length) errors.push(`${id}: ${phase} e ${other.phase} disputam a porta ${shared.join(", ")}`);
      const a = footprint.outputDir, b = other.outputDir;
      if (a === b || a.startsWith(`${b}/`) || b.startsWith(`${a}/`))
        errors.push(`${id}: ${phase} (${a}) e ${other.phase} (${b}) dividem/aninham outputDir; o Playwright limpa o seu ao começar`);
    }
    seen.push({ phase, ...footprint });
  }
  return errors;
}

function matrix(kind) {
  const include = entries
    .filter(([, surface]) =>
      kind === "quality" ||
      (kind === "pwa" && surface.capabilities?.pwa) ||
      (kind === "audit" && surface.capabilities?.npmAudit) ||
      (kind === "visual-pinned" && surface.visualRunner),
    )
    .map(([id, surface]) => ({
      id,
      dir: surface.dir,
      kind: surface.kind,
      install_layer: id === "operator-kit" || Boolean(registry.surfaces[id]?.uses_operator_kit),
      runner: kind === "visual-pinned" ? surface.visualRunner : "ubuntu-latest",
      component: Boolean(surface.commands?.component),
      python_mock: Boolean(surface.pythonMock),
      catalog: Boolean(surface.capabilities?.catalog),
      // O check obrigatório (`quality`) não roda retrato preso a SO: ele mora no
      // `surfaces-visual-pinned.yml`, fora do caminho da fila.
      visual: Boolean(surface.capabilities?.visual) && (kind === "visual-pinned" || !surface.visualRunner),
      geometry: Boolean(surface.capabilities?.geometry),
      browser: Boolean(surface.capabilities?.browser),
      browser_suite: Boolean(surface.capabilities?.browserSuite),
      a11y: Boolean(surface.capabilities?.a11y),
      security: Boolean(surface.capabilities?.security),
      ssr: Boolean(surface.capabilities?.ssr),
      pwa_browser: Boolean(surface.capabilities?.pwaBrowser),
      browser_engines: surface.browserEngines ?? "chromium",
      browser_with_deps: Boolean(surface.browserWithDeps),
    }))
    .map((entry) => (kind === "quality" ? scoped(entry) : entry))
    .map((entry) => (kind === "quality" ? withConcurrent(entry) : entry));
  process.stdout.write(JSON.stringify({ include }));
}

// `concurrent`: as fases declaradas em `concurrentPhases` que ESTA entrada da
// matriz vai rodar (no PR leve, nenhuma). O workflow pula os passos individuais
// dessas fases e roda `run-many` com elas; string vazia = tudo como sempre.
function withConcurrent(entry) {
  const declared = contract.surfaces[entry.id]?.concurrentPhases ?? [];
  const enabled = {
    geometry: entry.geometry,
    browser: entry.browser && !entry.browser_suite,
    a11y: entry.a11y && !entry.browser_suite,
    security: entry.security,
  };
  const phases = entry.skip ? [] : declared.filter((phase) => enabled[phase]);
  return { ...entry, concurrent: phases.length >= 2 ? phases.join(" ") : "" };
}

// Escopo da CI (docs/reference/ci-escopo.md). A matriz `quality` sai SEMPRE com
// todas as superfícies: o nome de cada app é check obrigatório do `main`, e app
// que some da matriz nunca reporta e trava o PR. O que muda é o que cada entrada
// faz. No pull_request (CI_HEAVY=false) roda só o leve (unit, component, lint,
// typecheck, em Linux) e só nos apps que o PR tocou (CI_SURFACES, lista JSON ou `all`); o
// resto sai com `skip`, verde em segundos e no runner Linux. Navegador, visual,
// geometria, a11y, segurança e catálogo rodam na fila (merge_group), sem filtro.
// Sem as variáveis (rodada local, push, fila) a matriz é a de sempre.
function scoped(entry) {
  const heavy = process.env.CI_HEAVY !== "false";
  const raw = process.env.CI_SURFACES || "all";
  const wanted = raw === "all" ? null : new Set(JSON.parse(raw));
  if (heavy && !wanted) return { ...entry, skip: false };
  const light = {
    ...entry,
    skip: false,
    python_mock: false,
    catalog: false,
    visual: false,
    geometry: false,
    browser: false,
    browser_suite: false,
    a11y: false,
    security: false,
  };
  const out = heavy ? { ...entry, skip: false } : light;
  if (wanted && !wanted.has(entry.dir)) return { ...out, skip: true, component: false };
  return out;
}

// Combinações de navegador que a matriz `quality` instala em Linux, uma por chave
// de cache (motores + dependências de sistema), com um app que as tem. Usada pelo
// `playwright-cache-main.yml`, que grava o cache no `main`: grupo da fila
// (`gh-readonly-queue/...`) só lê cache do próprio ref e do `main`.
function browsers() {
  const seen = new Map();
  for (const [, surface] of entries) {
    const caps = surface.capabilities ?? {};
    const usesBrowser = caps.visual || caps.geometry || caps.browser || caps.browserSuite || caps.a11y;
    if (!usesBrowser || surface.runner) continue;
    const engines = surface.browserEngines ?? "chromium";
    const withDeps = Boolean(surface.browserWithDeps);
    const key = `${engines}|${withDeps}`;
    if (!seen.has(key)) seen.set(key, { dir: surface.dir, browser_engines: engines, browser_with_deps: withDeps });
  }
  process.stdout.write(JSON.stringify({ include: [...seen.values()] }));
}

function run(id, phase) {
  const surface = contract.surfaces[id];
  if (!surface) fail([`app desconhecido: ${id}`]);
  const script = surface.commands?.[phase] ?? surface.capabilities?.[phase];
  if (!script || typeof script !== "string") fail([`${id} não declara a fase/capability ${phase}`]);
  const result = spawnSync("npm", ["run", script], {
    cwd: resolve(root, "surfaces", surface.dir),
    env: { ...process.env, ...(surface.environment?.[phase] ?? {}) },
    stdio: "inherit",
  });
  process.exit(result.status ?? 1);
}

// As fases declaradas em `concurrentPhases`, ao mesmo tempo. Cada linha sai com
// o prefixo da fase; reprova se QUALQUER uma reprovar, e diz quais.
async function runMany(id, phases) {
  const { spawn } = await import("node:child_process");
  const surface = contract.surfaces[id];
  if (!surface) fail([`app desconhecido: ${id}`]);
  const declared = new Set(surface.concurrentPhases ?? []);
  const stray = phases.filter((phase) => !declared.has(phase));
  if (stray.length) fail([`${id}: ${stray.join(", ")} fora de concurrentPhases (só o declarado e validado roda junto)`]);
  const started = Date.now();
  // Largada escalonada, na ordem declarada: a fase seguinte só começa quando a
  // anterior já tem o PRIMEIRO teste resolvido. Medido em 25/11: largando juntas,
  // o `nuxt build` de uma disputou CPU com a compilação a frio do `nuxt dev` da
  // outra, e o primeiro teste da geometria estourou 120 s. O primeiro teste é o
  // que paga a compilação; depois dele a disputa é só de regime.
  const FIRST_RESULT = /^\s*(✓|✘|ok|x|-)\s+\d+\s/;
  const STAGGER_LIMIT_MS = 240_000;
  const launch = (phase) => {
    let markFirst;
    const firstResult = new Promise((resolveFirst) => { markFirst = resolveFirst; });
    const finished = new Promise((done) => {
      const script = surface.capabilities?.[phase];
      const child = spawn("npm", ["run", script], {
        cwd: resolve(root, "surfaces", surface.dir),
        env: { ...process.env, ...(surface.environment?.[phase] ?? {}) },
        stdio: ["ignore", "pipe", "pipe"],
      });
      const tag = `[${phase}] `;
      for (const stream of [child.stdout, child.stderr]) {
        let rest = "";
        stream.on("data", (chunk) => {
          const lines = (rest + chunk).split("\n");
          rest = lines.pop();
          for (const line of lines) {
            if (FIRST_RESULT.test(line)) markFirst();
            process.stdout.write(tag + line + "\n");
          }
        });
        stream.on("end", () => { if (rest) process.stdout.write(tag + rest + "\n"); });
      }
      child.on("close", (code) => {
        markFirst();
        done({ phase, code: code ?? 1, seconds: Math.round((Date.now() - started) / 1000) });
      });
    });
    return { firstResult, finished };
  };
  const running = [];
  for (const [i, phase] of phases.entries()) {
    if (i > 0) {
      const previous = running[i - 1].firstResult;
      await Promise.race([previous, new Promise((r) => setTimeout(r, STAGGER_LIMIT_MS))]);
      console.log(`[surface-contract] ${id}: ${phase} larga aos ${Math.round((Date.now() - started) / 1000)}s`);
    }
    running.push(launch(phase));
  }
  const results = await Promise.all(running.map((r) => r.finished));
  for (const r of results) console.log(`[surface-contract] ${id} ${r.phase}: ${r.code === 0 ? "verde" : `REPROVOU (${r.code})`} em ${r.seconds}s`);
  process.exit(results.some((r) => r.code !== 0) ? 1 : 0);
}

const [command, ...args] = process.argv.slice(2);
if (command === "validate") validate();
else if (command === "matrix" && args[0] === "browsers") browsers();
else if (command === "matrix") matrix(args[0] ?? "quality");
else if (command === "run") run(args[0], args[1]);
else if (command === "run-many") runMany(args[0], args.slice(1));
else fail(["uso: surface_contract.mjs validate | matrix quality|pwa|audit|visual-pinned | run <id> <phase> | run-many <id> <phase...>"]);
