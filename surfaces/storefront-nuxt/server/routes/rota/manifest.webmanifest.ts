import { setResponseHeaders } from 'h3'
import { buildCourierManifest } from '../../utils/pwaManifest'

// O manifesto do app das rotas (DEV-2026-030, M2). Linkado só em `/rota/*`
// (`useCourierPageHead`); a loja segue com o `/manifest.webmanifest` dela.
export default defineEventHandler((event) => {
  setResponseHeaders(event, {
    'cache-control': 'no-cache',
    'content-type': 'application/manifest+json; charset=utf-8',
    'x-robots-tag': 'noindex'
  })
  return buildCourierManifest()
})
