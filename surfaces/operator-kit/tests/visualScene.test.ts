import { describe, expect, it, vi } from "vitest";

import { waitForOperatorScene } from "../visual/playwright";

describe("waitForOperatorScene", () => {
  it("reprova quando uma remontagem tardia remove o sujeito da cena", async () => {
    const ready = { waitFor: vi.fn().mockResolvedValue(undefined) };
    const subject = {
      waitFor: vi
        .fn()
        .mockResolvedValueOnce(undefined)
        .mockRejectedValueOnce(new Error("dialog detached after late refresh")),
    };
    const page = { evaluate: vi.fn().mockResolvedValue(undefined) };

    await expect(
      waitForOperatorScene(page as never, ready as never, subject as never),
    ).rejects.toThrow("dialog detached after late refresh");
    expect(subject.waitFor).toHaveBeenCalledTimes(2);
  });

  it("aceita a cena somente quando marcador e sujeito sobrevivem à estabilização", async () => {
    const ready = { waitFor: vi.fn().mockResolvedValue(undefined) };
    const subject = { waitFor: vi.fn().mockResolvedValue(undefined) };
    const page = { evaluate: vi.fn().mockResolvedValue(undefined) };

    await waitForOperatorScene(page as never, ready as never, subject as never);

    expect(ready.waitFor).toHaveBeenCalledTimes(2);
    expect(subject.waitFor).toHaveBeenCalledTimes(2);
  });
});
