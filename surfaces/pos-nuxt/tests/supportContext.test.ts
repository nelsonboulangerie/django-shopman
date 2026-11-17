import { describe, expect, it } from "vitest";

import { posSupportContext } from "../app/presentation/supportContext";

describe("presentation/supportContext", () => {
  it("manda app, tela, posto e terminal", () => {
    expect(
      posSupportContext({ route: "/", station: "pdv-02", terminal: "PDV-02" }),
    ).toEqual({
      app: "pos",
      route: "/",
      workstation_ref: "pdv-02",
      terminal_ref: "PDV-02",
    });
  });

  it("não manda ref vazia", () => {
    expect(posSupportContext({ route: "/preorders", station: "", terminal: "" })).toEqual({
      app: "pos",
      route: "/preorders",
    });
  });
});
