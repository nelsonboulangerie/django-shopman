import { describe, expect, it } from "vitest";

import { closeGuardNotice, closeGuardSituation, type CloseGuardInput } from "~/presentation/closeGuard";

const base: CloseGuardInput = {
  blocked: true,
  inFlightHere: false,
  pending: false,
  heldElsewhere: false,
  browserFailure: "",
};

describe("closeGuard — o aviso da trava contra cobrança duplicada", () => {
  it("sem trava, nada a avisar", () => {
    expect(closeGuardNotice({ ...base, blocked: false })).toBeNull();
  });

  it("a cobrança em voo desta aba é o caminho feliz, não aviso", () => {
    expect(closeGuardSituation({ ...base, pending: true, inFlightHere: true })).toBe("none");
  });

  it("outra aba cobrando: esperar, sem botão de liberar", () => {
    const notice = closeGuardNotice({ ...base, pending: true, heldElsewhere: true });
    expect(notice?.situation).toBe("other_tab_charging");
    expect(notice?.canRelease).toBe(false);
  });

  it("pending sem dono vivo é venda interrompida", () => {
    expect(closeGuardSituation({ ...base, pending: true })).toBe("interrupted");
  });

  it("resposta sem prova é resultado não confirmado", () => {
    expect(closeGuardNotice(base)?.title).toBe("Resultado da cobrança não confirmado");
  });

  it("com o fechamento guardado, a primeira saída é Conferir agora (sem cobrar de novo)", () => {
    const uncertain = closeGuardNotice({ ...base, replayable: true });
    expect(uncertain?.canRecheck).toBe(true);
    expect(uncertain?.body).toBe("A venda ficou sem resposta. Conferir agora pergunta por esta mesma venda, sem cobrar de novo.");
    expect(closeGuardNotice({ ...base, pending: true, replayable: true })?.canRecheck).toBe(true);
    // Sem o corpo guardado, só a conferência manual.
    expect(closeGuardNotice(base)?.canRecheck).toBe(false);
    // Outra aba cobrando ou navegador sem trava: nada a reenviar daqui.
    expect(closeGuardNotice({ ...base, heldElsewhere: true, replayable: true })?.canRecheck).toBe(false);
    expect(closeGuardNotice({ ...base, browserFailure: "x", replayable: true })?.canRecheck).toBe(false);
  });

  it("falha do navegador diz a falha, não 'resultado não confirmado'", () => {
    const notice = closeGuardNotice({ ...base, browserFailure: "Este navegador não conseguiu ativar a proteção." });
    expect(notice?.situation).toBe("browser_unavailable");
    expect(notice?.body).toBe("Este navegador não conseguiu ativar a proteção.");
  });

  it("nenhum título obriga o operador a escolher entre duas leituras", () => {
    const inputs: CloseGuardInput[] = [
      { ...base, pending: true, heldElsewhere: true },
      { ...base, pending: true },
      base,
      { ...base, browserFailure: "x" },
    ];
    for (const input of inputs) {
      const notice = closeGuardNotice(input)!;
      expect(notice.title).not.toMatch(/\bou\b/);
    }
  });
});

// O DEFEITO de 22/09/2026: o corpo citava "confira no Gestor" e a faixa não
// levava a lugar nenhum, com o `ordersUrl` já no `runtimeConfig`. Menção não é
// ação. Aqui não há `order_ref` (o que está em dúvida é se o pedido nasceu),
// então o destino honesto é a FILA, e o rótulo promete a fila.
describe("closeGuard — a saída para o Gestor", () => {
  const withOrders: CloseGuardInput = { ...base, ordersUrl: "https://pedidos.boulangerie/" };

  it("resultado não confirmado leva à fila do Gestor", () => {
    const notice = closeGuardNotice(withOrders);
    expect(notice?.situation).toBe("uncertain");
    expect(notice?.link).toEqual({
      href: "https://pedidos.boulangerie",
      label: "Procurar o pedido no Gestor",
    });
  });

  it("venda interrompida tem a mesma dúvida e a mesma porta", () => {
    const notice = closeGuardNotice({ ...withOrders, pending: true });
    expect(notice?.situation).toBe("interrupted");
    expect(notice?.link?.href).toBe("https://pedidos.boulangerie");
  });

  it("o corpo não repete o que o botão já diz", () => {
    const notice = closeGuardNotice(withOrders);
    expect(notice?.body).not.toContain("no Gestor");
    expect(notice?.body).toContain("confira se o pedido e o pagamento foram criados");
  });

  it("sem `ordersUrl` configurado não há botão — e nenhuma promessa de link", () => {
    expect(closeGuardNotice(base)?.link).toBeUndefined();
  });

  it("esperar outra aba não é conferir: sem porta para o Gestor", () => {
    const notice = closeGuardNotice({ ...withOrders, pending: true, heldElsewhere: true });
    expect(notice?.situation).toBe("other_tab_charging");
    expect(notice?.link).toBeUndefined();
  });
});
