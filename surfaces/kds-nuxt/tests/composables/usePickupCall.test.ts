import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { usePickupCall } from "~/composables/usePickupCall";
import {
  newlyReadyRefs,
  PICKUP_CALL_MS,
  PICKUP_CALL_NOTES,
} from "~/presentation/pickup";

const env = installNuxtGlobals();

describe("newlyReadyRefs: quem acabou de ficar pronto", () => {
  it("a primeira leitura não chama: o que já estava pronto quando o painel abriu fica quieto", () => {
    expect(newlyReadyRefs(null, ["WEB-0006"]).fresh).toEqual([]);
  });

  it("chama só o número que entrou em Pronto desde a leitura anterior", () => {
    const { ready } = newlyReadyRefs(null, ["WEB-0006"]);
    expect(newlyReadyRefs(ready, ["WEB-0007", "WEB-0006"]).fresh).toEqual([
      "WEB-0007",
    ]);
  });

  it("um número que saiu e voltou chama outra vez", () => {
    const first = newlyReadyRefs(null, ["WEB-0006"]).ready;
    const gone = newlyReadyRefs(first, []).ready;
    expect(newlyReadyRefs(gone, ["WEB-0006"]).fresh).toEqual(["WEB-0006"]);
  });
});

describe("usePickupCall: o Painel de retirada chama", () => {
  const beep = vi.fn(() => true);

  beforeEach(() => {
    env.reset();
    beep.mockClear();
    vi.useFakeTimers();
    vi.stubGlobal(
      "useAlertSound",
      (_key: string, options: { notes?: unknown }) => {
        expect(options.notes).toBe(PICKUP_CALL_NOTES);
        return {
          soundOn: ref(true),
          soundBlocked: ref(false),
          activateSound: vi.fn(),
          beep,
        };
      },
    );
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("o recém-pronto fica em destaque por alguns segundos e a TV toca uma vez", async () => {
    const ready = ref<string[]>(["WEB-0006"]);
    const { isCalling } = usePickupCall(ready);
    expect(isCalling("WEB-0006")).toBe(false);
    expect(beep).not.toHaveBeenCalled();

    ready.value = ["WEB-0007", "WEB-0006"];
    await nextTick();
    expect(isCalling("WEB-0007")).toBe(true);
    expect(isCalling("WEB-0006")).toBe(false);
    expect(beep).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(PICKUP_CALL_MS);
    expect(isCalling("WEB-0007")).toBe(false);
  });

  it("releitura igual (poll de reserva, evento repetido) não chama de novo", async () => {
    const ready = ref<string[]>([]);
    usePickupCall(ready);
    ready.value = ["WEB-0007"];
    await nextTick();
    ready.value = ["WEB-0007"];
    await nextTick();
    expect(beep).toHaveBeenCalledTimes(1);
  });
});
