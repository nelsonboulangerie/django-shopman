import { describe, expect, it } from "vitest";

import {
  EMPTY_CONFERENCE,
  VOLUME_CODE,
  applyResult,
  cardCheckBadge,
  conferenceLine,
  expectedRef,
  type VolumeCheckResponse,
} from "../app/presentation/volumeCheck";

// A conferência das sacolas no despacho (P1-13): a faixa diz o pedido em
// conferência e quantas sacolas foram bipadas; a sacola de outro pedido é o
// aviso forte e não troca a conferência em curso.

function response(overrides: Partial<VolumeCheckResponse>): VolumeCheckResponse {
  return {
    outcome: "checked", message: "", order_ref: "WEB-20261013-U68", expected_ref: "",
    volume: 1, volumes: 3, checked: 1, total: 3, complete: false, ...overrides,
  };
}

describe("conferência das sacolas", () => {
  it("o código da via casa com o formato do servidor", () => {
    expect(VOLUME_CODE.pattern.test("VP-WEB-20261013-U68-2-3-ABCDEFGH")).toBe(true);
    expect(VOLUME_CODE.pattern.test("KT-12-ABCDEFGHIJ")).toBe(false);
  });

  it("a primeira bipada abre a conferência do pedido, e ela segue até a última sacola", () => {
    const first = applyResult(EMPTY_CONFERENCE, response({}));
    expect(first.conference).toEqual({ ref: "WEB-20261013-U68", checked: 1, total: 3 });
    expect(conferenceLine(first.conference!)).toBe("Conferindo o pedido U68: 1 de 3 sacolas.");
    expect(expectedRef(first)).toBe("WEB-20261013-U68");

    const done = applyResult(first, response({ volume: 3, checked: 3, complete: true }));
    expect(conferenceLine(done.conference!)).toBe("Pedido U68: todas as 3 sacolas conferidas.");
    // Terminou: a próxima sacola é de outro pedido saindo, não um erro.
    expect(expectedRef(done)).toBe("");
  });

  it("sacola de outro pedido é o aviso forte, e a conferência em curso não muda", () => {
    const current = applyResult(EMPTY_CONFERENCE, response({}));
    const wrong = applyResult(current, response({
      outcome: "other_order", order_ref: "WEB-20261013-K12", expected_ref: "WEB-20261013-U68", checked: 0, total: 0,
    }));
    expect(wrong.conference).toEqual(current.conference);
    expect(wrong.alarm).toEqual({
      tone: "error",
      message: "Esta sacola é do pedido K12, não do U68. Separe-a antes de entregar.",
      otherRef: "WEB-20261013-K12",
    });
  });

  it("no detalhe, o pedido conferido é sempre o da tela", () => {
    expect(expectedRef(EMPTY_CONFERENCE, "WEB-1-A1")).toBe("WEB-1-A1");
  });

  it("sacola repetida e via velha avisam sem alarde", () => {
    const repeated = applyResult(EMPTY_CONFERENCE, response({ outcome: "repeated" }));
    expect(repeated.alarm).toEqual({ tone: "warning", message: "A sacola 1 de 3 do pedido U68 já foi conferida." });
    const stale = applyResult(EMPTY_CONFERENCE, response({ outcome: "stale", volumes: 1, total: 2 }));
    expect(stale.alarm?.message).toBe("Esta via diz 1 sacola, e o pedido U68 tem 2. Reimprima as vias do pedido.");
  });

  it("o cartão só fala da conferência depois da primeira bipada", () => {
    expect(cardCheckBadge({ volumes_checked: 0, volumes_to_check: 3 })).toBeNull();
    expect(cardCheckBadge({ volumes_checked: 2, volumes_to_check: 3 })).toEqual({ label: "2 de 3 conferidas", complete: false });
    expect(cardCheckBadge({ volumes_checked: 3, volumes_to_check: 3 })).toEqual({ label: "Sacolas conferidas", complete: true });
  });
});
