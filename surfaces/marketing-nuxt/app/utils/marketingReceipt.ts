import type { MarketingCommandReceipt } from "~/types/campaign";

const RECEIPT_PREFIX = "shopman:marketing:receipt:v1";
const RECEIPT_TTL_MS = 24 * 60 * 60 * 1_000;

type ReceiptStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

type StoredReceipt = {
  announcementId: number;
  storedAt: number;
  receipt: MarketingCommandReceipt;
};

function keyFor(announcementId: number): string {
  return `${RECEIPT_PREFIX}:announcement:${announcementId}`;
}

function browserStorage(): ReceiptStorage | null {
  try {
    return typeof sessionStorage === "undefined" ? null : sessionStorage;
  } catch {
    return null;
  }
}

/**
 * Keep the safe receipt beside its resource across a route change/refresh.
 * Session storage is deliberate: a shared workstation must not retain it after
 * the tab/session is closed, and command tokens are never accepted here.
 */
export function preserveMarketingReceipt(
  announcementId: number,
  receipt: MarketingCommandReceipt,
  options: { storage?: ReceiptStorage | null; now?: number } = {},
): boolean {
  const storage =
    options.storage === undefined ? browserStorage() : options.storage;
  if (
    !storage ||
    !Number.isSafeInteger(announcementId) ||
    announcementId <= 0 ||
    receipt.resource_ref !== `announcement:${announcementId}` ||
    !receipt.ref
  ) {
    return false;
  }
  const value: StoredReceipt = {
    announcementId,
    storedAt: options.now ?? Date.now(),
    receipt,
  };
  try {
    storage.setItem(keyFor(announcementId), JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

export function restoreMarketingReceipt(
  announcementId: number,
  options: { storage?: ReceiptStorage | null; now?: number } = {},
): MarketingCommandReceipt | null {
  const storage =
    options.storage === undefined ? browserStorage() : options.storage;
  if (
    !storage ||
    !Number.isSafeInteger(announcementId) ||
    announcementId <= 0
  ) {
    return null;
  }
  const key = keyFor(announcementId);
  try {
    const parsed = JSON.parse(
      storage.getItem(key) || "null",
    ) as Partial<StoredReceipt> | null;
    const now = options.now ?? Date.now();
    if (
      !parsed ||
      parsed.announcementId !== announcementId ||
      typeof parsed.storedAt !== "number" ||
      now - parsed.storedAt > RECEIPT_TTL_MS ||
      !parsed.receipt ||
      parsed.receipt.resource_ref !== `announcement:${announcementId}` ||
      typeof parsed.receipt.ref !== "string" ||
      !parsed.receipt.ref
    ) {
      storage.removeItem(key);
      return null;
    }
    return parsed.receipt as MarketingCommandReceipt;
  } catch {
    storage.removeItem(key);
    return null;
  }
}
