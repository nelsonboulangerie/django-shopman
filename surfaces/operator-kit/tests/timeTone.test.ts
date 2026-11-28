import { describe, expect, it } from "vitest";
import { timeTone } from "../app/presentation/timeTone";

describe("timeTone", () => {
  it("mantém um significado único para cada cor do tempo", () => {
    expect(timeTone("late")).toBe("late");
    expect(timeTone("warning")).toBe("warning");
    expect(timeTone("on_time")).toBe("neutral");
    expect(timeTone()).toBe("neutral");
    expect(timeTone("ready")).toBe("ready");
  });
});
