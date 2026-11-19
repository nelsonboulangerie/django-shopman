import { describe, expect, it } from "vitest";

import type { Affordance } from "../app/presentation/board";
import {
  OPEN_ORDER_LABEL,
  blockedReasonLines,
  cardNoticeView,
} from "../app/presentation/cardBlocks";

// WP-G06 (laudo do Gestor, P1-12, P2-13, P2-16): o motivo do botão travado vai escrito,
// a pílula diz o fato e o botão que só abre o pedido diz que abre.

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

describe("cardNoticeView: a pílula diz o fato", () => {
  const block = (over: Record<string, unknown> = {}) => ({
    key: "block", label: "Por que espera", title: "Pix expirado", ...over,
  });

  it("o bloqueio aparece pelo nome, não pela pergunta (P2-16)", () => {
    expect(cardNoticeView(block()).label).toBe("Pix expirado");
    expect(cardNoticeView(block({ title: "Cobrança recusada" })).label).toBe("Cobrança recusada");
  });

  it("sem nome de bloqueio do servidor, fica a pergunta: 'Bloqueado' repetiria o selo", () => {
    expect(cardNoticeView(block({ title: "Bloqueado" })).label).toBe("Por que espera");
    expect(cardNoticeView(block({ title: "" })).label).toBe("Por que espera");
  });

  it("o botão do aviso da NFC-e só abre o pedido, e diz que abre (P2-13)", () => {
    const shown = cardNoticeView({
      key: "fiscal", label: "NFC-e não autorizada", title: "NFC-e não autorizada",
      actions: [{ label: "Abrir e reprocessar", to: "/NB-261118-W33", "data-fiscal-failed-open": "" }],
    });
    expect(shown.actions).toEqual([
      { label: OPEN_ORDER_LABEL, to: "/NB-261118-W33", "data-fiscal-failed-open": "" },
    ]);
    expect(OPEN_ORDER_LABEL).toBe("Abrir o pedido");
  });

  it("os outros avisos passam como vieram", () => {
    const danfe = { key: "danfe", label: "DANFE não impressa", title: "DANFE não impressa", actions: [{ label: "Imprimir DANFE" }] };
    expect(cardNoticeView(danfe)).toBe(danfe);
    const reminder = { key: "courier-reminder", label: "Chamar entregador?", title: "Em preparo há 12 min", actions: [{ label: "Chamar entregador", to: "/NB-1#call" }] };
    expect(cardNoticeView(reminder)).toBe(reminder);
  });
});
