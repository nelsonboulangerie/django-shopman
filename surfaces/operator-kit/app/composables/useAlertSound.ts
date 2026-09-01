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
export function useAlertSound(storageKey: string) {
  const soundOn = ref(true);
  // Som BLOQUEADO pela política de autoplay: só é true com o som LIGADO e o
  // contexto fora de "running" (mudo de fato, não mudo por escolha).
  const soundBlocked = ref(false);

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
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.2, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.25);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.25);
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
    // Primeiro gesto na tela destrava o áudio (a política de autoplay exige um).
    const onGesture = () => primeAudio();
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
    if (removeGestureListeners) removeGestureListeners();
  });

  return { soundOn, soundBlocked, toggleSound, beep, primeAudio };
}
