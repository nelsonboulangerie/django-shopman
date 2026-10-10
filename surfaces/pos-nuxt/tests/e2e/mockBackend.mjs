// Mock backend mínimo p/ os e2e do POS: responde rápido a qualquer /api/* para o
// BFF/SSR do Nuxt não pendurar. NÃO simula dados de negócio — a leitura do terminal
// (`/backstage/pos/`) devolve 401 de propósito, para o app subir o gate de login
// (sessão de operador ausente). É o estado "sem backend" que dá pra exercitar sem
// dados. Fluxos com dados ricos rodam contra o Django real (reviewer local).
//
// Exceção: a VENDA SEM CONEXÃO (`offline-sale.spec.ts`) precisa de um balcão com
// produtos, comanda e fechamento. O spec manda o cookie `pos_e2e=offline-sale`, e
// esse tráfego vai para o mock do cenário da venda (`tests/visual/mockBackend.mjs`,
// `MOCK_SCENARIO=sale MOCK_DIRECT=1`), que sobe ao lado na porta seguinte. O resto
// dos specs não manda o cookie e segue no mock de sempre.
import { spawn } from "node:child_process";
import { createServer, request } from "node:http";
import { fileURLToPath } from "node:url";

const port = Number(process.env.MOCK_PORT || 8798);
const salePort = port + 1;

const saleMock = spawn(
  process.execPath,
  [fileURLToPath(new URL("../visual/mockBackend.mjs", import.meta.url))],
  { env: { ...process.env, MOCK_PORT: String(salePort), MOCK_SCENARIO: "sale", MOCK_DIRECT: "1" }, stdio: "inherit" },
);
const stopSaleMock = () => saleMock.kill();
process.on("exit", stopSaleMock);
process.on("SIGTERM", () => { stopSaleMock(); process.exit(0); });
process.on("SIGINT", () => { stopSaleMock(); process.exit(0); });

function proxyToSaleMock(req, res) {
  const upstream = request(
    { host: "127.0.0.1", port: salePort, method: req.method, path: req.url, headers: req.headers },
    (answer) => {
      res.writeHead(answer.statusCode || 502, answer.headers);
      answer.pipe(res);
    },
  );
  upstream.on("error", () => {
    res.statusCode = 502;
    res.end("{}");
  });
  req.pipe(upstream);
}

const server = createServer((req, res) => {
  if (/(^|;\s*)pos_e2e=offline-sale(;|$)/.test(req.headers.cookie || "")) {
    proxyToSaleMock(req, res);
    return;
  }

  res.setHeader("content-type", "application/json");
  // csrftoken p/ o handshake do BFF não semear em loop.
  res.setHeader("set-cookie", "csrftoken=e2e-mock; Path=/");

  // Sem estação ou operador, a antessala recusa identificação por PIN.
  // O shell usa esta leitura para escolher o login por senha.
  if (req.url && /\/backstage\/operator\/session\/?(\?|$)/.test(req.url)) {
    res.statusCode = 403;
    res.end(JSON.stringify({ detail: "Autenticação necessária." }));
    return;
  }

  // Leitura do terminal sem sessão → 401.
  if (req.url && /\/backstage\/pos\/?(\?|$)/.test(req.url)) {
    res.statusCode = 401;
    res.end(JSON.stringify({ detail: "Autenticação necessária." }));
    return;
  }

  res.statusCode = 200;
  res.end("{}");
});

server.listen(port, "127.0.0.1", () => {
  // eslint-disable-next-line no-console
  console.log(`[pos-mock] listening on http://127.0.0.1:${port} (venda: ${salePort})`);
});
