import { describe, expect, it } from "vitest";

import { isIdleBeyond } from "../app/utils/operatorLock";

describe("operator lock — idle / auto-lock", () => {
  it("locks once idle reaches the timeout", () => {
    expect(isIdleBeyond(0, 60_000, 60)).toBe(true);
    expect(isIdleBeyond(0, 59_000, 60)).toBe(false);
  });

  it("never auto-locks when timeout is disabled (<= 0)", () => {
    expect(isIdleBeyond(0, 9_999_999, 0)).toBe(false);
    expect(isIdleBeyond(0, 9_999_999, -1)).toBe(false);
  });
});
