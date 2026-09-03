// Aviso sonoro de evento novo nas superfícies de operador (KDS: ticket novo;
// Gestor: pedido novo), com mute persistido por chave e desbloqueio de autoplay.
//
// Um ÚNICO AudioContext por instância, resumido no primeiro gesto do operador
// (destravar/tocar/qualquer toque) — recriar por beep garantia suspensão. O beep
// vem de um watch/SSE (não de um gesto), então um AudioContext não-primado nasce
// suspenso e tocaria MUDO: quando isso acontece, `soundBlocked` fica true para a
// UI mostrar "toque para ativar o som" em vez de falhar em silêncio.
//
// `storageKey` é do chamador (ex.: `kds_sound_<ref>` por estação no KDS,
// `gestor_sound` no Gestor) — a preferência é da superfície, não do kit.
//
// ⚠️ O aviso é dimensionado para PADARIA, não para escritório. A versão original
// tocava UMA senoide de 880 Hz a 0.2 de ganho por 250 ms: senoide pura é o timbre
// que menos corta ruído ambiente, e um toque único desses passa despercebido a
// dois metros do balcão. Um pedido de cliente real chegou e ninguém ouviu. Por
// isso o padrão agora é um arpejo de três notas em `triangle` (harmônicos ímpares
// atravessam o ruído) a 0.6 de ganho. Volume e notas seguem ajustáveis pelo
// chamador — a régua de quanto é alto demais é da superfície, não do kit.

export interface AlertSoundOptions {
  /** Ganho de pico de cada nota (0..1). Padrão 0.6 — audível sobre ruído de salão. */
  volume?: number;
  /** Notas do aviso em Hz, tocadas em sequência. Padrão: tríade maior ascendente. */
  notes?: readonly number[];
  /** Duração de cada nota, em segundos. */
  noteSeconds?: number;
  /** Intervalo entre repetições de `startAlert`, em milissegundos. */
  repeatIntervalMs?: number;
  /**
   * Quantas vezes `startAlert` repete antes de desistir sozinho. Um aviso que
   * toca para sempre vira sirene que ninguém consegue calar — e a próxima
   * reação do operador é desligar o som de vez, que é exatamente o estado que
   * este composable existe para evitar.
   */
  maxRepeats?: number;
}

const DEFAULT_NOTES = [880, 1108.73, 1318.51] as const; // A5 · C#6 · E6

export function useAlertSound(storageKey: string, options: AlertSoundOptions = {}) {
  const volume = options.volume ?? 0.6;
  const notes = options.notes ?? DEFAULT_NOTES;
  const noteSeconds = options.noteSeconds ?? 0.14;
  const repeatIntervalMs = options.repeatIntervalMs ?? 8_000;
  const maxRepeats = options.maxRepeats ?? 6;

  const soundOn = ref(true);
  // Som BLOQUEADO pela política de autoplay: só é true com o som LIGADO e o
  // contexto fora de "running" (mudo de fato, não mudo por escolha).
  const soundBlocked = ref(false);
  /** Há um aviso repetindo agora? A UI usa para oferecer "silenciar". */
  const alerting = ref(false);

  let audioCtx: AudioContext | null = null;
  function ensureCtx(): AudioContext | null {
    if (!import.meta.client) return null;
    const Ctx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return null;
    if (!audioCtx) audioCtx = new Ctx();
    return audioCtx;
  }

  /** Chamar num gesto do usuário: resume o contexto (política de autoplay). */
  function primeAudio() {
    const ctx = ensureCtx();
    if (!ctx) return;
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    soundBlocked.value = soundOn.value && ctx.state !== "running";
  }

  function playNote(ctx: AudioContext, frequency: number, startAt: number) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    // `triangle` no lugar de `sine`: os harmônicos ímpares é que fazem o aviso
    // sobreviver ao ruído do salão, sem a aspereza da onda quadrada.
    osc.type = "triangle";
    osc.frequency.value = frequency;
    // `exponentialRamp` nunca alcança zero — daí o epsilon nas pontas.
    gain.gain.setValueAtTime(0.0001, startAt);
    gain.gain.exponentialRampToValueAtTime(volume, startAt + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, startAt + noteSeconds);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(startAt);
    osc.stop(startAt + noteSeconds);
  }

  /** Um aviso: o arpejo inteiro, uma vez. */
  function beep() {
    if (!soundOn.value) return;
    const ctx = ensureCtx();
    if (!ctx) return;
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    if (ctx.state !== "running") {
      // Não conseguimos tocar sem um gesto — sinalize visualmente em vez de falhar mudo.
      soundBlocked.value = true;
      return;
    }
    soundBlocked.value = false;
    notes.forEach((frequency, index) => {
      playNote(ctx, frequency, ctx.currentTime + index * noteSeconds);
    });
  }

  let repeatTimer: ReturnType<typeof setInterval> | null = null;

  /** Para o aviso repetido. Idempotente. */
  function stopAlert() {
    alerting.value = false;
    if (!repeatTimer) return;
    clearInterval(repeatTimer);
    repeatTimer = null;
  }

  /**
   * Aviso que INSISTE: toca agora e repete até o operador dar sinal de vida
   * (qualquer toque/tecla na tela), até `stopAlert()`, ou até `maxRepeats`.
   *
   * Existe porque pedido novo é compromisso com um cliente que já está
   * esperando: avisar uma vez só e torcer para alguém estar olhando é a
   * diferença entre um pedido atendido e uma pessoa esperando pão que não vem.
   */
  function startAlert() {
    if (!soundOn.value) return;
    stopAlert(); // um aviso por vez: o pedido mais novo reinicia a contagem
    beep();
    alerting.value = true;
    let repeats = 0;
    repeatTimer = setInterval(() => {
      repeats += 1;
      if (repeats >= maxRepeats || !soundOn.value) {
        stopAlert();
        return;
      }
      beep();
    }, repeatIntervalMs);
  }

  function toggleSound() {
    soundOn.value = !soundOn.value;
    if (import.meta.client) {
      try {
        localStorage.setItem(storageKey, soundOn.value ? "on" : "off");
      } catch {
        // navegação privada/sem storage: a preferência vale só na sessão
      }
    }
    // Calar o som cala o aviso em curso — senão o gesto de mutar não teria o
    // efeito que o operador acabou de pedir.
    stopAlert();
    primeAudio(); // gesto do usuário — desbloqueia o áudio
    if (soundOn.value) beep(); // feedback imediato: ligou, ouviu
  }

  let removeGestureListeners: (() => void) | null = null;

  onMounted(() => {
    try {
      soundOn.value = localStorage.getItem(storageKey) !== "off";
    } catch {
      // sem storage: fica no padrão ligado
    }
    // Primeiro gesto na tela destrava o áudio (a política de autoplay exige um)
    // e também acusa presença: quem tocou na tela já foi avisado.
    const onGesture = () => {
      primeAudio();
      stopAlert();
    };
    window.addEventListener("pointerdown", onGesture);
    window.addEventListener("keydown", onGesture);
    removeGestureListeners = () => {
      window.removeEventListener("pointerdown", onGesture);
      window.removeEventListener("keydown", onGesture);
    };
    // Reflete o estado inicial (provável bloqueado até o 1º gesto).
    primeAudio();
  });

  onBeforeUnmount(() => {
    stopAlert();
    if (removeGestureListeners) removeGestureListeners();
  });

  return { soundOn, soundBlocked, alerting, toggleSound, beep, startAlert, stopAlert, primeAudio };
}
