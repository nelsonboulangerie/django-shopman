// Timers da bancada — UM mecanismo para o chão de produção inteiro: o timer do
// forno (armado por fornada na Expedição, que ainda DECLARA enfornou/retirou ao
// servidor via useOvenFacts) e os timers avulsos (fermentação, descanso, o que o
// padeiro quiser lembrar), criados do cabeçalho em qualquer tela. Decisão do
// Pablo (2026-09-16): o timer ajuda o operador a lembrar; não tenta descrever
// nem controlar o processo. Sem processo, sem etapa, sem obrigação — nome e SKU
// são opcionais; nenhum timer bloqueia Continuar, QC ou qualquer fluxo.
//
// Local ao aparelho: quem armou, ouve. Sobrevive a reload e deploy pelo
// localStorage. O relógio de idade do lote (started_at vs max_started_minutes)
// segue como guardrail de esquecimento via alertas (sino), não por aqui.
//
// Som: "dim-dom" quente em triangle wave, duas frases curtas, volume moderado
// — fácil de ouvir, fácil de conviver. Repete a cada 45s enquanto ninguém
// marca ``Visto``. O alerta não conclui o forno, o QC nem a produção.
import { countdownLabel } from "~/presentation/production";

export type FloorTimerKind = "oven" | "free";

export interface FloorTimer {
  endsAt: number;
  minutes: number;
  /** ``Visto`` silencia o alerta, mas preserva o timer até alguém encerrá-lo. */
  seenAt?: number;
  /** Forno (chave = pk da fornada) ou avulso (chave gerada aqui). */
  kind?: FloorTimerKind;
  /** Nome opcional — o avulso sem nome nasce como "Timer N". */
  label?: string;
  /** SKU opcional: associação exploratória, nunca obrigação. */
  sku?: string;
  createdAt?: number;
}

export interface FloorTimerMeta {
  kind?: FloorTimerKind;
  label?: string;
  sku?: string;
}

export type FloorTimerMode = "running" | "ringing" | "seen";

export interface FloorTimerEntry extends FloorTimer {
  key: string;
  mode: FloorTimerMode;
  /** O que a tela mostra como nome: label, ou "Forno"/"Timer" sem nome. */
  title: string;
}

const STORAGE_KEY = "producao.timers";
// Chaves anteriores (timer só do forno; e antes disso, Fournil). Lidas como
// fallback: um turno em andamento não perde os timers por causa de um deploy.
const LEGACY_STORAGE_KEYS = ["producao.oven-timers", "fournil.oven-timers"];
const LAST_MINUTES_KEY = "producao.timer-last-minutes";
const RECHIME_MS = 45_000;
const FREE_KEY_PREFIX = "free:";

const timers = ref<Record<string, FloorTimer>>({});
const nowMs = ref(0);
const chimes = new Map<string, { lastAt: number }>();
const lastMinutes = ref<number | null>(null);
let ticker: ReturnType<typeof setInterval> | null = null;
let audio: AudioContext | null = null;
let loaded = false;

export function restoreFloorTimers(
  parsed: Record<string, FloorTimer>,
  _now: number,
): Record<string, FloorTimer> {
  return Object.fromEntries(
    Object.entries(parsed).filter(
      ([, timer]) =>
        timer &&
        typeof timer.endsAt === "number" &&
        typeof timer.minutes === "number",
    ),
  );
}

/** "Timer 1", "Timer 2"… — o próximo número livre entre os avulsos anônimos. */
export function nextFreeTimerTitle(
  existing: Record<string, FloorTimer>,
): string {
  const taken = new Set(
    Object.values(existing)
      .map((timer) => timer.label ?? "")
      .filter((label) => /^Timer \d+$/.test(label)),
  );
  let n = 1;
  while (taken.has(`Timer ${n}`)) n += 1;
  return `Timer ${n}`;
}

export function floorTimerMode(t: FloorTimer, now: number): FloorTimerMode {
  if (t.seenAt != null) return "seen";
  return t.endsAt <= now ? "ringing" : "running";
}

function load() {
  if (loaded || !import.meta.client) return;
  loaded = true;
  nowMs.value = Date.now();
  try {
    const raw =
      window.localStorage.getItem(STORAGE_KEY) ??
      LEGACY_STORAGE_KEYS.map((key) => window.localStorage.getItem(key)).find(
        (value) => value != null,
      ) ??
      null;
    const parsed = raw ? (JSON.parse(raw) as Record<string, FloorTimer>) : {};
    timers.value = restoreFloorTimers(parsed, Date.now());
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

function rememberMinutes(clamped: number) {
  lastMinutes.value = clamped;
  if (!import.meta.client) return;
  try {
    window.localStorage.setItem(LAST_MINUTES_KEY, String(clamped));
  } catch {
    // sugestão indisponível; o timer segue funcionando
  }
}

export function useFloorTimers() {
  load();

  function arm(key: string, minutes: number, meta: FloorTimerMeta = {}) {
    const clamped = Math.max(1, Math.round(minutes));
    unlockAudio();
    chimes.delete(key);
    const previous = timers.value[key];
    timers.value = {
      ...timers.value,
      [key]: {
        endsAt: Date.now() + clamped * 60_000,
        minutes: clamped,
        kind: meta.kind ?? previous?.kind ?? "oven",
        label: meta.label ?? previous?.label,
        sku: meta.sku ?? previous?.sku,
        createdAt: previous?.createdAt ?? Date.now(),
      },
    };
    rememberMinutes(clamped);
    persist();
    ensureTicker();
  }

  /** Timer avulso: nasce com chave própria e, sem nome, como "Timer N". */
  function create(minutes: number, meta: FloorTimerMeta = {}): string {
    const key = `${FREE_KEY_PREFIX}${Date.now().toString(36)}-${Math.random()
      .toString(36)
      .slice(2, 6)}`;
    const label = (meta.label ?? "").trim() || nextFreeTimerTitle(timers.value);
    arm(key, minutes, { ...meta, kind: "free", label });
    return key;
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
    const next: FloorTimer = {
      ...t,
      endsAt: Math.max(t.endsAt, Date.now()) + extra,
      seenAt: undefined,
    };
    timers.value = { ...timers.value, [key]: next };
    persist();
    ensureTicker();
  }

  function get(key: string): FloorTimer | null {
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

  // A lista do painel: quem toca primeiro, depois quem vence antes; o visto
  // vai para o fim. Reativa ao relógio (nowMs) para o modo virar sozinho.
  const entries = computed<FloorTimerEntry[]>(() => {
    const now = nowMs.value;
    const rank: Record<FloorTimerMode, number> = {
      ringing: 0,
      running: 1,
      seen: 2,
    };
    return Object.entries(timers.value)
      .map(([key, t]) => ({
        ...t,
        key,
        mode: floorTimerMode(t, now),
        title: t.label || (t.kind === "free" ? "Timer" : "Forno"),
      }))
      .sort((a, b) => rank[a.mode] - rank[b.mode] || a.endsAt - b.endsAt);
  });
  const activeCount = computed(() => entries.value.length);
  const ringingCount = computed(
    () => entries.value.filter((entry) => entry.mode === "ringing").length,
  );

  return {
    arm,
    create,
    clear,
    seen,
    extend,
    get,
    isSeen,
    isRinging,
    remainingLabel,
    lastMinutes,
    entries,
    activeCount,
    ringingCount,
  };
}
