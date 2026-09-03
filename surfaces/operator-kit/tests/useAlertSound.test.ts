import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

describe("useAlertSound — o aviso que insiste", () => {
  beforeEach(() => env.reset());
  afterEach(() => vi.useRealTimers());

  // Pedido novo é compromisso com alguém que já está esperando. Um toque único
  // deixou passar pedido de cliente real no alpha: o aviso do Gestor repete até
  // alguém dar sinal de vida — mas com fim, para não virar sirene.
  it("startAlert marca aviso em curso e stopAlert encerra", () => {
    const { startAlert, stopAlert, alerting } = useAlertSound("test_sound");

    startAlert();
    expect(alerting.value).toBe(true);
    stopAlert();
    expect(alerting.value).toBe(false);
  });

  it("stopAlert é idempotente — chamar sem aviso em curso não estoura", () => {
    const { stopAlert, alerting } = useAlertSound("test_sound");

    expect(() => { stopAlert(); stopAlert(); }).not.toThrow();
    expect(alerting.value).toBe(false);
  });

  it("com o som desligado, startAlert não começa aviso nenhum", () => {
    const { startAlert, toggleSound, alerting } = useAlertSound("test_sound");

    toggleSound(); // desliga
    startAlert();
    expect(alerting.value).toBe(false);
  });

  it("mutar durante o aviso o cala na hora", () => {
    const { startAlert, toggleSound, alerting } = useAlertSound("test_sound");

    startAlert();
    expect(alerting.value).toBe(true);
    toggleSound(); // desliga
    expect(alerting.value).toBe(false);
  });

  it("o aviso desiste sozinho — repete no máximo maxRepeats e para", () => {
    vi.useFakeTimers();
    const { startAlert, alerting } = useAlertSound("test_sound", {
      repeatIntervalMs: 1_000,
      maxRepeats: 3,
    });

    startAlert();
    expect(alerting.value).toBe(true);

    vi.advanceTimersByTime(2_000); // 2 repetições — ainda avisando
    expect(alerting.value).toBe(true);

    vi.advanceTimersByTime(1_000); // atinge o teto
    expect(alerting.value).toBe(false);

    vi.advanceTimersByTime(10_000); // e não ressuscita
    expect(alerting.value).toBe(false);
  });

  it("um pedido mais novo reinicia a contagem em vez de empilhar timers", () => {
    vi.useFakeTimers();
    const { startAlert, alerting } = useAlertSound("test_sound", {
      repeatIntervalMs: 1_000,
      maxRepeats: 2,
    });

    startAlert(); // t=0 — o teto do PRIMEIRO aviso cairia em t=2000
    vi.advanceTimersByTime(500);
    startAlert(); // t=500 — chegou outro pedido; o teto agora é t=2500

    // Em t=2000 o aviso ainda está de pé: se o timer do primeiro tivesse
    // sobrevivido ao segundo `startAlert`, ele teria calado o aviso aqui.
    vi.advanceTimersByTime(1_500);
    expect(alerting.value).toBe(true);

    vi.advanceTimersByTime(1_000); // t=3000, passado o teto do segundo
    expect(alerting.value).toBe(false);
  });
});
