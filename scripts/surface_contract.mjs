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

function matrix(kind) {
  const include = entries
    .filter(([, surface]) =>
      kind === "quality" ||
      (kind === "pwa" && surface.capabilities?.pwa) ||
      (kind === "audit" && surface.capabilities?.npmAudit),
    )
    .map(([id, surface]) => ({
      id,
      dir: surface.dir,
      kind: surface.kind,
      install_layer: surface.kind === "operator",
      runner: surface.runner ?? "ubuntu-latest",
      component: Boolean(surface.commands?.component),
      python_mock: Boolean(surface.pythonMock),
      catalog: Boolean(surface.capabilities?.catalog),
      visual: Boolean(surface.capabilities?.visual),
      geometry: Boolean(surface.capabilities?.geometry),
      browser: Boolean(surface.capabilities?.browser),
      browser_suite: Boolean(surface.capabilities?.browserSuite),
      a11y: Boolean(surface.capabilities?.a11y),
      security: Boolean(surface.capabilities?.security),
      ssr: Boolean(surface.capabilities?.ssr),
      pwa_browser: Boolean(surface.capabilities?.pwaBrowser),
      browser_install: surface.browserEngines
        ? `npx playwright install${surface.browserWithDeps ? " --with-deps" : ""} ${surface.browserEngines}`
        : "npx playwright install chromium",
    }));
  process.stdout.write(JSON.stringify({ include }));
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

const [command, ...args] = process.argv.slice(2);
if (command === "validate") validate();
else if (command === "matrix") matrix(args[0] ?? "quality");
else if (command === "run") run(args[0], args[1]);
else fail(["uso: surface_contract.mjs validate | matrix quality|pwa | run <id> <phase>"]);
