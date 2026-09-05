// A ESCOLHA É DO OPERADOR — a regra pura das duas perguntas do balcão:
// o WhatsApp digitado já é de outro cadastro (conflito), e o contato do cliente
// associado vai mudar (correção). Aqui se prova que a frase nomeia os dois
// lados e que as duas saídas dizem o que fica — nunca "OK / Cancelar".
import { describe, expect, it } from "vitest";

import {
  candidateSubtitle,
  conflictDecision,
  contactChangeDecision,
  customerDecisionCopy,
  decisionFieldLabel,
  phoneKey,
  type CustomerDecision,
  type ServerConflictCandidate,
} from "~/presentation/customerDecision";

function candidate(overrides: Partial<ServerConflictCandidate> = {}): ServerConflictCandidate {
  return {
    ref: "CUST-A",
    name: "Ana Prado",
    phone: "+5543999990011",
    email: "",
    tax_id: "",
    matched_by: ["ref"],
    is_current: true,
    owner_inactive: false,
    ...overrides,
  };
}

describe("conflictDecision — a recusa 422 vira decisão de tela", () => {
  const current = candidate();
  const other = candidate({
    ref: "CUST-B", name: "Bruno Souza", phone: "+5543999990022",
    matched_by: ["phone"], is_current: false,
  });

  it("nomeia os DOIS lados: quem está na comanda e quem é dono do telefone", () => {
    const decision = conflictDecision({
      field: "customer_phone",
      candidates: [current, other],
      typed: "43999990022",
    });
    expect(decision).toEqual({
      kind: "contact_conflict",
      field: "phone",
      typed: "43999990022",
      current: { ref: "CUST-A", name: "Ana Prado", value: "+5543999990011" },
      other: { ref: "CUST-B", name: "Bruno Souza", value: "+5543999990022" },
      candidates: [current, other],
    });
  });

  it("sem o digitado, o valor do dono serve de frase", () => {
    expect(conflictDecision({ field: "customer_phone", candidates: [current, other] })?.typed)
      .toBe("+5543999990022");
  });

  it("e-mail e CPF/CNPJ leem o campo certo do candidato", () => {
    const byEmail = conflictDecision({
      field: "customer_email",
      candidates: [
        candidate({ email: "ana@example.com" }),
        candidate({ ref: "CUST-B", name: "Bruno", email: "bruno@example.com", matched_by: ["email"], is_current: false }),
      ],
    });
    expect(byEmail?.field).toBe("email");
    expect(byEmail?.other?.value).toBe("bruno@example.com");
  });

  // ⚠️ Uma recusa que exige DECISÃO não pode virar toast que some. O único
  // caso sem painel é o de candidato nenhum — aí não há nada a mostrar.
  it("sem candidato nenhum não há o que mostrar", () => {
    expect(conflictDecision({ field: "customer_phone", candidates: [] })).toBeNull();
    expect(conflictDecision({ field: "customer_phone" })).toBeNull();
  });

  // ⚠️ Dois ou mais intrusos, por campos diferentes: não há UM campo culpado
  // para nomear. O servidor já mandava a lista e a tela a jogava fora.
  it("sem UM campo culpado, a tela mostra a LISTA em vez de sumir", () => {
    const terceiro = candidate({
      ref: "CUST-C", name: "Célia Dias", phone: "+5543999990033",
      tax_id: "52998224725", matched_by: ["document"], is_current: false,
    });
    const decision = conflictDecision({ field: "", candidates: [current, other, terceiro] });

    expect(decision?.kind).toBe("candidate_list");
    expect(decision?.field).toBe("");
    expect(decision?.candidates).toHaveLength(3);
  });

  it("um lado só também cai na lista — não há troca de um toque a oferecer", () => {
    expect(conflictDecision({ field: "customer_phone", candidates: [current] })?.kind)
      .toBe("candidate_list");
  });

  // ⚠️ O resolve do servidor só enxerga cliente ATIVO; os UNIQUEs do banco
  // enxergam TODOS. Com o dono desativado, "atender Bruno" não existe: ele não
  // aparece nem na busca. A tela precisa dizer isso e dar a saída certa.
  it("dono DESATIVADO é um caso próprio, não um conflito comum", () => {
    const morto = candidate({
      ref: "CUST-OLD", name: "Cadastro Antigo", phone: "+5543999990022",
      matched_by: ["phone"], is_current: false, owner_inactive: true,
    });
    const decision = conflictDecision({ field: "customer_phone", candidates: [current, morto] });

    expect(decision?.kind).toBe("inactive_owner");
    expect(decision?.other?.ref).toBe("CUST-OLD");
  });

  it("o subtítulo do candidato mostra por onde reconhecê-lo", () => {
    expect(candidateSubtitle(other)).toBe("+5543999990022");
    expect(candidateSubtitle(candidate({
      phone: "+5543999990033", email: "c@example.com", tax_id: "52998224725",
    }))).toBe("+5543999990033 · c@example.com · 52998224725");
  });
});

describe("contactChangeDecision — corrigir contato se DIZ antes de acontecer", () => {
  const base = {
    customerRef: "CUST-A",
    customerName: "Ana Prado",
    registeredPhone: "+5543999990011",
    typedPhone: "+5543999990011",
    registeredEmail: "",
    typedEmail: "",
  };

  it("telefone diferente do cadastrado vira pergunta", () => {
    const decision = contactChangeDecision({ ...base, typedPhone: "43 98888-7777" });
    expect(decision).toEqual({
      kind: "contact_change",
      field: "phone",
      typed: "43 98888-7777",
      current: { ref: "CUST-A", name: "Ana Prado", value: "+5543999990011" },
      other: null,
    });
  });

  // ⚠️ O cadastro guarda E.164 e o operador digita como se fala. Sem derrubar o
  // código do país, TODO telefone já cadastrado pareceria diferente e a tela
  // perguntaria "trocar?" em cima do número que já estava certo.
  it("o mesmo número em formatos diferentes NÃO é troca", () => {
    expect(contactChangeDecision({ ...base, typedPhone: "(43) 99999-0011" })).toBeNull();
    expect(contactChangeDecision({ ...base, typedPhone: "43999990011" })).toBeNull();
    expect(phoneKey("+5543999990011")).toBe("43999990011");
    expect(phoneKey("(43) 99999-0011")).toBe("43999990011");
  });

  it("campo VAZIO no cadastro é lacuna, não troca — o merge preenche sem perguntar", () => {
    expect(contactChangeDecision({ ...base, registeredPhone: "", typedPhone: "43988887777" })).toBeNull();
  });

  it("campo esvaziado no formulário também não apaga contato de ninguém", () => {
    expect(contactChangeDecision({ ...base, typedPhone: "  " })).toBeNull();
  });

  it("sem cadastro associado não há 'de quem' para corrigir", () => {
    expect(contactChangeDecision({ ...base, customerRef: "", typedPhone: "43988887777" })).toBeNull();
  });

  it("e-mail entra pela mesma porta, e caixa alta não conta como mudança", () => {
    expect(contactChangeDecision({
      ...base, registeredEmail: "ana@example.com", typedEmail: "ANA@Example.com",
    })).toBeNull();
    expect(contactChangeDecision({
      ...base, registeredEmail: "ana@example.com", typedEmail: "outra@example.com",
    })?.field).toBe("email");
  });
});

describe("customerDecisionCopy — voz de balcão, e as saídas dizem o que fica", () => {
  const conflict: CustomerDecision = {
    kind: "contact_conflict",
    field: "phone",
    typed: "(43) 99999-0022",
    current: { ref: "CUST-A", name: "Ana Prado", value: "+5543999990011" },
    other: { ref: "CUST-B", name: "Bruno Souza", value: "+5543999990022" },
  };

  it("o conflito nomeia o dono, o da comanda, e as duas saídas", () => {
    const copy = customerDecisionCopy(conflict);
    expect(copy.title).toBe("Este WhatsApp já é de outro cadastro");
    expect(copy.body).toContain("(43) 99999-0022");
    expect(copy.body).toContain("Bruno Souza");
    expect(copy.body).toContain("Ana Prado");
    // Nem "OK", nem "Cancelar": cada botão diz com quem a venda continua.
    expect(copy.confirmLabel).toBe("Atender Bruno");
    expect(copy.cancelLabel).toBe("Manter Ana");
  });

  // A TERCEIRA saída, que faltava por completo: são a MESMA pessoa. Sem ela o
  // operador só podia escolher UM dos dois cadastros duplicados do cliente.
  it("o conflito oferece unificar os cadastros", () => {
    const copy = customerDecisionCopy(conflict);
    expect(copy.merge?.label).toBe("É a mesma pessoa — unificar cadastros");
    expect(copy.release).toBeNull();
  });

  // ⚠️ Com o dono DESATIVADO não existe "atender": ele não aparece na busca. E
  // o Core recusa unificar com um lado inativo. A única saída é liberar.
  it("dono desativado tem copy própria e oferece LIBERAR, não unificar", () => {
    const copy = customerDecisionCopy({
      kind: "inactive_owner",
      field: "phone",
      typed: "(43) 99999-0022",
      current: { ref: "CUST-A", name: "Ana Prado", value: "+5543999990011" },
      other: { ref: "CUST-OLD", name: "Cadastro Antigo", value: "+5543999990022" },
    });
    expect(copy.title).toBe("Este WhatsApp está preso num cadastro desativado");
    expect(copy.body).toContain("Cadastro Antigo");
    expect(copy.confirmLabel).toBe("Liberar o WhatsApp");
    expect(copy.release?.label).toBe("Liberar o WhatsApp");
    // Unificar não é oferecido porque o Core recusaria — botão morto é pior
    // que botão ausente.
    expect(copy.merge).toBeNull();
  });

  // ⚠️ Sem UM campo culpado a escolha é por LINHA: o par confirmar/cancelar não
  // teria o que dizer, e o painel some com o `confirmLabel` vazio.
  it("a lista de candidatos não tem botão de confirmar — a escolha é por linha", () => {
    const copy = customerDecisionCopy({
      kind: "candidate_list",
      field: "",
      typed: "",
      current: { ref: "CUST-A", name: "Ana Prado", value: "" },
      other: null,
    });
    expect(copy.title).toBe("Os dados apontam para cadastros diferentes");
    expect(copy.confirmLabel).toBe("");
    expect(copy.cancelLabel).toBe("Manter Ana");
    expect(copy.merge).toBeNull();
  });

  it("a correção diz DE onde PARA onde antes de acontecer", () => {
    const copy = customerDecisionCopy({
      kind: "contact_change",
      field: "phone",
      typed: "(43) 98888-7777",
      current: { ref: "CUST-A", name: "Ana Prado", value: "+5543999990011" },
      other: null,
    });
    expect(copy.title).toBe("Trocar o WhatsApp de Ana Prado?");
    expect(copy.body).toContain("De +5543999990011 para (43) 98888-7777");
    expect(copy.confirmLabel).toBe("Trocar o WhatsApp");
    expect(copy.cancelLabel).toBe("Manter +5543999990011");
  });

  it("os campos têm nome de balcão", () => {
    expect(decisionFieldLabel("phone")).toBe("WhatsApp");
    expect(decisionFieldLabel("email")).toBe("e-mail");
    expect(decisionFieldLabel("tax_id")).toBe("CPF/CNPJ");
  });
});
