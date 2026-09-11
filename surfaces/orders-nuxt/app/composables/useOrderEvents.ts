import { useBackstageEvents } from "./useBackstageEvents";

export function useOrderEvents(orderRef: string, onPush: () => void, opts?: { pollMs?: number }) {
  return useBackstageEvents("orders", onPush, { ...opts, orderRef });
}
