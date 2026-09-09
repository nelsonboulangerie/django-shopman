export const MARKETING_DRAFT_SCHEMA = 1;
export const MARKETING_DRAFT_TTL_MS = 7 * 24 * 60 * 60 * 1_000;

export type MarketingDraftPayload = Record<string, unknown>;

export interface MarketingDraftIdentity {
  owner: string;
  resource: string;
}

export interface StoredMarketingDraft extends MarketingDraftIdentity {
  schema: number;
  baseVersion: string;
  base: MarketingDraftPayload;
  payload: MarketingDraftPayload;
  savedAt: number;
  expiresAt: number;
}

export interface DraftStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export interface MarketingDraftConflict {
  field: string;
  base: unknown;
  current: unknown;
  draft: unknown;
}

export interface MarketingDraftMerge {
  conflicts: MarketingDraftConflict[];
  localChanged: string[];
  serverChanged: string[];
  localWins: MarketingDraftPayload;
  serverWins: MarketingDraftPayload;
}

const PREFIX = "shopman.marketing.draft.v1";

function clone<T>(value: T): T {
  if (value === undefined) return value;
  return JSON.parse(JSON.stringify(value)) as T;
}

function normalized(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalized);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, nested]) => [key, normalized(nested)]),
    );
  }
  return value;
}

export function marketingDraftEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(normalized(left)) === JSON.stringify(normalized(right));
}

export function marketingDraftKey(identity: MarketingDraftIdentity): string {
  return `${PREFIX}:${encodeURIComponent(identity.owner)}:${encodeURIComponent(identity.resource)}`;
}

function validPayload(value: unknown): value is MarketingDraftPayload {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

export function readMarketingDraft(
  storage: DraftStorage,
  identity: MarketingDraftIdentity,
  now = Date.now(),
): StoredMarketingDraft | null {
  const key = marketingDraftKey(identity);
  try {
    const parsed = JSON.parse(storage.getItem(key) ?? "null") as Partial<StoredMarketingDraft> | null;
    if (
      !parsed
      || parsed.schema !== MARKETING_DRAFT_SCHEMA
      || parsed.owner !== identity.owner
      || parsed.resource !== identity.resource
      || typeof parsed.baseVersion !== "string"
      || typeof parsed.savedAt !== "number"
      || typeof parsed.expiresAt !== "number"
      || parsed.expiresAt <= now
      || !validPayload(parsed.base)
      || !validPayload(parsed.payload)
    ) {
      storage.removeItem(key);
      return null;
    }
    return parsed as StoredMarketingDraft;
  } catch {
    // Storage can be denied by browser policy or contain a truncated write. Either
    // way the form remains usable; an unreadable draft never replaces server truth.
    try { storage.removeItem(key); } catch { /* storage unavailable */ }
    return null;
  }
}

export function writeMarketingDraft(
  storage: DraftStorage,
  identity: MarketingDraftIdentity,
  baseVersion: string | number,
  base: MarketingDraftPayload,
  payload: MarketingDraftPayload,
  now = Date.now(),
): StoredMarketingDraft | null {
  const record: StoredMarketingDraft = {
    schema: MARKETING_DRAFT_SCHEMA,
    ...identity,
    baseVersion: String(baseVersion),
    base: clone(base),
    payload: clone(payload),
    savedAt: now,
    expiresAt: now + MARKETING_DRAFT_TTL_MS,
  };
  try {
    storage.setItem(marketingDraftKey(identity), JSON.stringify(record));
    return record;
  } catch {
    return null;
  }
}

export function clearMarketingDraft(
  storage: DraftStorage,
  identity: MarketingDraftIdentity,
): void {
  try { storage.removeItem(marketingDraftKey(identity)); } catch { /* storage unavailable */ }
}

function own(record: MarketingDraftPayload, field: string): boolean {
  return Object.prototype.hasOwnProperty.call(record, field);
}

function copyField(
  target: MarketingDraftPayload,
  source: MarketingDraftPayload,
  field: string,
): void {
  if (own(source, field)) target[field] = clone(source[field]);
  else Reflect.deleteProperty(target, field);
}

/** Three-way merge: base saved at edit start, current server state and local draft. */
export function mergeMarketingDraft(
  base: MarketingDraftPayload,
  current: MarketingDraftPayload,
  draft: MarketingDraftPayload,
): MarketingDraftMerge {
  const fields = [...new Set([...Object.keys(base), ...Object.keys(current), ...Object.keys(draft)])]
    .sort();
  const localChanged = fields.filter(field => !marketingDraftEqual(base[field], draft[field])
    || own(base, field) !== own(draft, field));
  const serverChanged = fields.filter(field => !marketingDraftEqual(base[field], current[field])
    || own(base, field) !== own(current, field));
  const serverSet = new Set(serverChanged);
  const conflicts = localChanged
    .filter(field => serverSet.has(field) && (
      !marketingDraftEqual(current[field], draft[field])
      || own(current, field) !== own(draft, field)
    ))
    .map(field => ({
      field,
      base: clone(base[field]),
      current: clone(current[field]),
      draft: clone(draft[field]),
    }));
  const conflictSet = new Set(conflicts.map(conflict => conflict.field));
  const localWins = clone(current);
  const serverWins = clone(current);
  for (const field of localChanged) {
    copyField(localWins, draft, field);
    if (!conflictSet.has(field)) copyField(serverWins, draft, field);
  }
  return { conflicts, localChanged, serverChanged, localWins, serverWins };
}

export function browserDraftStorage(): DraftStorage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}
