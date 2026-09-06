import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * A VARREDURA — porque o gêmeo já apareceu duas vezes.
 *
 * A pergunta "quer salvar este e-mail no cadastro?" nasceu no campo da coluna
 * do fechamento. A prova de navegador achou o SEGUNDO campo, dentro do modal
 * "Cliente": lá a pergunta não existia, o operador fechava o modal e a oferta
 * aparecia JÁ MARCADA sem nunca ter sido feita. Como o padrão é marcado, isso
 * é gravar calado com outro nome.
 *
 * Um teste de componente prova o campo que ele conhece; não prova o IRMÃO que
 * alguém adiciona amanhã. Este aqui varre a superfície: **todo arquivo que
 * edita ou repassa o e-mail do comprovante / o CPF da nota tem de conhecer a
 * oferta.** Se um terceiro campo nascer sem ela, quem falha é este teste, e não
 * o balcão.
 *
 * ⚠️ Um wrapper que só REPASSE o valor sem editar também reprova aqui. É de
 * propósito: repasse novo é caminho novo, e caminho novo pede um par de olhos.
 */

const appDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "app");

/** Os dois campos que podem virar cadastro, pelos nomes que a tela usa. */
const RECEIPT_CONTACT_EMITS = ["update:receiptEmail", "update:invoiceTaxId"];
const OFFER_COMPONENT = "PosReceiptSaveOffer";

function sourceFiles(dir: string, found: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".nuxt" || entry === ".output") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) sourceFiles(full, found);
    else if (full.endsWith(".vue")) found.push(full);
  }
  return found;
}

describe("nenhum campo do comprovante existe sem a pergunta ao lado", () => {
  it("todo arquivo que toca o e-mail do comprovante ou o CPF da nota conhece a oferta", () => {
    const orphans: string[] = [];
    for (const file of sourceFiles(appDir)) {
      const source = readFileSync(file, "utf8");
      const touches = RECEIPT_CONTACT_EMITS.filter((emitName) => source.includes(emitName));
      if (touches.length && !source.includes(OFFER_COMPONENT)) {
        orphans.push(`${file.slice(appDir.length + 1)} → ${touches.join(", ")}`);
      }
    }

    expect(
      orphans,
      "Campo do comprovante SEM a oferta ao lado. O contato do comprovante só pode\n"
        + `virar cadastro quando o operador vê a pergunta — monte o <${OFFER_COMPONENT}>\n`
        + "em volta do campo (a lógica pura já existe em presentation/receiptContact.ts).\n"
        + `Órfãos:\n  ${orphans.join("\n  ")}`,
    ).toEqual([]);
  });

  it("a oferta é montada em MAIS DE UM lugar — o gêmeo existe e é conhecido", () => {
    // Se este número cair para 1, alguém removeu um campo OU removeu a
    // pergunta de um deles. Os dois merecem ser notados.
    const mounts = sourceFiles(appDir).filter((file) =>
      readFileSync(file, "utf8").includes(`<${OFFER_COMPONENT}`),
    );

    expect(mounts.map((file) => file.slice(appDir.length + 1)).sort()).toEqual([
      "components/PosCustomerModal.vue",
      "components/PosPaymentWorkspace.vue",
    ]);
  });
});
