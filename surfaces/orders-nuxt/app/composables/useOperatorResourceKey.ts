/** Read caches belong to the authenticated person; null is never another person. */
export function useOperatorResourceKey(resource: string): string {
  const { data } = useNuxtData<{ operator?: { id: number } }>("operator-session");
  return `orders:${data.value?.operator?.id ?? "unidentified"}:${resource}`;
}
