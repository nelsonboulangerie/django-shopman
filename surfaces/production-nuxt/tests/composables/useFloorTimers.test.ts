import { describe, expect, it } from "vitest";
import "../../../operator-kit/tests/support/installGlobals"; // stubs `ref` etc. before the singleton module evaluates
import {
  floorTimerMode,
  nextFreeTimerTitle,
  restoreFloorTimers,
  useFloorTimers,
} from "~/composables/useFloorTimers";

// useFloorTimers is a device-local singleton (its ticker + chime + AudioContext are
// client-only, so ringing/sound is e2e/manual territory). Here we cover the pure,
// unit-observable part: the arm/create→get→clear dictionary, the minutes clamp,
// and the panel list (entries/activeCount/ringingCount).
describe("useFloorTimers — forno (chave = fornada)", () => {
  it("arms a timer under its key and reads it back; clear removes it", () => {
    const timers = useFloorTimers();
    timers.arm("wo-1", 15);
    expect(timers.get("wo-1")?.minutes).toBe(15);
    expect(timers.get("wo-1")?.kind).toBe("oven");
    timers.clear("wo-1");
    expect(timers.get("wo-1")).toBeNull();
  });

  it("clamps minutes to a whole number ≥ 1 (no zero/sub-minute reminders)", () => {
    const timers = useFloorTimers();
    timers.arm("wo-clamp-a", 0.4);
    expect(timers.get("wo-clamp-a")?.minutes).toBe(1);
    timers.arm("wo-clamp-b", 15.7);
    expect(timers.get("wo-clamp-b")?.minutes).toBe(16);
    timers.clear("wo-clamp-a");
    timers.clear("wo-clamp-b");
  });

  it("keeps the label and SKU the oven declared when re-armed without them", () => {
    const timers = useFloorTimers();
    timers.arm("wo-meta", 20, { label: "Croissant", sku: "CRO" });
    timers.arm("wo-meta", 25);
    expect(timers.get("wo-meta")).toMatchObject({
      label: "Croissant",
      sku: "CRO",
      minutes: 25,
    });
    timers.clear("wo-meta");
  });

  it("a freshly armed timer is not yet ringing", () => {
    const timers = useFloorTimers();
    timers.arm("wo-2", 20);
    expect(timers.isRinging("wo-2")).toBe(false);
    timers.clear("wo-2");
  });

  it("get/isRinging/remainingLabel are safe for an unknown key", () => {
    const timers = useFloorTimers();
    expect(timers.get("nope")).toBeNull();
    expect(timers.isRinging("nope")).toBe(false);
    expect(timers.remainingLabel("nope")).toBe("");
  });

  it("Visto is only accepted after expiry and keeps the timer until someone clears it", () => {
    const timers = useFloorTimers();
    timers.arm("wo-seen", 1);
    timers.seen("wo-seen");
    expect(timers.isSeen("wo-seen")).toBe(false);

    const timer = timers.get("wo-seen");
    expect(timer).not.toBeNull();
    if (timer) timer.endsAt = Date.now() - 1;
    timers.seen("wo-seen");

    expect(timers.isSeen("wo-seen")).toBe(true);
    expect(timers.get("wo-seen")).not.toBeNull();
    timers.clear("wo-seen");
  });

  it("extending a seen timer rearms it", () => {
    const timers = useFloorTimers();
    timers.arm("wo-rearm", 1);
    const timer = timers.get("wo-rearm");
    expect(timer).not.toBeNull();
    if (timer) timer.endsAt = Date.now() - 1;
    timers.seen("wo-rearm");
    expect(timers.isSeen("wo-rearm")).toBe(true);

    timers.extend("wo-rearm", 5);

    expect(timers.isSeen("wo-rearm")).toBe(false);
    expect(timers.get("wo-rearm")?.endsAt).toBeGreaterThan(Date.now());
    timers.clear("wo-rearm");
  });
});

describe("useFloorTimers — avulsos (o mais usado)", () => {
  it("create nasce com chave própria, kind free e 'Timer N' quando anônimo", () => {
    const timers = useFloorTimers();
    const a = timers.create(12);
    const b = timers.create(7);
    expect(a).not.toBe(b);
    expect(timers.get(a)).toMatchObject({ kind: "free", label: "Timer 1", minutes: 12 });
    expect(timers.get(b)).toMatchObject({ kind: "free", label: "Timer 2", minutes: 7 });
    timers.clear(a);
    timers.clear(b);
  });

  it("um nome dado vale mais que o número automático; espaços não contam como nome", () => {
    const timers = useFloorTimers();
    const named = timers.create(30, { label: "Fermentação croissant", sku: "CRO" });
    const blank = timers.create(5, { label: "   " });
    expect(timers.get(named)).toMatchObject({ label: "Fermentação croissant", sku: "CRO" });
    expect(timers.get(blank)?.label).toBe("Timer 1");
    timers.clear(named);
    timers.clear(blank);
  });

  it("entries lista todos, quem toca primeiro; activeCount e ringingCount seguem", () => {
    const timers = useFloorTimers();
    const later = timers.create(40, { label: "depois" });
    const soon = timers.create(3, { label: "logo" });
    const rang = timers.create(9, { label: "tocou" });
    const timer = timers.get(rang);
    if (timer) timer.endsAt = Date.now() - 1;

    // O relógio interno (nowMs) só anda no ticker client-side; entries usa o
    // snapshot dele, então forçamos uma leitura pelo próprio modo puro.
    expect(floorTimerMode(timers.get(rang)!, Date.now())).toBe("ringing");
    expect(floorTimerMode(timers.get(soon)!, Date.now())).toBe("running");
    expect(timers.activeCount.value).toBe(3);
    const titles = timers.entries.value.map((entry) => entry.title);
    expect(titles).toContain("depois");
    expect(titles).toContain("logo");
    expect(titles).toContain("tocou");
    expect(
      timers.entries.value.findIndex((entry) => entry.key === soon) <
        timers.entries.value.findIndex((entry) => entry.key === later),
    ).toBe(true);

    timers.clear(later);
    timers.clear(soon);
    timers.clear(rang);
    expect(timers.activeCount.value).toBe(0);
    expect(timers.ringingCount.value).toBe(0);
  });

  it("nextFreeTimerTitle pula os números já em uso", () => {
    expect(nextFreeTimerTitle({})).toBe("Timer 1");
    expect(
      nextFreeTimerTitle({
        a: { endsAt: 1, minutes: 1, label: "Timer 1" },
        b: { endsAt: 1, minutes: 1, label: "Timer 3" },
        c: { endsAt: 1, minutes: 1, label: "Croissant" },
      }),
    ).toBe("Timer 2");
  });
});

describe("useFloorTimers — reload", () => {
  it("preserva alarmes vistos ou não vistos até alguém limpá-los", () => {
    const now = Date.now();

    const restored = restoreFloorTimers(
      {
        unseen: { endsAt: now - 3 * 60 * 60 * 1000, minutes: 15 },
        seen: {
          endsAt: now - 3 * 60 * 60 * 1000,
          minutes: 15,
          seenAt: now - 2 * 60 * 60 * 1000,
        },
        free: {
          endsAt: now + 60 * 1000,
          minutes: 1,
          kind: "free",
          label: "Timer 1",
        },
      },
      now,
    );

    expect(restored.unseen).toBeDefined();
    expect(restored.seen).toBeDefined();
    expect(restored.free?.label).toBe("Timer 1");
  });

  it("descarta entradas sem endsAt/minutes numéricos (storage corrompido)", () => {
    const restored = restoreFloorTimers(
      {
        ok: { endsAt: 1, minutes: 1 },
        broken: { endsAt: "x" as unknown as number, minutes: 1 },
      },
      Date.now(),
    );
    expect(Object.keys(restored)).toEqual(["ok"]);
  });
});
