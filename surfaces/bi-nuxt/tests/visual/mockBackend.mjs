import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

// Backend hermético da matriz visual do B.I. Sem Django, sem dados vivos: as respostas
// foram GRAVADAS do Django real (seed Nelson, sintético, 08/10/2026) por um proxy entre
// o app e o servidor, com as 8 telas percorridas no desktop e no celular. O mock só
// repete o gravado: casa pelo caminho com a query e, sem ela, só pelo caminho (o mesmo
// `recordedFor` do Gestor). Para regravar, ver tests/visual/README.md.
//
// Cenário por GET /__visual/scenario?set=<normal|empty|error>:
//   normal → o gravado; empty → as leituras do B.I. sem linhas (o estado vazio de cada
//   tela); error → 500 nas leituras do B.I. (o "Tentar de novo"). Sessão, posto e avisos
//   seguem o gravado nos três.

const here = dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.MOCK_PORT || 38794);
const recorded = JSON.parse(readFileSync(join(here, "fixtures", "recorded-django.json"), "utf8"));

function recordedFor(url) {
  const exact = recorded[url.pathname + url.search];
  if (exact) return exact;
  const key = Object.keys(recorded).find((k) => k.split("?")[0] === url.pathname);
  return key ? recorded[key] : null;
}

/** A mesma forma, sem linhas: listas vazias e números zerados, para o estado vazio. */
function emptied(value) {
  if (Array.isArray(value)) return [];
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, emptied(v)]));
  }
  if (typeof value === "number") return 0;
  return value;
}

let scenario = "normal";

function send(res, status, body) {
  res.writeHead(status, { "content-type": "application/json", "set-cookie": "csrftoken=visual-mock; Path=/" });
  res.end(JSON.stringify(body));
}

createServer((req, res) => {
  const url = new URL(req.url || "/", "http://127.0.0.1");
  if (url.pathname === "/__visual/scenario") {
    scenario = url.searchParams.get("set") || "normal";
    send(res, 200, { scenario });
    return;
  }
  const isBi = url.pathname.startsWith("/api/v1/backstage/bi/");
  if (req.method !== "GET") {
    // "Levar ao plano": a resposta real é {plan_day, carried}; o resto ecoa vazio.
    if (url.pathname.endsWith("/bi/over-short/carry/")) send(res, 200, { plan_day: "2026-10-10", carried: 3 });
    else send(res, 200, {});
    return;
  }
  if (isBi && scenario === "error") {
    send(res, 500, { detail: "Erro de teste da matriz visual." });
    return;
  }
  const body = recordedFor(url);
  if (body) {
    const reading = isBi && scenario === "empty" && !url.pathname.endsWith("/bi/scenarios/") ? emptied(body) : body;
    // Toda leitura do B.I. diz quando o servidor a gerou (`generated_at`, ao lado de
    // `bi`). A gravação é anterior a essa chave: o mock carimba a hora da resposta.
    send(res, 200, isBi && reading && "bi" in reading ? { ...reading, generated_at: reading.generated_at ?? new Date().toISOString() } : reading);
    return;
  }
  send(res, 200, {});
}).listen(port, "127.0.0.1", () => {
  console.log("[bi-visual-mock] listening on http://127.0.0.1:" + port);
});
