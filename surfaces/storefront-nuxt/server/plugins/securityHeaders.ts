import { getRequestHeader, getRequestURL } from 'h3'
import { defineNitroPlugin } from 'nitropack/runtime'
import { storefrontResponseHeaders } from '../utils/storefrontSecurity'

// A TELA DE ERRO E TELA DA LOJA, e sai com a politica da loja.
//
// O `middleware/storefront-security.ts` carimba os cabecalhos na entrada, mas o
// handler de erro do Nitro REESCREVE o `content-security-policy` com o dele
// (`script-src 'none'; frame-ancestors 'none'`). Enquanto a loja respondia 200
// para tudo ninguem via; desde que ela responde 503 quando o backend cai
// (`useContentGuard`), a pagina de erro passou a sair com politica de outra casa
// -- sem `worker-src`, o service worker do PWA nao sobe, e o gate estrutural
// acusou na primeira tentativa.
//
// `render:response` e o ultimo lugar onde a politica da casa ainda vence: ele
// carrega a resposta HTML ja montada (a da pagina e a do erro), e os cabecalhos
// dela sao os que vao para a rede.
export default defineNitroPlugin((nitro) => {
  nitro.hooks.hook('render:response', (response, { event }) => {
    const forwarded = getRequestHeader(event, 'x-forwarded-proto')?.split(',', 1)[0]?.trim().toLowerCase()
    const secure = forwarded ? forwarded === 'https' : getRequestURL(event).protocol === 'https:'
    response.headers ||= {}
    Object.assign(response.headers, storefrontResponseHeaders(secure, getRequestURL(event).pathname))
  })
})
