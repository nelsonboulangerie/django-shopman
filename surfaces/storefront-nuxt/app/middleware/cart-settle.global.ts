export default defineNuxtRouteMiddleware(async () => {
  if (import.meta.server) return

  const { hasPendingMutations, settleCart } = useCartState()
  if (!hasPendingMutations.value) return

  // A cart click is optimistic, but navigation must not abort the request that
  // makes it durable (and carries the first session cookie). Reuse the cart's
  // existing queue and authoritative refresh before changing pages.
  await settleCart().catch(() => null)
})
