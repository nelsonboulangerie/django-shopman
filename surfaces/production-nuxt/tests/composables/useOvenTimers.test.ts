import { describe, expect, it } from "vitest";
import "../../../operator-kit/tests/support/installGlobals"; // stubs `ref` etc. before the singleton module evaluates
import { restoreOvenTimers, useOvenTimers } from "~/composables/useOvenTimers";

// useOvenTimers is a device-local singleton (its ticker + chime + AudioContext are
// client-only, so ringing/sound is e2e/manual territory). Here we cover the pure,
// unit-observable part: the arm→get→clear dictionary and the minutes clamp.
describe("useOvenTimers", () => {
  it("arms a timer under its key and reads it back; clear removes it", () => {
    const oven = useOvenTimers();
    oven.arm("wo-1", 15);
    expect(oven.get("wo-1")?.minutes).toBe(15);
    oven.clear("wo-1");
    expect(oven.get("wo-1")).toBeNull();
  });

  it("clamps minutes to a whole number ≥ 1 (no zero/sub-minute reminders)", () => {
    const oven = useOvenTimers();
    oven.arm("wo-clamp-a", 0.4);
    expect(oven.get("wo-clamp-a")?.minutes).toBe(1);
    oven.arm("wo-clamp-b", 15.7);
    expect(oven.get("wo-clamp-b")?.minutes).toBe(16);
    oven.clear("wo-clamp-a");
    oven.clear("wo-clamp-b");
  });

  it("a freshly armed timer is not yet ringing", () => {
    const oven = useOvenTimers();
    oven.arm("wo-2", 20);
    expect(oven.isRinging("wo-2")).toBe(false);
    oven.clear("wo-2");
  });

  it("get/isRinging/remainingLabel are safe for an unknown key", () => {
    const oven = useOvenTimers();
    expect(oven.get("nope")).toBeNull();
    expect(oven.isRinging("nope")).toBe(false);
    expect(oven.remainingLabel("nope")).toBe("");
  });

  it("Visto is only accepted after expiry and keeps the timer until the production action clears it", () => {
    const oven = useOvenTimers();
    oven.arm("wo-seen", 1);
    oven.seen("wo-seen");
    expect(oven.isSeen("wo-seen")).toBe(false);

    const timer = oven.get("wo-seen");
    expect(timer).not.toBeNull();
    if (timer) timer.endsAt = Date.now() - 1;
    oven.seen("wo-seen");

    expect(oven.isSeen("wo-seen")).toBe(true);
    expect(oven.get("wo-seen")).not.toBeNull();
    oven.clear("wo-seen");
  });

  it("extending a seen timer rearms it", () => {
    const oven = useOvenTimers();
    oven.arm("wo-rearm", 1);
    const timer = oven.get("wo-rearm");
    expect(timer).not.toBeNull();
    if (timer) timer.endsAt = Date.now() - 1;
    oven.seen("wo-rearm");
    expect(oven.isSeen("wo-rearm")).toBe(true);

    oven.extend("wo-rearm", 5);

    expect(oven.isSeen("wo-rearm")).toBe(false);
    expect(oven.get("wo-rearm")?.endsAt).toBeGreaterThan(Date.now());
    oven.clear("wo-rearm");
  });

  it("reload preserva alarmes vistos ou não vistos até a produção limpá-los", () => {
    const now = Date.now();

    const restored = restoreOvenTimers(
      {
        unseen: { endsAt: now - 3 * 60 * 60 * 1000, minutes: 15 },
        seen: {
          endsAt: now - 3 * 60 * 60 * 1000,
          minutes: 15,
          seenAt: now - 2 * 60 * 60 * 1000,
        },
      },
      now,
    );

    expect(restored.unseen).toBeDefined();
    expect(restored.seen).toBeDefined();
  });

  it("não descarta um timer antigo que acabou de ser marcado Visto", () => {
    const now = Date.now();
    const restored = restoreOvenTimers(
      {
        recentSeen: {
          endsAt: now - 3 * 60 * 60 * 1000,
          minutes: 15,
          seenAt: now - 60 * 1000,
        },
      },
      now,
    );

    expect(restored.recentSeen).toBeDefined();
  });
});
