import { describe, expect, it } from "vitest";

import { shouldPollTick } from "../app/presentation/events";

describe("shouldPollTick — o poll é fallback, não segundo canal", () => {
  it("com o SSE vivo, o tick não refaz nada (o push já refez)", () => {
    expect(shouldPollTick("live")).toBe(false);
  });

  it("sem o SSE de pé, o tick carrega a tela", () => {
    expect(shouldPollTick("polling")).toBe(true);
    // Conectando ainda não é vivo: até o onopen, quem garante dado é o poll.
    expect(shouldPollTick("connecting")).toBe(true);
  });
});
