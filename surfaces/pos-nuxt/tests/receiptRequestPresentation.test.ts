import { describe, expect, it } from "vitest";
import { receiptRequestEmits, receiptRequestNote } from "~/presentation/receiptRequest";
import type { POSCheckoutContractProjection } from "~/types/pos";

const contract = (capabilities: Record<string, unknown>, extra: Record<string, unknown> = {}) =>
  ({ capabilities, receipt_channels: [], ...extra }) as unknown as POSCheckoutContractProjection;

describe("receiptRequestEmits", () => {
  it("lê a palavra do servidor em `capabilities`", () => {
    expect(receiptRequestEmits(contract({ receipt_requests_emission: true }))).toBe(true);
    expect(receiptRequestEmits(contract({ receipt_requests_emission: false }))).toBe(false);
    expect(receiptRequestEmits(contract({}))).toBe(false);
    expect(receiptRequestEmits(null)).toBe(false);
  });

  it("no topo do contrato a chave não vale: não é lá que o servidor publica", () => {
    expect(receiptRequestEmits(contract({}, { receipt_requests_emission: true }))).toBe(false);
  });
});

describe("receiptRequestNote", () => {
  it("sem canal pedido, não há promessa", () => {
    expect(receiptRequestNote({ print: false, email: false, emits: true })).toBe("");
    expect(receiptRequestNote({ print: false, email: false, emits: false })).toBe("");
  });

  it("papel e e-mail pedem a nota quando a regra do servidor confirma", () => {
    expect(receiptRequestNote({ print: true, email: false, emits: true }))
      .toBe("Pedir papel já pede a nota: ela imprime sozinha assim que for autorizada.");
    expect(receiptRequestNote({ print: false, email: true, emits: true }))
      .toBe("Pedir por e-mail já pede a nota: o e-mail sai assim que ela for autorizada.");
    expect(receiptRequestNote({ print: true, email: true, emits: true }))
      .toBe("Papel e e-mail já pedem a nota: ela imprime sozinha, e o e-mail sai assim que ela for autorizada.");
  });

  it("sem a palavra do servidor, diz quando a nota sai em vez de prometer", () => {
    for (const [print, email] of [[true, false], [false, true], [true, true]] as const) {
      const note = receiptRequestNote({ print, email, emits: false });
      expect(note).toContain("quando houver NFC-e (CPF, cartão ou Pix)");
      expect(note).not.toContain("já pede");
    }
  });
});
