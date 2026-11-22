// #2515: o "Suporte" do Gestor leva o pedido em foco, não só app e tela.
import { describe, expect, it } from "vitest";

import { gestorSupportContext } from "../app/presentation/supportContext";

describe("gestorSupportContext", () => {
  it("com o pedido aberto, leva a ref dele", () => {
    expect(
      gestorSupportContext({ path: "/WEB-261121-K3P", name: "ref", params: { ref: "WEB-261121-K3P" } }),
    ).toEqual({ app: "orders", route: "/WEB-261121-K3P", focus: { kind: "order", ref: "WEB-261121-K3P" } });
  });

  it("fora da página do pedido, só app e tela", () => {
    expect(gestorSupportContext({ path: "/", name: "index", params: {} })).toEqual({ app: "orders", route: "/" });
    expect(gestorSupportContext({ path: "/history", name: "history" })).toEqual({ app: "orders", route: "/history" });
  });

  it("ref vazia não vira pedido em foco", () => {
    expect(gestorSupportContext({ path: "/", name: "ref", params: { ref: "" } })).toEqual({ app: "orders", route: "/" });
  });
});
