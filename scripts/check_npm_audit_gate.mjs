#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const SEVERITY = new Map([
  ["info", 0],
  ["low", 1],
  ["moderate", 2],
  ["high", 3],
  ["critical", 4],
]);

function usage() {
  console.error(
    "Uso: node scripts/check_npm_audit_gate.mjs --audit-level=high --allowlist=surfaces/npm-audit-allowlist.json",
  );
}

function parseArgs(argv) {
  const args = { auditLevel: "high", allowlist: "" };
  for (const arg of argv) {
    if (arg.startsWith("--audit-level=")) args.auditLevel = arg.slice("--audit-level=".length);
    else if (arg.startsWith("--allowlist=")) args.allowlist = arg.slice("--allowlist=".length);
    else {
      usage();
      process.exit(2);
    }
  }
  if (!SEVERITY.has(args.auditLevel) || !args.allowlist) {
    usage();
    process.exit(2);
  }
  return args;
}

function ghsaFrom(url = "") {
  return url.match(/GHSA-[a-z0-9-]+/i)?.[0] ?? "";
}

function collectAdvisories(vulnerabilities, packageName, seen = new Set()) {
  if (seen.has(packageName)) return [];
  seen.add(packageName);

  const vulnerability = vulnerabilities[packageName];
  if (!vulnerability) return [];

  const advisories = [];
  for (const via of vulnerability.via ?? []) {
    if (typeof via === "string") {
      advisories.push(...collectAdvisories(vulnerabilities, via, seen));
    } else if (via && typeof via === "object") {
      advisories.push({
        id: String(via.source ?? ""),
        ghsa: ghsaFrom(via.url),
        name: via.name,
        severity: via.severity,
        title: via.title,
        url: via.url,
        range: via.range,
      });
    }
  }
  return advisories;
}

function uniqueAdvisories(advisories) {
  const byKey = new Map();
  for (const advisory of advisories) {
    const key = advisory.ghsa || advisory.id || advisory.url;
    if (key) byKey.set(key, advisory);
  }
  return [...byKey.values()];
}

function loadAllowlist(path) {
  const parsed = JSON.parse(readFileSync(resolve(path), "utf8"));
  return new Map((parsed.allowedAdvisories ?? []).map((item) => [item.ghsa, item]));
}

function isExpired(expiresOn) {
  const expires = Date.parse(`${expiresOn}T23:59:59Z`);
  return Number.isFinite(expires) && Date.now() > expires;
}

const args = parseArgs(process.argv.slice(2));
const threshold = SEVERITY.get(args.auditLevel);
const allowlist = loadAllowlist(args.allowlist);

const audit = spawnSync("npm", ["audit", `--audit-level=${args.auditLevel}`, "--json"], {
  encoding: "utf8",
  stdio: ["ignore", "pipe", "pipe"],
});

const raw = audit.stdout || audit.stderr;
let report;
try {
  report = raw.trim() ? JSON.parse(raw) : {};
} catch (error) {
  console.error("npm audit não retornou JSON válido.");
  console.error(raw);
  process.exit(audit.status || 1);
}

const vulnerabilities = report.vulnerabilities ?? {};
const blocked = [];
const allowed = [];

for (const [packageName, vulnerability] of Object.entries(vulnerabilities)) {
  if ((SEVERITY.get(vulnerability.severity) ?? -1) < threshold) continue;

  const advisories = uniqueAdvisories(collectAdvisories(vulnerabilities, packageName));
  const unknown = advisories.filter((advisory) => !allowlist.has(advisory.ghsa));
  const expired = advisories.filter((advisory) => {
    const entry = allowlist.get(advisory.ghsa);
    return entry && isExpired(entry.expiresOn);
  });

  if (!advisories.length || unknown.length || expired.length) {
    blocked.push({ packageName, vulnerability, advisories, unknown, expired });
  } else {
    allowed.push({ packageName, vulnerability, advisories });
  }
}

for (const item of allowed) {
  const labels = item.advisories.map((advisory) => advisory.ghsa).join(", ");
  console.warn(`Permitido temporariamente: ${item.packageName} (${item.vulnerability.severity}) via ${labels}`);
}

if (blocked.length) {
  console.error("npm audit encontrou vulnerabilidades sem exceção válida:");
  for (const item of blocked) {
    console.error(`- ${item.packageName} (${item.vulnerability.severity})`);
    for (const advisory of item.advisories) {
      const status = item.unknown.includes(advisory)
        ? "sem allowlist"
        : item.expired.includes(advisory)
          ? "allowlist vencida"
          : "indireta";
      console.error(`  ${advisory.ghsa || advisory.id || advisory.url}: ${status}. ${advisory.title ?? ""}`);
    }
    if (!item.advisories.length) console.error("  Sem advisory folha identificável no relatório do npm.");
  }
  process.exit(1);
}

if (allowed.length) {
  console.warn("npm audit passou com exceções temporárias rastreadas.");
} else {
  console.log(`npm audit passou sem vulnerabilidades ${args.auditLevel}+.`);
}
