import { describe, expect, it } from "vitest";

import { contactRequestNotice } from "../app/presentation/contactRequest";

describe("ouvidoria aberta no pedido", () => {
  it("da avaliação: estrelas e o comentário do cliente", () => {
    const notice = contactRequestNotice({
      origin: "rating",
      rating: 2,
      comment: "Chegou frio",
      requested_at_display: "06/11 às 10:12",
    });
    expect(notice.title).toBe("Ouvidoria aberta");
    expect(notice.showsRating).toBe(true);
    expect(notice.description).toBe(
      "O cliente pediu para falar com o responsável (06/11 às 10:12). Comentário: Chegou frio",
    );
  });

  it("do cancelamento depois do preparo: sem estrelas, diz que o pedido segue", () => {
    const notice = contactRequestNotice({
      origin: "cancellation",
      rating: 0,
      comment: "",
      requested_at_display: "06/11 às 10:12",
    });
    expect(notice.title).toBe("Ouvidoria aberta: o cliente queria cancelar");
    expect(notice.showsRating).toBe(false);
    expect(notice.description).toContain("o preparo já tinha começado");
    expect(notice.description).toContain("O pedido segue");
    expect(notice.description).not.toContain("—");
  });
});
