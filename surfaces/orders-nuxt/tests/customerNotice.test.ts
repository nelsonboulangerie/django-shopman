// WP-G07, "Avisar o cliente" com um toque: o que a tela faz com a leitura do servidor
// (`GET/POST orders/<ref>/customer-notice/preview/`). Quando cabe, o que cada aviso pede
// e a mensagem são do servidor; a tela só desenha e diz o que falta escolher.
import { describe, expect, it } from "vitest";

import {
  SENT_SENTENCE,
  delayItems,
  lineItems,
  messageHeading,
  missingStep,
  noticeInputs,
  noticeItems,
  noticeTitle,
  pickedNotice,
  type CustomerNoticeOptions,
} from "../app/presentation/customerNotice";

const options: CustomerNoticeOptions = {
  ref: "2026-11-20-A17",
  payload_schema: { base_revision: "r1", expected_actor_id: 7 },
  notices: [
    {
      kind: "delayed",
      label: "Vai atrasar",
      enabled: true,
      reason: "",
      delay_choices: [
        { value: "2026-11-20T16:30:00-03:00", label: "16h30 (em 30 min)" },
        { value: "2026-11-20T17:00:00-03:00", label: "17h (em 1 hora)" },
      ],
      lines: [],
    },
    {
      kind: "item_missing",
      label: "Faltou um item",
      enabled: true,
      reason: "",
      delay_choices: [],
      lines: [
        { line_id: "L1", name: "Focaccia", qty: "2", qty_display: "2 unidades" },
        { line_id: "L2", name: "Brioche", qty: "1", qty_display: "1 unidade" },
      ],
    },
    {
      kind: "reschedule",
      label: "Precisamos remarcar",
      enabled: false,
      reason: "Só a encomenda tem data combinada para remarcar.",
      delay_choices: [],
      lines: [],
    },
  ],
};

describe("Avisar o cliente", () => {
  it("lista os três avisos na ordem do servidor, e o travado escreve o motivo", () => {
    expect(noticeItems(options.notices).map((item) => [item.label, item.disabled, item.description])).toEqual([
      ["Vai atrasar", false, undefined],
      ["Faltou um item", false, undefined],
      ["Precisamos remarcar", true, "Só a encomenda tem data combinada para remarcar."],
    ]);
  });

  it("aviso travado nunca conta como marcado", () => {
    expect(pickedNotice(options, "reschedule")).toBeNull();
    expect(pickedNotice(options, "")).toBeNull();
    expect(pickedNotice(options, "delayed")?.label).toBe("Vai atrasar");
  });

  it("as horas prontas e os itens viram toques, sem campo", () => {
    const delayed = pickedNotice(options, "delayed");
    expect(delayItems(delayed).map((item) => item.label)).toEqual(["16h30 (em 30 min)", "17h (em 1 hora)"]);
    const missing = pickedNotice(options, "item_missing");
    expect(lineItems(missing).map((item) => [item.label, item.description])).toEqual([
      ["Focaccia", "2 unidades"],
      ["Brioche", "1 unidade"],
    ]);
  });

  it("diz o que falta escolher antes de mostrar a mensagem", () => {
    const pick = { kind: "" as const, eta: "", lines: [] };
    expect(missingStep(null, pick)).toBe("Escolha o aviso para ver a mensagem.");
    const delayed = pickedNotice(options, "delayed");
    expect(missingStep(delayed, { ...pick, kind: "delayed" })).toBe("Escolha a nova previsão para ver a mensagem.");
    expect(missingStep(delayed, { ...pick, kind: "delayed", eta: "x" })).toBe("");
    const missing = pickedNotice(options, "item_missing");
    expect(missingStep(missing, { ...pick, kind: "item_missing" })).toBe("Marque o que vai faltar para ver a mensagem.");
  });

  it("manda só o que o aviso pede, com os itens na ordem do pedido", () => {
    const missing = pickedNotice(options, "item_missing")!;
    expect(noticeInputs(missing, { kind: "item_missing", eta: "", lines: ["L2", "L1"] })).toEqual({
      kind: "item_missing",
      lines: [{ line_id: "L1" }, { line_id: "L2" }],
    });
    const delayed = pickedNotice(options, "delayed")!;
    expect(noticeInputs(delayed, { kind: "delayed", eta: "2026-11-20T16:30:00-03:00", lines: ["L1"] })).toEqual({
      kind: "delayed",
      eta: "2026-11-20T16:30:00-03:00",
    });
  });

  it("nunca diz enviado: a fila e o recibo do pedido", () => {
    expect(SENT_SENTENCE).not.toMatch(/enviad/i);
    expect(SENT_SENTENCE).toContain("Avisos ao cliente");
    expect(noticeTitle("A17")).toBe("Avisar o cliente do pedido A17");
    expect(messageHeading(" ")).toBe("Mensagem para o cliente");
  });
});
