import { proxyEventStream } from '../../utils/eventStream'

// Rota SSE same-origin da loja viva (WP-L04): /sse/loja → streaming do aviso
// público da vitrine no Django. O aviso não carrega dado (nem SKU, nem motivo):
// só diz que vale reler a página. Ver `shopman/storefront/api/shelf_events.py`.
export default defineEventHandler(event => proxyEventStream(event, '/api/v1/storefront/shelf/events/'))
