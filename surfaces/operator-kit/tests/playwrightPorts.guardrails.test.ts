import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Guardrail de PORTA dos servidores de teste do Playwright.
//
// Medido em 19 e 20/11/2026: o "Functional browser contract" do purchase-nuxt caía
// na fila com `listen EADDRINUSE: address already in use 127.0.0.1:41008` (#2814,
// #2849, run 44781136315). Não era outro job: o runner do GitHub roda um job por
// máquina. A porta 41008 fica DENTRO da faixa efêmera do Linux (32768–60999, a de
// `/proc/sys/net/ipv4/ip_local_port_range`), de onde o kernel tira a porta LOCAL de
// toda conexão de saída. Durante a fase visual o Chromium, o Nitro e o mock abrem
// centenas de conexões; basta uma ainda em TIME_WAIT/aberta com a 41008 como porta
// local, e o `listen` do servidor seguinte falha. O `url` do webServer não vê nada
// (não há ninguém ESCUTANDO), então o Playwright sobe o servidor e ele morre.
//
// Porta escolhida na hora com `listen(0)` não resolve: ela sai da mesma faixa, e entre
// a escolha e o `listen` do app há um `nuxt build` de minutos. O que resolve é ficar
// FORA da faixa efêmera: abaixo de 32768 (no macOS a faixa começa em 49152). Esta
// trava reprova qualquer porta fixa de teste de 32768 para cima.

const EPHEMERAL_FLOOR = 32768;
const kitRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const surfacesRoot = resolve(kitRoot, "..");

// `PORT || 41008`, `port: 41008`, `127.0.0.1:41008`, `localhost:41008`.
const PORT_LITERAL = /(?:\|\|\s*|\?\?\s*|port:\s*|(?:127\.0\.0\.1|localhost):)(\d{4,5})\b/g;

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name.startsWith(".") || name === "test-results") continue;
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path, out);
    // Só o que sobe ou fala com servidor de teste do Playwright: spec e mock. O
    // `*.test.ts` do vitest fica de fora: ali `127.0.0.1:47811` é o endereço do
    // agente do balcão num fetch simulado, não uma porta que o teste abre.
    else if (/\.spec\.ts$|\.mjs$/.test(name)) out.push(path);
  }
  return out;
}

function testServerFiles(): string[] {
  const files: string[] = [];
  for (const app of readdirSync(surfacesRoot)) {
    const appDir = join(surfacesRoot, app);
    if (!statSync(appDir).isDirectory()) continue;
    for (const name of readdirSync(appDir)) {
      if (/^playwright.*\.config\.ts$/.test(name)) files.push(join(appDir, name));
    }
    const testsDir = join(appDir, "tests");
    try {
      if (statSync(testsDir).isDirectory()) walk(testsDir, files);
    } catch {
      // app sem pasta de testes
    }
  }
  return files;
}

describe("portas dos servidores de teste do Playwright", () => {
  it("ficam fora da faixa efêmera do kernel (abaixo de 32768)", () => {
    const files = testServerFiles();
    expect(files.length).toBeGreaterThan(10);
    const offenders: string[] = [];
    for (const file of files) {
      const text = readFileSync(file, "utf8");
      for (const match of text.matchAll(PORT_LITERAL)) {
        const port = Number(match[1]);
        if (port >= EPHEMERAL_FLOOR && port <= 65535) {
          offenders.push(`${relative(surfacesRoot, file)}: ${match[0]}`);
        }
      }
    }
    expect(offenders, "porta de teste dentro da faixa efêmera; use uma abaixo de 32768").toEqual([]);
  });
});
