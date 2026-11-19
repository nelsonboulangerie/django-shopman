import { describe, expect, it } from "vitest";

import {
  emptyTitle,
  pageLine,
  replyLengthHint,
  reviewErrorText,
  reviewTabFromQuery,
  statusColor,
  summaryLine,
} from "../app/presentation/ifoodReviews";

describe("reviewErrorText", () => {
  it("uma frase em português e a mensagem original do iFood, sem HTTP", () => {
    expect(
      reviewErrorText(
        {
          detail: "Esta avaliação não aceita mais resposta: o iFood só aceita enquanto ela aguarda resposta.",
          ifood_status: 409,
          ifood_message: "Review must have status NOT_REPLIED to receive an answer",
        },
        "x",
      ),
    ).toEqual({
      title: "Esta avaliação não aceita mais resposta: o iFood só aceita enquanto ela aguarda resposta.",
      ifood: "Mensagem do iFood: Review must have status NOT_REPLIED to receive an answer",
    });
  });

  it("sem mensagem do iFood, só a frase", () => {
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
  it("todas contam: só o total", () => {
    expect(summaryLine({ score: 3.5, score_display: "3,5", total_reviews: 4, valid_reviews: 4 })).toBe(
      "Nota 3,5 · 4 avaliações",
    );
  });

  it("nem todas contam: diz quantas e por quê", () => {
    expect(
      summaryLine({ score: 4.3, score_display: "4,3", total_reviews: 142, valid_reviews: 53 }),
    ).toBe("Nota 4,3 · 142 avaliações (a nota usa as 53 dos últimos 3 meses)");
    expect(summaryLine(null)).toBe("");
  });

  it("página e contagem", () => {
    expect(pageLine(1, 5, 45)).toBe("Página 1 de 5 · 45 avaliações");
    expect(pageLine(1, null, null)).toBe("Página 1");
    expect(pageLine(1, 1, 1)).toBe("Página 1 de 1 · 1 avaliação");
  });
});

describe("abas", () => {
  it("a aba vem da query; sem ou desconhecida, a fila de quem responde", () => {
    expect(reviewTabFromQuery("replied")).toBe("replied");
    expect(reviewTabFromQuery(undefined)).toBe("waiting");
    expect(reviewTabFromQuery("x")).toBe("waiting");
    expect(emptyTitle("waiting")).toBe("Nenhuma avaliação aguardando resposta");
  });

  it("só aguardando resposta pede ação", () => {
    expect(statusColor("NOT_REPLIED")).toBe("warning");
    expect(statusColor("PUBLISHED")).toBe("neutral");
  });
});
