import { describe, expect, it } from "vitest";
import {
  receiptContactChecked,
  receiptContactOffer,
  receiptSaveOffers,
  receiptSaveSummary,
  receiptValueIsAskable,
} from "~/presentation/receiptContact";

const ANA = { name: "Ana Prado", email: "ana@example.org", tax_id: "52998224725" };
const CPF_A = "52998224725";
const CPF_B = "11144477735";

describe("receiptContactOffer — a matriz, igual para e-mail e para CPF", () => {
  it("cadastro SEM o e-mail: oferece salvar, desmarcado", () => {
    const offer = receiptContactOffer({
      field: "email",
      typed: "ana@example.org",
      customer: { name: "Ana Prado" },
    });
    expect(offer.kind).toBe("save");
    expect(offer.defaultChecked).toBe(false);
    expect(offer.title).toContain("Ana");
  });

  it("cadastro SEM o CPF: oferece salvar, desmarcado", () => {
    const offer = receiptContactOffer({
      field: "tax_id",
      typed: CPF_A,
      customer: { name: "Ana Prado" },
    });
    expect(offer.kind).toBe("save");
    expect(offer.defaultChecked).toBe(false);
    expect(offer.title).toContain("CPF");
  });

  it("e-mail IGUAL ao do cadastro: nada a perguntar", () => {
    const offer = receiptContactOffer({ field: "email", typed: "ANA@example.org", customer: ANA });
    expect(offer.kind).toBe("none");
    expect(offer.title).toBe("");
  });

  it("CPF IGUAL ao do cadastro: nada a perguntar", () => {
    const offer = receiptContactOffer({ field: "tax_id", typed: "529.982.247-25", customer: ANA });
    expect(offer.kind).toBe("none");
  });

  it("e-mail DIFERENTE: atualizar é ação nomeada e nasce DESMARCADA", () => {
    const offer = receiptContactOffer({
      field: "email",
      typed: "contador@example.org",
      customer: ANA,
    });
    expect(offer.kind).toBe("update");
    expect(offer.defaultChecked).toBe(false);
    expect(offer.confirmLabel).toBe("Atualizar o cadastro");
    // O cadastro atual sai por escrito: o operador precisa ver o que some.
    expect(offer.hint).toContain("ana@example.org");
  });

  it("CPF DIFERENTE: atualizar é ação nomeada e nasce DESMARCADA", () => {
    const offer = receiptContactOffer({ field: "tax_id", typed: CPF_B, customer: ANA });
    expect(offer.kind).toBe("update");
    expect(offer.defaultChecked).toBe(false);
    expect(offer.hint).toContain(CPF_A);
  });

  it("SEM cliente identificado: 'Salvar como cliente?' vem JÁ MARCADO", () => {
    // ⚠️ Decisão do dono, contra a recomendação de nascer desmarcado. Não
    // "corrigir" — o que segura a transparência é a linha ficar à vista.
    const email = receiptContactOffer({ field: "email", typed: "novo@example.org", customer: null });
    const taxId = receiptContactOffer({ field: "tax_id", typed: CPF_A, customer: null });
    expect(email.kind).toBe("create");
    expect(email.defaultChecked).toBe(true);
    expect(taxId.kind).toBe("create");
    expect(taxId.defaultChecked).toBe(true);
  });

  // ⚠️ A CAIXA VEM MARCADA — então a consequência dita tem de ser a que
  // acontece. O servidor resolve o contato como identidade numa venda anônima:
  // se já houver cadastro com este e-mail, a venda vai PARA ELE, com faixa de
  // preço e fidelidade junto. Prometer "nasce um cadastro novo" era vender uma
  // consequência que o sistema não cumpre.
  it("a oferta NÃO promete cadastro novo — o servidor acha quem já existe", () => {
    const email = receiptContactOffer({ field: "email", typed: "novo@example.org", customer: null });
    expect(email.hint).not.toContain("Nasce um cadastro novo");
    expect(email.summaryLine).not.toContain("cadastro novo será criado");
    expect(email.hint).toContain("ou vai para o cadastro que já o tem");
    expect(email.summaryLine).toContain("ou vai para o cadastro que já o tem");
    // Desmarcar segue sendo um toque, e a frase continua dizendo isso.
    expect(email.hint).toContain("Desmarque para vender sem cadastrar");

    const taxId = receiptContactOffer({ field: "tax_id", typed: CPF_A, customer: null });
    expect(taxId.hint).toContain("Este CPF fica salvo como cliente");
    expect(taxId.summaryLine).toContain("ou vai para o cadastro que já o tem");
  });

  it("campo vazio ou incompleto não pergunta nada", () => {
    expect(receiptContactOffer({ field: "email", typed: "", customer: ANA }).kind).toBe("none");
    expect(receiptContactOffer({ field: "email", typed: "ana@", customer: null }).kind).toBe("none");
    expect(receiptContactOffer({ field: "tax_id", typed: "529", customer: null }).kind).toBe("none");
    // Documento com dígito verificador errado não é pergunta, é erro de digitação.
    expect(receiptContactOffer({ field: "tax_id", typed: "11111111111", customer: null }).kind).toBe("none");
  });
});

describe("receiptValueIsAskable — perguntar no fim da digitação, não no meio", () => {
  it("só depois do endereço inteiro", () => {
    expect(receiptValueIsAskable("email", "a")).toBe(false);
    expect(receiptValueIsAskable("email", "a@b")).toBe(false);
    expect(receiptValueIsAskable("email", "a@b.org")).toBe(true);
  });

  it("só depois do documento inteiro e válido", () => {
    expect(receiptValueIsAskable("tax_id", "5299822")).toBe(false);
    expect(receiptValueIsAskable("tax_id", CPF_A)).toBe(true);
  });
});

describe("receiptContactChecked — o toque do operador vence o padrão", () => {
  const anonima = receiptContactOffer({ field: "email", typed: "novo@example.org", customer: null });

  it("sem toque, vale o padrão da oferta", () => {
    expect(receiptContactChecked(anonima, null)).toBe(true);
  });

  it("desmarcar SEGURA — o padrão não volta a cada tecla", () => {
    expect(receiptContactChecked(anonima, false)).toBe(false);
  });

  it("oferta muda não guarda nada, tenha o operador tocado ou não", () => {
    const muda = receiptContactOffer({ field: "email", typed: "ana@example.org", customer: ANA });
    expect(receiptContactChecked(muda, true)).toBe(false);
  });
});

describe("receiptSaveSummary — a confirmação no resumo do fechamento", () => {
  it("lista só o que VAI acontecer", () => {
    const salvar = receiptContactOffer({
      field: "email",
      typed: "ana@example.org",
      customer: { name: "Ana Prado" },
    });
    const cpf = receiptContactOffer({ field: "tax_id", typed: CPF_B, customer: ANA });

    expect(
      receiptSaveSummary([
        { offer: salvar, checked: true },
        { offer: cpf, checked: false },
      ]),
    ).toEqual(["O e-mail será salvo no cadastro de Ana."]);
  });

  it("nada marcado, nada dito", () => {
    const muda = receiptContactOffer({ field: "email", typed: "ana@example.org", customer: ANA });
    expect(receiptSaveSummary([{ offer: muda, checked: true }])).toEqual([]);
  });
});

describe("receiptSaveOffers — o campo do painel do cliente JÁ é identidade", () => {
  const base = {
    receiptEmail: "",
    customerEmail: "",
    invoiceTaxId: "",
    wantsCpfOnInvoice: false,
    customerTaxId: "",
    customer: null,
  };

  it("comprovante repetindo o e-mail do painel não pergunta nada", () => {
    // `customer_email` vira cadastro por definição; oferecer "salvar" ali
    // seria prometer o que já está acontecendo.
    const { email } = receiptSaveOffers({
      ...base,
      receiptEmail: "ana@example.org",
      customerEmail: "ana@example.org",
    });
    expect(email.kind).toBe("none");
  });

  it("comprovante com OUTRO endereço pergunta", () => {
    const { email } = receiptSaveOffers({
      ...base,
      receiptEmail: "contador@example.org",
      customerEmail: "ana@example.org",
    });
    expect(email.kind).toBe("create");
  });

  it("o CPF só entra na conta com 'CPF na nota' ligado", () => {
    expect(receiptSaveOffers({ ...base, invoiceTaxId: CPF_A }).taxId.kind).toBe("none");
    expect(
      receiptSaveOffers({ ...base, invoiceTaxId: CPF_A, wantsCpfOnInvoice: true }).taxId.kind,
    ).toBe("create");
  });

  it("CPF da nota igual ao do painel do cliente não pergunta", () => {
    const { taxId } = receiptSaveOffers({
      ...base,
      invoiceTaxId: CPF_A,
      wantsCpfOnInvoice: true,
      customerTaxId: CPF_A,
    });
    expect(taxId.kind).toBe("none");
  });
});
