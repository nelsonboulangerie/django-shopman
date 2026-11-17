import { describe, expect, it } from "vitest";

import {
  pageLine,
  replyLengthHint,
  reviewErrorText,
  statusColor,
  summaryLine,
} from "../app/presentation/ifoodReviews";

describe("reviewErrorText", () => {
  it("mostra a frase da casa e, embaixo, a recusa do iFood como veio", () => {
    expect(
      reviewErrorText(
        {
          detail: "O iFood só aceita resposta em avaliação que está aguardando resposta.",
          ifood_status: 409,
          ifood_message: "Review must have status NOT_REPLIED to receive an answer",
        },
        "x",
      ),
    ).toEqual({
      title: "O iFood só aceita resposta em avaliação que está aguardando resposta.",
      ifood: "Resposta do iFood (HTTP 409): Review must have status NOT_REPLIED to receive an answer",
    });
  });

  it("sem resposta do iFood, não inventa linha de HTTP", () => {
    expect(reviewErrorText({ detail: "O iFood não respondeu.", ifood_status: 0 }, "x")).toEqual({
      title: "O iFood não respondeu.",
      ifood: "",
    });
    expect(reviewErrorText(null, "Falhou")).toEqual({ title: "Falhou", ifood: "" });
  });
});

describe("replyLengthHint", () => {
  it("orienta pelo limite do iFood e marca o que está fora", () => {
    expect(replyLengthHint("Obrigado", 10, 300)).toEqual({
      label: "8 de 10 a 300 caracteres",
      outside: true,
    });
    expect(replyLengthHint("Obrigada pelo retorno!", 10, 300).outside).toBe(false);
  });
});

describe("summaryLine e pageLine", () => {
  it("nota, total e o que conta na nota", () => {
    expect(
      summaryLine({ score: 4.3, score_display: "4,3", total_reviews: 142, valid_reviews: 53 }),
    ).toBe("Nota 4,3 · 142 avaliações (53 contam na nota)");
    expect(summaryLine(null)).toBe("");
  });

  it("página e contagem", () => {
    expect(pageLine(1, 5, 45)).toBe("Página 1 de 5 · 45 avaliações");
    expect(pageLine(1, null, null)).toBe("Página 1");
    expect(pageLine(1, 1, 1)).toBe("Página 1 de 1 · 1 avaliação");
  });
});

describe("statusColor", () => {
  it("só aguardando resposta pede ação", () => {
    expect(statusColor("NOT_REPLIED")).toBe("warning");
    expect(statusColor("PUBLISHED")).toBe("neutral");
  });
});
