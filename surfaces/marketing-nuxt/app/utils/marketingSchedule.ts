export type ScheduleFold = "earlier" | "later" | "";
export type ScheduleProblem =
  | ""
  | "invalid"
  | "invalid_timezone"
  | "nonexistent"
  | "ambiguous"
  | "past"
  | "after_expiry"
  | "quiet_hours";

export interface ZonedScheduleCandidate {
  epochMs: number;
  instant: string;
  offset: string;
}

export interface ScheduleResolution {
  ok: boolean;
  problem: ScheduleProblem;
  detail: string;
  candidate: ZonedScheduleCandidate | null;
  candidates: ZonedScheduleCandidate[];
  nextAllowedLocal: string;
}

interface WallParts {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
}

const LOCAL_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/;
const MIN_OFFSET = -14 * 60;
const MAX_OFFSET = 14 * 60;
const OFFSET_STEP = 15;

function wallParts(value: string): WallParts | null {
  const match = LOCAL_PATTERN.exec(value);
  if (!match) return null;
  const [, yearText, monthText, dayText, hourText, minuteText] = match;
  const parts = {
    year: Number(yearText),
    month: Number(monthText),
    day: Number(dayText),
    hour: Number(hourText),
    minute: Number(minuteText),
  };
  const check = new Date(Date.UTC(
    parts.year,
    parts.month - 1,
    parts.day,
    parts.hour,
    parts.minute,
  ));
  if (
    check.getUTCFullYear() !== parts.year
    || check.getUTCMonth() + 1 !== parts.month
    || check.getUTCDate() !== parts.day
    || check.getUTCHours() !== parts.hour
    || check.getUTCMinutes() !== parts.minute
  ) return null;
  return parts;
}

function formatter(timeZone: string) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
}

function partsAt(epochMs: number, timeZone: string): WallParts {
  const values = Object.fromEntries(
    formatter(timeZone)
      .formatToParts(new Date(epochMs))
      .filter(part => part.type !== "literal")
      .map(part => [part.type, Number(part.value)]),
  );
  return {
    year: values.year!,
    month: values.month!,
    day: values.day!,
    hour: values.hour!,
    minute: values.minute!,
  };
}

function sameWall(left: WallParts, right: WallParts): boolean {
  return left.year === right.year
    && left.month === right.month
    && left.day === right.day
    && left.hour === right.hour
    && left.minute === right.minute;
}

function offsetText(minutes: number): string {
  const sign = minutes >= 0 ? "+" : "-";
  const absolute = Math.abs(minutes);
  return `${sign}${String(Math.floor(absolute / 60)).padStart(2, "0")}:${String(absolute % 60).padStart(2, "0")}`;
}

function localText(parts: WallParts): string {
  return `${String(parts.year).padStart(4, "0")}-${String(parts.month).padStart(2, "0")}-${String(parts.day).padStart(2, "0")}T${String(parts.hour).padStart(2, "0")}:${String(parts.minute).padStart(2, "0")}`;
}

export function zonedScheduleCandidates(
  localValue: string,
  timeZone: string,
): ZonedScheduleCandidate[] {
  const local = wallParts(localValue);
  if (!local) return [];
  // Construct every legal civil offset and retain only instants whose IANA
  // round-trip returns the exact wall time. A DST gap yields zero; a fold two.
  const localEpoch = Date.UTC(
    local.year,
    local.month - 1,
    local.day,
    local.hour,
    local.minute,
  );
  try {
    formatter(timeZone).format(new Date(localEpoch));
  } catch {
    return [];
  }
  const found = new Map<number, ZonedScheduleCandidate>();
  for (let offset = MIN_OFFSET; offset <= MAX_OFFSET; offset += OFFSET_STEP) {
    const epochMs = localEpoch - offset * 60_000;
    if (!sameWall(partsAt(epochMs, timeZone), local)) continue;
    const offsetValue = offsetText(offset);
    found.set(epochMs, {
      epochMs,
      instant: `${localValue}:00${offsetValue}`,
      offset: offsetValue,
    });
  }
  return [...found.values()].sort((left, right) => left.epochMs - right.epochMs);
}

export function localInputFromInstant(instant: string, timeZone: string): string {
  const epochMs = Date.parse(instant);
  if (!Number.isFinite(epochMs)) return "";
  try {
    return localText(partsAt(epochMs, timeZone));
  } catch {
    return "";
  }
}

function quietHours(candidate: ZonedScheduleCandidate, timeZone: string): boolean {
  const { hour } = partsAt(candidate.epochMs, timeZone);
  return hour >= 20 || hour < 8;
}

function tomorrowAtEight(epochMs: number, timeZone: string): string {
  const local = partsAt(epochMs, timeZone);
  const localDay = new Date(Date.UTC(local.year, local.month - 1, local.day));
  if (local.hour >= 20) localDay.setUTCDate(localDay.getUTCDate() + 1);
  return `${localDay.toISOString().slice(0, 10)}T08:00`;
}

export function resolveScheduleInput(options: {
  localValue: string;
  timeZone: string;
  fold?: ScheduleFold;
  nowMs?: number;
  expiresAt?: string;
  directMessage?: boolean;
}): ScheduleResolution {
  const { localValue, timeZone } = options;
  if (!wallParts(localValue)) {
    return problem("invalid", "Escolha uma data e hora completas.");
  }
  try {
    formatter(timeZone).format(new Date());
  } catch {
    return problem("invalid_timezone", "O timezone da loja é inválido. Recarregue a tela.");
  }
  const candidates = zonedScheduleCandidates(localValue, timeZone);
  if (candidates.length === 0) {
    return problem(
      "nonexistent",
      "Esse horário não existe por causa da mudança do relógio. Escolha outro horário.",
    );
  }
  if (candidates.length > 1 && !options.fold) {
    return {
      ...problem(
        "ambiguous",
        "Esse horário acontece duas vezes. Escolha a primeira ou a segunda ocorrência.",
      ),
      candidates,
    };
  }
  const candidate = options.fold === "later"
    ? candidates.at(-1)!
    : candidates[0]!;
  const nowMs = options.nowMs ?? Date.now();
  if (candidate.epochMs <= nowMs) {
    return {
      ...problem("past", "Escolha um horário futuro."),
      candidate,
      candidates,
    };
  }
  const expiryMs = options.expiresAt ? Date.parse(options.expiresAt) : Number.NaN;
  if (Number.isFinite(expiryMs) && candidate.epochMs >= expiryMs) {
    return {
      ...problem(
        "after_expiry",
        "O anúncio expiraria antes desse horário. Antecipe o agendamento.",
      ),
      candidate,
      candidates,
    };
  }
  if (options.directMessage && quietHours(candidate, timeZone)) {
    return {
      ...problem(
        "quiet_hours",
        "O WhatsApp fica em silêncio das 20:00 às 08:00.",
      ),
      candidate,
      candidates,
      nextAllowedLocal: tomorrowAtEight(candidate.epochMs, timeZone),
    };
  }
  return {
    ok: true,
    problem: "",
    detail: "",
    candidate,
    candidates,
    nextAllowedLocal: "",
  };
}

function problem(code: ScheduleProblem, detail: string): ScheduleResolution {
  return {
    ok: false,
    problem: code,
    detail,
    candidate: null,
    candidates: [],
    nextAllowedLocal: "",
  };
}

export function suggestedScheduleLocal(options: {
  timeZone: string;
  suggestedAt?: string;
  nowMs?: number;
  expiresAt?: string;
}): string {
  const nowMs = options.nowMs ?? Date.now();
  const expiryMs = options.expiresAt ? Date.parse(options.expiresAt) : Number.NaN;
  const suggestedMs = options.suggestedAt ? Date.parse(options.suggestedAt) : Number.NaN;
  if (
    Number.isFinite(suggestedMs)
    && suggestedMs > nowMs
    && (!Number.isFinite(expiryMs) || suggestedMs < expiryMs)
  ) return localInputFromInstant(options.suggestedAt!, options.timeZone);

  const localNow = partsAt(nowMs, options.timeZone);
  if (localNow.hour >= 20 || localNow.hour < 8) {
    return tomorrowAtEight(nowMs, options.timeZone);
  }
  const rounded = Math.ceil((nowMs + 60_000) / (15 * 60_000)) * 15 * 60_000;
  return localInputFromInstant(new Date(rounded).toISOString(), options.timeZone);
}

export function scheduleSummary(instant: string, timeZone: string): string {
  const epochMs = Date.parse(instant);
  if (!Number.isFinite(epochMs)) return "";
  try {
    return new Intl.DateTimeFormat("pt-BR", {
      timeZone,
      dateStyle: "full",
      timeStyle: "short",
    }).format(new Date(epochMs));
  } catch {
    return "";
  }
}

export function expirySummary(expiresAt: string, timeZone: string, nowMs = Date.now()): string {
  const expiresMs = Date.parse(expiresAt);
  if (!Number.isFinite(expiresMs)) return "";
  const remaining = expiresMs - nowMs;
  if (remaining <= 0) return "Expirou";
  const minutes = Math.ceil(remaining / 60_000);
  const relative = minutes < 60
    ? `${minutes} min`
    : `${Math.floor(minutes / 60)} h${minutes % 60 ? ` ${minutes % 60} min` : ""}`;
  const absolute = new Intl.DateTimeFormat("pt-BR", {
    timeZone,
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(expiresMs));
  return `Expira em ${relative} · ${absolute} (${timeZone})`;
}

export function isQuietHoursNow(timeZone: string, nowMs = Date.now()): boolean {
  try {
    const hour = partsAt(nowMs, timeZone).hour;
    return hour >= 20 || hour < 8;
  } catch {
    return true;
  }
}
