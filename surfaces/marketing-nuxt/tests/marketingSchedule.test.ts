import { describe, expect, it } from "vitest";
import {
  resolveScheduleInput,
  suggestedScheduleLocal,
  zonedScheduleCandidates,
} from "~/utils/marketingSchedule";

describe("canonical marketing schedule", () => {
  it("turns a shop wall time into one offset-bearing instant", () => {
    const result = resolveScheduleInput({
      localValue: "2026-09-10T08:00",
      timeZone: "America/Sao_Paulo",
      nowMs: Date.parse("2026-09-09T12:00:00Z"),
    });

    expect(result.ok).toBe(true);
    expect(result.candidate?.instant).toBe("2026-09-10T08:00:00-03:00");
  });

  it("refuses a wall time erased by spring DST", () => {
    const result = resolveScheduleInput({
      localValue: "2026-03-08T02:30",
      timeZone: "America/New_York",
      nowMs: Date.parse("2026-03-01T12:00:00Z"),
    });

    expect(result.problem).toBe("nonexistent");
    expect(result.detail).toContain("não existe");
  });

  it("makes both fall DST occurrences visible and waits for a choice", () => {
    const candidates = zonedScheduleCandidates(
      "2026-11-01T01:30",
      "America/New_York",
    );
    const undecided = resolveScheduleInput({
      localValue: "2026-11-01T01:30",
      timeZone: "America/New_York",
      nowMs: Date.parse("2026-10-31T12:00:00Z"),
    });
    const later = resolveScheduleInput({
      localValue: "2026-11-01T01:30",
      timeZone: "America/New_York",
      fold: "later",
      nowMs: Date.parse("2026-10-31T12:00:00Z"),
    });

    expect(candidates.map(item => item.offset)).toEqual(["-04:00", "-05:00"]);
    expect(undecided.problem).toBe("ambiguous");
    expect(later.candidate?.instant).toBe("2026-11-01T01:30:00-05:00");
  });

  it("blocks a schedule at the expiry boundary before submitting", () => {
    const result = resolveScheduleInput({
      localValue: "2026-09-10T10:00",
      timeZone: "America/Sao_Paulo",
      nowMs: Date.parse("2026-09-09T12:00:00Z"),
      expiresAt: "2026-09-10T10:00:00-03:00",
    });

    expect(result.problem).toBe("after_expiry");
  });

  it("blocks WhatsApp quiet hours and supplies the next permitted time", () => {
    const result = resolveScheduleInput({
      localValue: "2026-09-09T20:00",
      timeZone: "America/Sao_Paulo",
      nowMs: Date.parse("2026-09-09T12:00:00Z"),
      directMessage: true,
    });

    expect(result.problem).toBe("quiet_hours");
    expect(result.nextAllowedLocal).toBe("2026-09-10T08:00");
  });

  it("uses the server suggestion and never infers the browser timezone", () => {
    expect(suggestedScheduleLocal({
      timeZone: "America/Sao_Paulo",
      suggestedAt: "2026-09-10T08:00:00-03:00",
      nowMs: Date.parse("2026-09-09T12:00:00Z"),
    })).toBe("2026-09-10T08:00");
  });
});
