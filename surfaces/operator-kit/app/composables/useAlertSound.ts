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

/** Uma nota: altura, quando entra, quanto dura, e o peso dela na figura. */
export interface AlertNote {
  /** Frequência em Hz. */
  f: number;
  /** Início, em segundos desde o começo do aviso. */
  t: number;
  /** Duração, em segundos. Notas que se SOBREPÕEM soam como acorde. */
  d: number;
  /** Peso relativo (0..1). Ausente = 1. Serve para acentuar um tempo. */
  g?: number;
}

/**
 * Uma parcial do timbre: razão sobre a fundamental, peso e quanto ela dura
 * em relação à nota. Razões INTEIRAS soam como instrumento afinado; razões
 * quebradas (2.76, 5.4) soam como sino — e é a inarmonicidade que faz o som
 * atravessar conversa.
 */
export interface AlertPartial {
  r: number;
  g: number;
  d: number;
}

/** Banda do alto-falante. Aplicada em série, na ordem dada. */
export interface AlertFilter {
  type: BiquadFilterType;
  freq: number;
  q?: number;
}

/** Rabo de sala: delay realimentado com amortecimento. `mix` 0..1. */
export interface AlertSpace {
  time: number;
  feedback: number;
  mix: number;
}

export interface AlertSoundOptions {
  /** Ganho de pico de cada nota (0..1). Padrão 0.6 — audível sobre ruído de salão. */
  volume?: number;
  /** A figura: quais notas, quando e por quanto tempo. */
  notes?: readonly AlertNote[];
  /** Onda do oscilador. Ignorada quando há `partials` (que somam senoides). */
  wave?: OscillatorType;
  /**
   * Envoltória. `swell` cresce e decai (sino soprado); `ping` bate e decai
   * (percussão). É o que separa "toque" de "batida".
   */
  shape?: "ping" | "swell";
  /**
   * Ataque em segundos. 4 ms é martelo duro de xilofone; 22 ms é baqueta de
   * feltro. É a diferença entre "estalo" e "macio", e não tem relação com os
   * parciais — foi a primeira coisa que o dono apontou ao ouvir os candidatos.
   */
  attack?: number;
  /** Timbre. Ausente = uma onda simples de `wave`. */
  partials?: readonly AlertPartial[];
  /** Banda do alto-falante. Ausente = espectro inteiro. */
  filters?: readonly AlertFilter[];
  /** Ambiente. Ausente = seco. */
  space?: AlertSpace | null;
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

// Tríade maior ascendente (A5 · C#6 · E6). É o que o KDS toca.
const DEFAULT_NOTES: readonly AlertNote[] = [
  { f: 880, t: 0, d: 0.14 },
  { f: 1108.73, t: 0.14, d: 0.14 },
  { f: 1318.51, t: 0.28, d: 0.14 },
];

export function useAlertSound(storageKey: string, options: AlertSoundOptions = {}) {
  const volume = options.volume ?? 0.6;
  const notes = options.notes ?? DEFAULT_NOTES;
  const wave = options.wave ?? "triangle";
  const shape = options.shape ?? "swell";
  const attack = options.attack ?? (shape === "ping" ? 0.004 : 0.02);
  const partials = options.partials ?? null;
  const filters = options.filters ?? null;
  const space = options.space ?? null;
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

  /**
   * Cadeia de um aviso: banda do alto-falante + rabo de sala.
   *
   * É criada por BEEP e desligada quando a cauda morre. Isso não é zelo
   * gratuito: `space` é um laço realimentado, e num kiosk que fica aberto por
   * dias cada aviso deixaria um grafo vivo para trás até o navegador engasgar.
   */
  function buildChain(ctx: AudioContext): { input: GainNode; outs: AudioNode[]; tail: number } {
    const input = ctx.createGain();
    let node: AudioNode = input;

    for (const f of filters ?? []) {
      const bq = ctx.createBiquadFilter();
      bq.type = f.type;
      bq.frequency.value = f.freq;
      bq.Q.value = f.q ?? 0.7;
      node.connect(bq);
      node = bq;
    }

    if (!space) {
      node.connect(ctx.destination);
      return { input, outs: [node], tail: 0 };
    }

    const dry = ctx.createGain();
    const wet = ctx.createGain();
    const delay = ctx.createDelay(1);
    const feedback = ctx.createGain();
    const damp = ctx.createBiquadFilter();
    wet.gain.value = space.mix;
    delay.delayTime.value = space.time;
    feedback.gain.value = space.feedback;
    damp.type = "lowpass";
    damp.frequency.value = 2600;
    node.connect(dry);
    dry.connect(ctx.destination);
    node.connect(delay);
    delay.connect(damp);
    damp.connect(feedback);
    feedback.connect(delay);
    delay.connect(wet);
    wet.connect(ctx.destination);
    return { input, outs: [dry, wet], tail: space.time * 14 };
  }

  function playNote(ctx: AudioContext, note: AlertNote, startAt: number, dest: AudioNode) {
    // Sem `partials`, uma onda só — `triangle` por padrão, porque os harmônicos
    // ímpares atravessam o ruído do salão sem a aspereza da quadrada. Com
    // `partials`, senoides somadas: é assim que se constrói sino e gongo.
    const voices = partials ?? [{ r: 1, g: 1, d: 1 }];
    const weight = note.g ?? 1;
    const ping = shape === "ping";

    for (const p of voices) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = partials ? "sine" : wave;
      osc.frequency.value = note.f * p.r;
      // `exponentialRamp` nunca alcança zero — daí o epsilon nas pontas.
      const peak = Math.max(0.0002, volume * p.g * weight);
      const end = startAt + note.d * (ping ? p.d : 1);
      gain.gain.setValueAtTime(0.0001, startAt);
      gain.gain.exponentialRampToValueAtTime(peak, startAt + attack);
      gain.gain.exponentialRampToValueAtTime(0.0001, Math.max(end, startAt + 0.03));
      osc.connect(gain);
      gain.connect(dest);
      osc.start(startAt);
      osc.stop(startAt + note.d + 0.05);
    }
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
    const chain = buildChain(ctx);
    let end = 0;
    for (const note of notes) {
      playNote(ctx, note, ctx.currentTime + note.t, chain.input);
      end = Math.max(end, note.t + note.d);
    }
    window.setTimeout(
      () => {
        for (const out of chain.outs) {
          try {
            out.disconnect();
          } catch {
            // já desconectado (contexto fechado) — nada a fazer
          }
        }
      },
      (end + chain.tail + 1.5) * 1000,
    );
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
