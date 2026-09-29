type AddressEventName =
  | 'address.location.requested'
  | 'address.location.resolved'
  | 'address.location.denied'
  | 'address.map.ready'
  | 'address.map.fallback'
  | 'address.map.confirmed'
  | 'address.zone.resolved'
  | 'address.location_check.requested'
  | 'address.location_check.resolved'
  | 'address.location_check.failed'
  | 'address.location_mismatch.shown'
  | 'address.location_mismatch.action'

/**
 * Fire-and-forget aggregate telemetry. Callers pass only closed enums: the
 * endpoint deliberately has no fields for query, address, CEP, coordinates,
 * place id, customer/session/order identifiers or free text.
 */
export function useStorefrontTelemetry () {
  const apiPath = useShopmanApiPath()

  function addressEvent (event: AddressEventName, properties: Record<string, string | boolean>) {
    if (!import.meta.client) return
    void $fetch(apiPath('/api/v1/storefront/address-event/'), {
      method: 'POST',
      body: { event, properties }
    }).catch(() => undefined)
  }

  return { addressEvent }
}
