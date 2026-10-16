// Proxy gravador: app do B.I. → este proxy → Django real (banco semeado, sessão de
// superusuário). Grava cada GET JSON por caminho+query em OUT ao receber SIGTERM/SIGINT.
import { createServer, request } from "node:http";
import { readFileSync, writeFileSync } from "node:fs";

const [port, upstreamPort, sessionFile, out] = process.argv.slice(2);
const sessionid = readFileSync(sessionFile, "utf8").trim();
const recorded = {};

createServer((req, res) => {
  const chunks = [];
  req.on("data", (c) => chunks.push(c));
  req.on("end", () => {
    const headers = { ...req.headers, host: `127.0.0.1:${upstreamPort}` };
    headers.cookie = `sessionid=${sessionid}; csrftoken=onda0rec`;
    headers["x-csrftoken"] = "onda0rec";
    delete headers["accept-encoding"];
    const up = request({ host: "127.0.0.1", port: upstreamPort, path: req.url, method: req.method, headers }, (ur) => {
      const body = [];
      ur.on("data", (c) => body.push(c));
      ur.on("end", () => {
        const buf = Buffer.concat(body);
        if (req.method === "GET" && ur.statusCode === 200 && String(ur.headers["content-type"] || "").includes("json")) {
          try { recorded[req.url] = JSON.parse(buf.toString("utf8")); } catch { /* não-JSON */ }
        }
        console.log(`${req.method} ${ur.statusCode} ${req.url}`);
        const h = { ...ur.headers }; delete h["content-length"]; delete h["transfer-encoding"];
        res.writeHead(ur.statusCode, h); res.end(buf);
      });
    });
    up.on("error", (e) => { res.writeHead(502); res.end(String(e)); });
    up.end(Buffer.concat(chunks));
  });
}).listen(Number(port), "127.0.0.1", () => console.log(`gravador em ${port} → ${upstreamPort}`));

function save() { writeFileSync(out, JSON.stringify(recorded, null, 2)); console.log(`gravou ${Object.keys(recorded).length}`); process.exit(0); }
process.on("SIGTERM", save); process.on("SIGINT", save);
