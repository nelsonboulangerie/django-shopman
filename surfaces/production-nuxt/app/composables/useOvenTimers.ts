// Timer auxiliar do forno — lembrete armado por fornada (WO). É a ferramenta
// ATIVA do forneiro; o relógio de idade do lote
// (started_at vs max_started_minutes) segue como guardrail de esquecimento
// via alertas (sino). Local ao aparelho: quem armou, ouve.
//
// Som: "dim-dom" quente em triangle wave, duas frases curtas, volume moderado
// — fácil de ouvir, fácil de conviver. Repete a cada 45s enquanto ninguém
// marca ``Visto``. O alerta não conclui o forno, o QC nem a produção.
// Padrões configuráveis via Admin ficam para o ProductionConfig (follow-up).
import { countdownLabel } from "~/presentation/production";

export interface OvenTimer {
  endsAt: number;
  minutes: number;
  /** ``Visto`` silencia o alerta, mas preserva o timer até a fornada terminar. */
  seenAt?: number;
}

const STORAGE_KEY = "producao.oven-timers";
// Chave anterior à renomeação Fournil→Produção. Lida como fallback: um turno
// em andamento não pode perder os timers de forno por causa de um deploy.
const LEGACY_STORAGE_KEY = "fournil.oven-timers";
const LAST_MINUTES_KEY = "producao.oven-timer-last-minutes";
const RECHIME_MS = 45_000;

const timers = ref<Record<string, OvenTimer>>({});
const nowMs = ref(0);
const chimes = new Map<string, { lastAt: number }>();
const lastMinutes = ref<number | null>(null);
let ticker: ReturnType<typeof setInterval> | null = null;
let audio: AudioContext | null = null;
let loaded = false;

export function restoreOvenTimers(
  parsed: Record<string, OvenTimer>,
  _now: number,
): Record<string, OvenTimer> {
  return Object.fromEntries(
    Object.entries(parsed).filter(
      ([, timer]) =>
        timer &&
        typeof timer.endsAt === "number" &&
        typeof timer.minutes === "number",
    ),
  );
}

function load() {
  if (loaded || !import.meta.client) return;
  loaded = true;
  nowMs.value = Date.now();
  try {
    const raw =
      window.localStorage.getItem(STORAGE_KEY) ??
      window.localStorage.getItem(LEGACY_STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as Record<string, OvenTimer>) : {};
    timers.value = restoreOvenTimers(parsed, Date.now());
    const storedLast = Number(window.localStorage.getItem(LAST_MINUTES_KEY));
    lastMinutes.value =
      Number.isInteger(storedLast) && storedLast > 0 ? storedLast : null;
  } catch {
    timers.value = {};
  }
  ensureTicker();
}

function persist() {
  if (!import.meta.client) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(timers.value));
  } catch {
    // storage indisponível: o timer ainda vive na sessão em memória
  }
}

function ensureTicker() {
  if (ticker || !import.meta.client) return;
  ticker = setInterval(() => {
    nowMs.value = Date.now();
    for (const key of Object.keys(timers.value)) {
      const t = timers.value[key];
      if (!t || t.seenAt != null || t.endsAt > nowMs.value) continue;
      const state = chimes.get(key) ?? { lastAt: 0 };
      if (nowMs.value - state.lastAt >= RECHIME_MS) {
        chime();
        chimes.set(key, { lastAt: nowMs.value });
      }
    }
  }, 1000);
}

/** O gesto de armar é interação do usuário — aproveita para destravar o áudio. */
function unlockAudio() {
  if (!import.meta.client) return;
  try {
    audio = audio ?? new AudioContext();
    if (audio.state === "suspended") void audio.resume();
  } catch {
    audio = null;
  }
}

function chime() {
  if (!audio) return;
  try {
    const ctx = audio;
    const note = (freq: number, at: number) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "triangle";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0, at);
      gain.gain.linearRampToValueAtTime(0.4, at + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.6);
      osc.connect(gain).connect(ctx.destination);
      osc.start(at);
      osc.stop(at + 0.65);
    };
    const t = ctx.currentTime;
    note(880, t); // dim
    note(659.25, t + 0.28); // dom
    note(880, t + 1.05); // dim (eco)
    note(659.25, t + 1.33); // dom
  } catch {
    // sem áudio: o chip pulsando segue avisando
  }
}

export function useOvenTimers() {
  load();

  function arm(key: string, minutes: number) {
    const clamped = Math.max(1, Math.round(minutes));
    unlockAudio();
    chimes.delete(key);
    timers.value = {
      ...timers.value,
      [key]: { endsAt: Date.now() + clamped * 60_000, minutes: clamped },
    };
    lastMinutes.value = clamped;
    if (import.meta.client) {
      try {
        window.localStorage.setItem(LAST_MINUTES_KEY, String(clamped));
      } catch {
        // sugestão indisponível; o timer segue funcionando
      }
    }
    persist();
    ensureTicker();
  }

  function clear(key: string) {
    const { [key]: _, ...rest } = timers.value;
    timers.value = rest;
    chimes.delete(key);
    persist();
  }

  /** Marca que alguém viu o alerta; não altera qualquer fato produtivo. */
  function seen(key: string) {
    const t = timers.value[key];
    if (!t || t.endsAt > Date.now()) return;
    timers.value = { ...timers.value, [key]: { ...t, seenAt: Date.now() } };
    chimes.delete(key);
    persist();
  }

  /** "+N min": estende o que corre e rearma o que já tocou/foi visto. */
  function extend(key: string, minutes: number) {
    const t = timers.value[key];
    const extra = Math.max(1, Math.round(minutes)) * 60_000;
    if (!t) return;
    chimes.delete(key);
    const next: OvenTimer = {
      ...t,
      endsAt: Math.max(t.endsAt, Date.now()) + extra,
      seenAt: undefined,
    };
    timers.value = { ...timers.value, [key]: next };
    persist();
    ensureTicker();
  }

  function get(key: string): OvenTimer | null {
    return timers.value[key] ?? null;
  }

  function isRinging(key: string): boolean {
    const t = timers.value[key];
    return !!t && t.seenAt == null && t.endsAt <= nowMs.value;
  }

  function isSeen(key: string): boolean {
    const t = timers.value[key];
    return !!t && t.seenAt != null;
  }

  function remainingLabel(key: string): string {
    const t = timers.value[key];
    if (!t) return "";
    return countdownLabel((t.endsAt - nowMs.value) / 1000);
  }

  return {
    arm,
    clear,
    seen,
    extend,
    get,
    isSeen,
    isRinging,
    remainingLabel,
    lastMinutes,
  };
}
