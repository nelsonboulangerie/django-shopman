import { describe, expect, it } from "vitest";

import { homologationClock } from "../app/presentation/homologationBand";

describe("homologationClock", () => {
  it("data, hora com segundos e o fuso", () => {
    const text = homologationClock(new Date(2026, 10, 17, 9, 5, 7));
    expect(text).toMatch(/^17\/11\/2026 09:05:07 \(UTC[+-]\d{2}:\d{2}\)$/);
  });
});
