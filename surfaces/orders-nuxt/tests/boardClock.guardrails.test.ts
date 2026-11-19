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

/** O arquivo sem comentários: o que vale é o código. Repete até não sobrar marcador:
 *  tirar um comentário pode juntar as pontas de outro (`<!-<!-- x -->-`). */
function code(path: string): string {
  let text = read(path);
  let before: string;
  do {
    before = text;
    text = text
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/<!--[\s\S]*?-->/g, "")
      .replace(/(^|\s)\/\/[^\n]*/g, "$1");
  } while (text !== before);
  return text;
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
