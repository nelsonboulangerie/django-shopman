/** Rota de acompanhamento a partir de um `ref`. */
export function orderTrackingRoute (ref: string): string {
  return `/pedido/${encodeURIComponent(ref)}`
}
