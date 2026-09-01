import { beforeEach, describe, expect, it } from "vitest";

import { installNuxtGlobals } from "./support/composableEnv";
import { useAlertSound } from "../app/composables/useAlertSound";

// O aviso sonoro compartilhado (KDS: ticket novo; Gestor: pedido novo). O beep de
// verdade (AudioContext) é território de browser/e2e; aqui provamos a semântica de
// preferência e a degradação silenciosa em ambiente sem áudio.
const env = installNuxtGlobals();

describe("useAlertSound — preferência de som", () => {
  beforeEach(() => env.reset());

  it("nasce ligado e o toggle alterna", () => {
    const { soundOn, toggleSound } = useAlertSound("test_sound");
    expect(soundOn.value).toBe(true);
    toggleSound();
    expect(soundOn.value).toBe(false);
    toggleSound();
    expect(soundOn.value).toBe(true);
  });

  it("instâncias com chaves diferentes têm preferência independente", () => {
    const a = useAlertSound("kds_sound_bancada");
    const b = useAlertSound("gestor_sound");
    a.toggleSound();
    expect(a.soundOn.value).toBe(false);
    expect(b.soundOn.value).toBe(true);
  });

  it("beep sem AudioContext (node) não estoura nem marca bloqueio falso", () => {
    const { beep, soundBlocked } = useAlertSound("test_sound");
    expect(() => beep()).not.toThrow();
    expect(soundBlocked.value).toBe(false);
  });

  it("beep com som desligado é no-op silencioso", () => {
    const { beep, toggleSound, soundBlocked } = useAlertSound("test_sound");
    toggleSound(); // desliga
    expect(() => beep()).not.toThrow();
    expect(soundBlocked.value).toBe(false);
  });
});
