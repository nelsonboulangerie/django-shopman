import { describe, expect, it } from "vitest";

import type { Affordance } from "../app/presentation/board";
import { blockPillLabel, blockedReasonLines, lockedButtonRepeatsPill } from "../app/presentation/cardBlocks";

// WP-G06 (laudo do Gestor, P1-12 e P2-16): o motivo do botão travado vai escrito, e a
// pílula do bloqueio diz o fato.

const aff = (over: Partial<Affordance> = {}): Affordance => ({
  ref: "confirm", label: "Aceitar", icon: "lucide:check", priority: "primary",
  needsInput: false, disabled: false, reason: "", ...over,
});
const PERMISSION = "Identifique uma pessoa com permissão para gerenciar pedidos.";

describe("blockedReasonLines: por que o botão está travado, escrito", () => {
  it("nada travado, nenhuma linha", () => {
    expect(
      blockedReasonLines({
        primary: aff(), primaryLabel: "Aceitar",
        secondary: [aff({ ref: "reject", label: "Recusar", priority: "danger" })],
        blockAnnounced: false,
      }),
    ).toEqual([]);
  });

  it("o mesmo motivo em todos os botões sai uma vez, sem nome de botão", () => {
    expect(
      blockedReasonLines({
        primary: aff({ disabled: true, reason: PERMISSION }), primaryLabel: "Aceitar",
        secondary: [aff({ ref: "reject", label: "Recusar", priority: "danger", disabled: true, reason: PERMISSION })],
        blockAnnounced: false,
      }),
    ).toEqual([PERMISSION]);
  });

  it("travado só um dos botões: a linha diz de qual botão fala", () => {
    expect(
      blockedReasonLines({
        primary: aff({ ref: "advance", label: "Marcar como retirado" }), primaryLabel: "Entregar W33",
        secondary: [
          aff({ ref: "settle_cash", label: "Receber na retirada", priority: "secondary", disabled: true,
            reason: "Abra um turno de caixa para registrar o acerto." }),
        ],
        blockAnnounced: false,
      }),
    ).toEqual(["Receber na retirada: Abra um turno de caixa para registrar o acerto."]);
  });

  it("o Aceitar travado mostra o motivo sem depender de hover", () => {
    expect(
      blockedReasonLines({
        primary: aff({ disabled: true, reason: "Cancelamento solicitado ao iFood. Aguardando confirmação." }),
        primaryLabel: "Aceitar",
        secondary: [aff({ ref: "reject", label: "Recusar", priority: "danger" })],
        blockAnnounced: false,
      }),
    ).toEqual(["Aceitar: Cancelamento solicitado ao iFood. Aguardando confirmação."]);
  });

  it("dois botões com o mesmo motivo e um livre: os dois nomes na frente", () => {
    expect(
      blockedReasonLines({
        primary: aff({ ref: "advance", label: "Marcar pronto" }), primaryLabel: "Marcar pronto",
        secondary: [
          aff({ ref: "settle_cash", label: "Acertar entrega", disabled: true, reason: PERMISSION }),
          aff({ ref: "equipment_back", label: "Maquininha voltou", disabled: true, reason: PERMISSION }),
        ],
        blockAnnounced: false,
      }),
    ).toEqual([`Acertar entrega e Maquininha voltou: ${PERMISSION}`]);
  });

  it("o bloqueio que o cartão já anuncia na pílula não se repete sob o botão", () => {
    const lines = blockedReasonLines({
      primary: aff({ disabled: true, reason: "Pagamento ainda não confirmado. Aceite o pedido quando o dinheiro entrar." }),
      primaryLabel: "Aceitar",
      secondary: [aff({ ref: "reject", label: "Recusar", priority: "danger" })],
      blockAnnounced: true,
    });
    expect(lines).toEqual([]);
  });

  it("com o bloqueio anunciado, o outro botão travado continua dizendo o seu motivo", () => {
    const lines = blockedReasonLines({
      primary: aff({ disabled: true, reason: PERMISSION }), primaryLabel: "Aceitar",
      secondary: [aff({ ref: "reject", label: "Recusar", priority: "danger", disabled: true, reason: PERMISSION })],
      blockAnnounced: true,
    });
    expect(lines).toEqual([`Recusar: ${PERMISSION}`]);
  });

  it("botão travado sem motivo do servidor não inventa frase", () => {
    expect(
      blockedReasonLines({
        primary: aff({ disabled: true, reason: "" }), primaryLabel: "Aceitar", secondary: [], blockAnnounced: false,
      }),
    ).toEqual([]);
  });
});

describe("blockPillLabel: a pílula do bloqueio diz o fato (P2-16)", () => {
  it("o bloqueio aparece pelo nome que o servidor deu, não pela pergunta", () => {
    expect(blockPillLabel("Pix expirado")).toBe("Pix expirado");
    expect(blockPillLabel("Cobrança recusada")).toBe("Cobrança recusada");
  });

  it("as reticências do rótulo de espera não vão para a pílula", () => {
    expect(blockPillLabel("Aguardando Pix…")).toBe("Aguardando Pix");
    expect(blockPillLabel("Aguardando o dia da encomenda…")).toBe("Aguardando o dia da encomenda");
  });

  it("sem nome de bloqueio do servidor, fica a pergunta", () => {
    expect(blockPillLabel("")).toBe("Por que espera");
    expect(blockPillLabel("  ")).toBe("Por que espera");
    expect(blockPillLabel(undefined)).toBe("Por que espera");
    expect(blockPillLabel(null)).toBe("Por que espera");
  });
});

describe("lockedButtonRepeatsPill: o botão morto que só repete a pílula sai (P1-16)", () => {
  const locked = aff({ ref: "advance", label: "Iniciar preparo", disabled: true, reason: "Pagamento ainda não foi confirmado." });

  it("o avanço travado com o nome do bloqueio repete a pílula", () => {
    expect(
      lockedButtonRepeatsPill({ primary: locked, primaryLabel: "Pix expirado", blockLabel: "Pix expirado", blockAnnounced: true }),
    ).toBe(true);
    expect(
      lockedButtonRepeatsPill({ primary: locked, primaryLabel: "Aguardando Pix", blockLabel: "Aguardando Pix…", blockAnnounced: true }),
    ).toBe(true);
  });

  it("sem a pílula no cartão, o botão travado fica: é o único lugar do fato", () => {
    expect(
      lockedButtonRepeatsPill({ primary: locked, primaryLabel: "Pix expirado", blockLabel: "Pix expirado", blockAnnounced: false }),
    ).toBe(false);
  });

  it("o Aceitar travado guarda o nome do gesto e fica", () => {
    expect(
      lockedButtonRepeatsPill({
        primary: aff({ disabled: true, reason: "Pagamento ainda não confirmado." }),
        primaryLabel: "Aceitar", blockLabel: "Aguardando Pix…", blockAnnounced: true,
      }),
    ).toBe(false);
  });

  it("botão livre nunca sai", () => {
    expect(
      lockedButtonRepeatsPill({ primary: aff({ ref: "advance", label: "Iniciar preparo" }), primaryLabel: "Iniciar preparo", blockLabel: "", blockAnnounced: false }),
    ).toBe(false);
    expect(lockedButtonRepeatsPill({ primary: null, primaryLabel: "", blockLabel: "Pix expirado", blockAnnounced: true })).toBe(false);
  });
});
