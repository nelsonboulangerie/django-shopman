import { proxyEventStream } from '../../utils/eventStream'

// Rota SSE same-origin da loja viva (WP-L04): /sse/loja → streaming do aviso
// público da vitrine no Django. O aviso leva só o SKU cujo estado público mudou (o
// que a vitrine já mostra a qualquer um), ou nada quando vale para a vitrine inteira
// (#2784). Ver `shopman/storefront/api/shelf_events.py`.
export default defineEventHandler(event => proxyEventStream(event, '/api/v1/storefront/shelf/events/'))
