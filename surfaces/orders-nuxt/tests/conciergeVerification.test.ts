// O "vou verificar" da Concierge no sino do Gestor (WP-07): o cartão que se resolve com
// uma resposta escrita, ou assumindo a conversa. Os rótulos vêm do servidor (ações da
// projeção do sino); o campo, o limite e as frases dos três desfechos são daqui.
import { describe, expect, it } from "vitest";

import { operatorAlertToInbox } from "../../operator-kit/app/presentation/suiteChrome";
import {
  ANSWER_FAILED,
  ANSWER_HINT,
  ANSWER_MAX_LENGTH,
  ANSWER_PLACEHOLDER,
  ANSWER_SENT,
  isFinalAnswerError,
  TAKE_OVER_FAILED,
  TAKEN_OVER,
  TAKEN_OVER_NOTICE_NOT_SENT,
  verificationActions,
  verificationInbox,
} from "../app/presentation/conciergeVerification";
import type { AlertProjection } from "../app/types/orders";

function action(kind: string, label: string, path: string) {
  return {
    ref: `${kind}:31`,
    kind,
    label,
    enabled: true,
    href: `/api/v1/backstage/alerts/31/concierge-verification/${path}/`,
    source_alert_effect: "resolves",
  };
}

const CARD: AlertProjection = {
  pk: 31,
  type: "concierge_verify",
  type_label: "WhatsApp: cliente esperando a resposta da equipe",
  severity: "warning",
  severity_label: "Aviso",
  message: "Pergunta do cliente: “vocês têm estacionamento”.\nA Concierge prometeu a resposta em até 10 minutos.",
  order_ref: "",
  created_at_display: "19/11 às 12h45",
  actions: [
    action("answer_concierge_verification", "Responder ao cliente", "answer"),
    action("take_over_conversation", "Assumir a conversa", "take-over"),
    { ref: "acknowledge:31", kind: "acknowledge_alert", label: "Visto", enabled: true, href: "/api/v1/backstage/alerts/31/ack/" },
  ],
};

describe("cartão de verificação da Concierge", () => {
  it("troca o gesto direto pelo campo de resposta e pelo Assumir a conversa", () => {
    const item = { ...operatorAlertToInbox(CARD), ...verificationInbox(CARD) };

    expect(item.actLabel).toBeUndefined();
    expect(item.answer).toEqual({
      label: "Responder ao cliente",
      placeholder: ANSWER_PLACEHOLDER,
      maxLength: ANSWER_MAX_LENGTH,
      hint: ANSWER_HINT,
      altLabel: "Assumir a conversa",
    });
    expect(item.canAck).toBe(true);
    expect(item.message).toContain("estacionamento");
  });

  it("assumir abre o Live Chat daquela conversa no mesmo gesto", () => {
    const card: AlertProjection = {
      ...CARD,
      actions: [
        ...CARD.actions!,
        {
          ref: "open_live_chat:31", kind: "open_live_chat", label: "Responder no Live Chat", enabled: true,
          href: `https://app.manychat.com/fb486126/chat/4605`, source_alert_effect: "",
        },
      ],
    };
    const item = { ...operatorAlertToInbox(card), ...verificationInbox(card) };

    expect(item.answer?.altHref).toBe(`https://app.manychat.com/fb486126/chat/4605`);
    expect(item.answer?.altNoteHref).toBeUndefined();
    expect(item.href).toBeUndefined(); // não vira um botão solto no cartão
  });

  it("sem a conta do Live Chat, o cartão diz por que e leva a configurar", () => {
    const card: AlertProjection = {
      ...CARD,
      actions: [
        ...CARD.actions!,
        {
          ref: "configure_live_chat:31", kind: "configure_live_chat", label: "Configurar o Live Chat", enabled: true,
          reason: "Assumir não abre a conversa do ManyChat: falta a conta do Live Chat no Admin.",
          href: `https://admin.exemplo.com/admin/shop/shopintegrations/1/change/`, source_alert_effect: "",
        },
      ],
    };
    const item = verificationInbox(card);

    expect(item.answer?.altHref).toBeUndefined();
    expect(item.answer?.altNote).toContain("Assumir não abre a conversa do ManyChat: falta a conta do Live Chat no Admin.");
    expect(item.answer?.altNoteHref).toBe(`https://admin.exemplo.com/admin/shop/shopintegrations/1/change/`);
    expect(item.answer?.altNoteLabel).toBe("Configurar o Live Chat");
  });

  it("acha as duas rotas que o servidor ofereceu", () => {
    const { answer, takeOver } = verificationActions(CARD);
    expect(answer?.href).toBe("/api/v1/backstage/alerts/31/concierge-verification/answer/");
    expect(takeOver?.href).toBe("/api/v1/backstage/alerts/31/concierge-verification/take-over/");
  });

  it("na janela do aviso, a linha do prazo sai: o relógio já diz a hora", () => {
    const card: AlertProjection = {
      ...CARD,
      message: "“amanhã vai ter pão de forma?”\nPrometemos responder até 16h12.",
      respond_by_iso: "2026-11-19T19:12:00Z",
    };
    const item = verificationInbox(card);
    expect(item.urgentMessage).toBe("“amanhã vai ter pão de forma?”");
    expect(verificationInbox(CARD).urgentMessage).toBeUndefined();
  });

  it("só a janela fechada é erro definitivo", () => {
    expect(isFinalAnswerError("window_closed")).toBe(true);
    for (const code of ["not_sent", "house_rule_held", "empty_answer", undefined, null]) {
      expect(isFinalAnswerError(code)).toBe(false);
    }
  });

  it("aviso de outro tipo fica como estava", () => {
    const other: AlertProjection = { ...CARD, type: "stale_new_order", actions: [CARD.actions[2]!] };
    expect(verificationInbox(other)).toEqual({});
  });

  it("sem o Assumir oferecido, só o Responder", () => {
    const only: AlertProjection = { ...CARD, actions: [CARD.actions[0]!] };
    expect(verificationInbox(only).answer?.altLabel).toBeUndefined();
  });

  it("a copy dos desfechos não usa travessão", () => {
    for (const text of [ANSWER_PLACEHOLDER, ANSWER_HINT, ANSWER_SENT, TAKEN_OVER, TAKEN_OVER_NOTICE_NOT_SENT, ANSWER_FAILED, TAKE_OVER_FAILED]) {
      expect(text).not.toMatch(/[—–]/);
    }
  });
});

describe("promotionToast (WP-15)", () => {
  it("criado, já existia e o alerta de data", async () => {
    const { promotionToast, PROMOTED, ALREADY_PROMOTED } = await import("../app/presentation/conciergeVerification");
    expect(promotionToast({ admin_url: `https://a/x` })).toEqual({
      color: "success", title: PROMOTED, action: { label: "Abrir no Admin", to: `https://a/x` },
    });
    expect(promotionToast({ already: true })).toEqual({ color: "info", title: ALREADY_PROMOTED });
    expect(promotionToast({ warning: "A resposta cita um dia." })).toMatchObject({
      color: "warning", description: "A resposta cita um dia.",
    });
  });
});
