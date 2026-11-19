// O relógio e o "hoje" do painel são os do servidor (WP-G09, laudo do Gestor P2-05 e
// P2-06). Trava de fonte: a página é grande demais para montar num teste de unidade, e
// o defeito era uma linha (o relógio ancorado no primeiro pedido novo, que sem pedido
// novo caía no relógio do dispositivo).
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const read = (path: string) => readFileSync(join(here, path), "utf8");

/** Tira os blocos entre `open` e `close`, procurando as pontas pelo índice (sem
 *  expressão regular): repete enquanto houver abertura, porque tirar um bloco pode
 *  juntar as pontas de outro. Abertura sem fecho leva o resto do texto junto. */
function withoutBlocks(text: string, open: string, close: string): string {
  let rest = text;
  for (;;) {
    const start = rest.indexOf(open);
    if (start < 0) return rest;
    const end = rest.indexOf(close, start + open.length);
    rest = rest.slice(0, start) + (end < 0 ? "" : rest.slice(end + close.length));
  }
}

/** O arquivo sem comentários: o que vale é o código. */
function code(path: string): string {
  return withoutBlocks(withoutBlocks(read(path), "/*", "*/"), "<!--", "-->")
    .split("\n")
    .map((line) => {
      // Comentário de linha: `//` no começo ou depois de espaço (não o de `https://`).
      const at = line.search(/(^|\s)\/\//);
      return at < 0 ? line : line.slice(0, at);
    })
    .join("\n");
}

describe("o relógio do painel ancora na leitura do servidor", () => {
  const page = code("../app/pages/index.vue");

  it("a âncora é o generated_at da última leitura boa", () => {
    expect(page).toMatch(/const serverNow = computed\(\(\) => readMetadata\.value\?\.generated_at \?\? ""\)/);
    expect(page).toMatch(/const nowMs = useNowTick\(\(\) => serverNow\.value\)/);
  });

  it("a página não ancora relógio em cartão (o primeiro pedido novo nem sempre existe)", () => {
    expect(page).not.toContain("server_now_iso");
  });
});

describe("o hoje da tela é o do servidor", () => {
  it.each(["queue.ts", "board.ts", "boardStrip.ts", "preorderList.ts", "kitchen.ts"])(
    "presentation/%s não monta data com o relógio do dispositivo",
    (file) => {
      const source = code(`../app/presentation/${file}`);
      for (const deviceDay of ["getFullYear(", "getMonth(", "getDate(", "toDateString(", "new Date()"])
        expect(source, `${file} usa ${deviceDay}`).not.toContain(deviceDay);
    },
  );
});
