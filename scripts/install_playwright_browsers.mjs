#!/usr/bin/env node
// Instala os motores do Playwright declarados por uma superfície, com teto
// por tentativa e nova tentativa. Roda no diretório do app (usa o `npx` dele).
//
//   node ../../scripts/install_playwright_browsers.mjs "chromium webkit" --with-deps
//
// Por que existe (06/11/2026): o `npx playwright install --with-deps chromium
// webkit` do production-nuxt travou três vezes no mesmo dia. Não era o
// Playwright: as 181 dependências de sistema do WebKit (114 MB de .deb) vinham
// do espelho azure.archive.ubuntu.com a 47 kB/s, 40 minutos de download, e o
// job morria no `timeout-minutes: 45` como CANCELLED, sem teste reprovado.
// O download dos navegadores em si leva 13 segundos.
//
// O que este script faz no lugar do comando único:
// 1. dependências de sistema (só Linux, só com --with-deps) em passo próprio,
//    reaproveitando os .deb guardados no cache do workflow;
// 2. cada tentativa tem teto; estourou, mata o grupo de processos e tenta de
//    novo, a partir da segunda com o archive.ubuntu.com à frente do espelho
//    da Azure (lento não é falha para o apt, ele nunca troca sozinho);
// 3. os navegadores (CDN do Playwright) com o mesmo teto e nova tentativa.
// Falha gritando depois da última tentativa: o job fica vermelho em minutos,
// com a causa no log, em vez de cancelado aos 45.

import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync } from "node:fs";
import { homedir, platform } from "node:os";
import { join } from "node:path";

const args = process.argv.slice(2);
const withDeps = args.includes("--with-deps");
const engines = (args.find((arg) => !arg.startsWith("--")) ?? "chromium").split(/\s+/).filter(Boolean);

const ATTEMPTS = 3;
const DEPS_TIMEOUT_MS = Number(process.env.PLAYWRIGHT_DEPS_TIMEOUT_MS ?? 5 * 60_000);
const BROWSER_TIMEOUT_MS = Number(process.env.PLAYWRIGHT_BROWSER_TIMEOUT_MS ?? 3 * 60_000);
const DEB_CACHE = process.env.PLAYWRIGHT_APT_CACHE ?? join(homedir(), ".cache", "playwright-apt");
const APT_ARCHIVES = "/var/cache/apt/archives";
const APT_MIRRORS = "/etc/apt/apt-mirrors.txt";
const FALLBACK_MIRROR = "http://archive.ubuntu.com/ubuntu/";

const log = (message) => console.log(`[playwright-install] ${message}`);

function sh(command) {
  const result = spawnSync("bash", ["-c", command], { stdio: "inherit" });
  return result.status === 0;
}

function runWithTimeout(command, commandArgs, timeoutMs) {
  return new Promise((resolve) => {
    const started = Date.now();
    // detached: o filho lidera um grupo de processos próprio, e o kill alcança
    // npx → playwright → sudo → apt-get de uma vez.
    const child = spawn(command, commandArgs, { stdio: "inherit", detached: true });
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      log(`teto de ${Math.round(timeoutMs / 1000)}s estourado; encerrando a tentativa`);
      try { process.kill(-child.pid, "SIGTERM"); } catch {}
      setTimeout(() => { try { process.kill(-child.pid, "SIGKILL"); } catch {} }, 15_000).unref();
    }, timeoutMs);
    child.on("exit", (code) => {
      clearTimeout(timer);
      log(`${command} ${commandArgs.join(" ")} → ${timedOut ? "teto" : `saída ${code}`} em ${Math.round((Date.now() - started) / 1000)}s`);
      resolve(!timedOut && code === 0);
    });
  });
}

function preferFallbackMirror() {
  if (!existsSync(APT_MIRRORS)) return;
  const current = readFileSync(APT_MIRRORS, "utf8");
  if (current.trimStart().startsWith(FALLBACK_MIRROR)) return;
  log(`pondo ${FALLBACK_MIRROR} à frente em ${APT_MIRRORS}`);
  sh(`{ echo '${FALLBACK_MIRROR}'; grep -v '^${FALLBACK_MIRROR}' ${APT_MIRRORS}; } | sudo tee ${APT_MIRRORS}.new >/dev/null && sudo mv ${APT_MIRRORS}.new ${APT_MIRRORS}`);
}

function cleanUpInterruptedApt() {
  // A tentativa morta pode ter deixado o apt-get vivo (sudo) ou o dpkg no meio.
  sh("sudo pkill -x apt-get || true; sleep 2; sudo dpkg --configure -a || true");
}

async function installSystemDeps() {
  mkdirSync(DEB_CACHE, { recursive: true });
  const cached = readdirSync(DEB_CACHE).filter((name) => name.endsWith(".deb"));
  log(`${cached.length} pacotes .deb no cache do workflow`);
  if (cached.length) sh(`sudo cp ${JSON.stringify(DEB_CACHE)}/*.deb ${APT_ARCHIVES}/`);
  // O apt-get guarda os .deb por padrão; a linha garante, caso a imagem mude.
  sh(`echo 'APT::Keep-Downloaded-Packages "true";' | sudo tee /etc/apt/apt.conf.d/99-keep-playwright-debs >/dev/null`);

  for (let attempt = 1; attempt <= ATTEMPTS; attempt++) {
    log(`dependências de sistema, tentativa ${attempt}/${ATTEMPTS}`);
    if (attempt > 1) {
      cleanUpInterruptedApt();
      preferFallbackMirror();
    }
    if (await runWithTimeout("npx", ["playwright", "install-deps", ...engines], DEPS_TIMEOUT_MS)) {
      sh(`cp ${APT_ARCHIVES}/*.deb ${JSON.stringify(DEB_CACHE)}/ 2>/dev/null || true`);
      log(`${readdirSync(DEB_CACHE).filter((name) => name.endsWith(".deb")).length} pacotes .deb guardados para o próximo run`);
      return true;
    }
  }
  return false;
}

async function installBrowsers() {
  for (let attempt = 1; attempt <= ATTEMPTS; attempt++) {
    log(`navegadores (${engines.join(", ")}), tentativa ${attempt}/${ATTEMPTS}`);
    if (await runWithTimeout("npx", ["playwright", "install", ...engines], BROWSER_TIMEOUT_MS)) return true;
  }
  return false;
}

if (withDeps && platform() === "linux") {
  if (!(await installSystemDeps())) {
    console.error(`::error::dependências de sistema do Playwright não instalaram em ${ATTEMPTS} tentativas de ${DEPS_TIMEOUT_MS / 60_000} min (espelho apt lento ou fora do ar)`);
    process.exit(1);
  }
}
if (!(await installBrowsers())) {
  console.error(`::error::navegadores do Playwright (${engines.join(", ")}) não baixaram em ${ATTEMPTS} tentativas`);
  process.exit(1);
}
