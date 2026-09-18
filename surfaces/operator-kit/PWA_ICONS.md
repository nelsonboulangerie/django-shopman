# Ícones PWA das superfícies

Os ícones instaláveis usam fundo de cor, símbolo centralizado e desenho creme
`#FCF7EE`. O gerador canônico é `scripts/generate-pwa-assets.mjs` (rode
`npm run pwa:assets` no app; o Storefront tem o próprio, em
`storefront-nuxt/scripts/finalize-pwa-assets.mjs`, com a mesma regra de forma).

## A identidade de um app mora num arquivo só

`operator-kit/app-identity.json` — rótulo, descrição, símbolo, ícone de recurso e
**cor**. Quem lê: o gerador de ícones (`--app=<chave>`), o manifesto
(`pwa.config.ts` → `resolveOperatorPwa`), a barra de título, o rail, o gate de login,
o convite de instalação e o gate `tools/pwa-gate/check.mjs`. **Esta tabela é o
espelho legível do arquivo, não a fonte** — mude o JSON e rode `npm run pwa:assets`.

Antes, os mesmos três dados estavam escritos em seis lugares, e derivaram: a Central
tinha ícone ardósia (`#34373B`) e barra de título vinho (`#7C3A40`); cinco apps tinham
barra branca; o Gestor se chamava "Gestor" na janela e "Gestor de Pedidos" no
launcher; a Cozinha era "Cozinha" no rail e "KDS" no título.

| Superfície | Chave | Símbolo | Cor (ícone **e** barra de título) |
| --- | --- | --- | --- |
| Storefront | — (fora do kit) | `lucide:store` | `#6D1F32` |
| Central | `hub` | `lucide:layout-grid` | `#34373B` |
| PDV | `pos` | `lucide:shopping-basket` | `#A95032` |
| Cozinha | `kds` | `lucide:chef-hat` | `#2E7168` |
| Gestor de pedidos | `orders` | `lucide:square-kanban` | `#8B2F4D` |
| Produção | `production` | `tabler:baguette` | `#B9781B` |
| Marketing | `marketing` | `lucide:megaphone` | `#7D4B88` |
| Compras | `purchase` | `lucide:package` | `#386F9A` |
| B.I. | `bi` | `lucide:chart-no-axes-combined` | `#414F91` |

### A barra de título é a cor do ícone

O `theme_color` do manifesto é o que o Chrome pinta na barra de título do app
instalado (no Mac, no Windows e no ChromeOS) e na barra do navegador no Android. Ele
é a cor do ÍCONE, e não uma cor de tela: é por ela que o operador sabe em qual app
está antes de ler qualquer palavra, e oito barras sem relação com o ícone eram oito
janelas iguais. O `background_color` é outra coisa — a tela de abertura — e segue o
`--background` do `operator-theme.css`: `#FCF6F1` no claro, `#221610` na Cozinha
(dark-first). Nenhum dos dois se escreve no `nuxt.config`; os dois saem da identidade.

### O nome do app também

O app instalado se chama `"<casa> · <rótulo>"` (a casa é `Shop.short_name`, lida do
Django em runtime). O rótulo da tabela acima é o MESMO na barra de título, no
`short_name`, no rail, no gate de login, no tile da Central
(`shopman/backstage/projections/hub.py`) e no menu do Admin. Quem impede os dois lados
de divergirem é `shopman/backstage/tests/test_hub_projection_identity.py` — o Django
não lê o JSON em runtime, porque o deploy do backend não empacota `surfaces/`.

Exceção com razão escrita: no menu do Admin o item que abre a Produção se chama
"Produção ao vivo", para não colidir com o grupo "Produção" (fichas, ordens, insumos)
logo abaixo. "ao vivo" é qualificador, não um segundo nome.

Fontes vetoriais:

- [Lucide](https://lucide.dev/), licença ISC;
- [Tabler Icons](https://tabler.io/icons), licença MIT.

Os PNGs versionados em cada `public/pwa/` são derivados dessas fontes.

## Forma: quem arredonda o canto

| Arquivo | Forma | Por quê |
| --- | --- | --- |
| `pwa-64x64`, `pwa-192x192`, `pwa-512x512` (`purpose: any`) | retângulo arredondado, raio 22,5% do lado, **transparente fora** | Windows e Linux desktop usam o `any` como está, sem máscara (o macOS também, mas só se faltar `maskable`; ver abaixo). Quadrado cheio aparecia de quinas vivas no menu Iniciar/barra de tarefas (visto no PDV no Windows, 17/09/2026). |
| `maskable-512x512` (`purpose: maskable`) | quadrado **cheio**, símbolo em 48% do lado | O launcher Android recorta na forma dele, e o Chrome no macOS recorta na grade do Dock; a arte fica dentro da zona segura (círculo de 80%). |
| `apple-touch-icon-180x180` | quadrado **cheio e opaco** | O iOS arredonda sozinho e pinta de preto o que for transparente. Nunca arredondar este. |

### macOS: o Dock usa o `maskable`, não o `any`

O Chrome no macOS gera o `app.icns` do app instalado a partir do ícone `maskable`,
recortado na grade dos ícones do macOS; só usa o `any` quando o manifesto não traz
`maskable`, e aí copia o PNG como está. Medido nos `app.icns` de
`~/Applications/Chrome Apps.localized/` (17/09/2026, quadro de 512 px):

| App instalado | Manifesto servido ao Mac | Forma opaca no `app.icns` | Sombra |
| --- | --- | --- | --- |
| Shopman PDV | `any` + `maskable` | 50…462 = **412/512 (80,5%)** — a grade do macOS (824/1024) | 40…477 |
| Nelson Boulangerie (antes, `?v=5`) | só `any` (o `maskable` era omitido por `User-Agent`) | 0…512 = **512/512 (100%)** | nenhuma |

Os PNGs da loja e do PDV têm a mesma forma, pixel a pixel; o que mudava era o
manifesto. A exceção por `User-Agent` vinha da época do selo transparente da loja, e
com a arte atual fazia o app aparecer ~24% maior (512/412) que os vizinhos.
**Todo manifesto publica `maskable`, para todo navegador.** O teste
`storefront-nuxt/tests/pwaAssets.test.ts` compara a forma dos PNGs da loja com os do
PDV, e `pwaManifest*.test.ts` exigem o `maskable` também para o Mac.

Como o PNG `any` tem cantos transparentes, quem o exibe dentro de um quadrado
(rail, tile da Central) só pinta o fundo quando mostra o Lucide de fallback — senão
o fundo vira uma moldura clara nos quatro cantos.

## Favicon da aba

O mesmo `pwa:assets` grava, na raiz do `public/` (um nível acima de `--out`), a
identidade do app para a aba do navegador — antes os apps serviam o logo verde do
template do Nuxt, e o Compras nem tinha favicon:

| Arquivo | Conteúdo | Arte |
| --- | --- | --- |
| `favicon.ico` | três quadros PNG: 16, 32 e 48 px | retângulo arredondado (22,5%), canto transparente; símbolo em 78%/70%/66% do lado com traço 1,5×/1,25×/1,125× |
| `favicon.svg` | vetor, `rx` proporcional | a arte de 16 px (a aba é sempre 16 px CSS) |

A proporção do ícone PWA (símbolo em 56%, traço 2 de 24) em 16 px vira linha de
0,75 px, um borrão; a tabela acima saiu de renderizar as oito famílias lado a lado.
Em 16 px o Gestor (`square-kanban`) e o B.I. (as barras do gráfico) viram mancha no
miolo, mas o contorno e a cor seguem reconhecíveis.

Os links saem da capability PWA (`OPERATOR_HEAD_LINKS` em `pwa.config.ts`), iguais nos
oito apps: `favicon.svg?v=1` e `favicon.ico?v=1` com `sizes="48x48"` (com `sizes="any"`
o Chrome prefere o `.ico` ao SVG). Trocou o desenho do favicon? Suba `FAVICON_VERSION`.

Trocou a forma ou o desenho? Suba o `?v=` em todos os lugares da tabela abaixo. O
SO só relê o ícone de um app **já instalado** quando o navegador revisita o
manifesto (Chrome/Edge: em até um dia de uso, às vezes pedindo confirmação de
atualização); no Windows o atalho do menu Iniciar pode seguir com o ícone antigo
até o app ser atualizado ou reinstalado.

## Onde a família aparece

A identidade de cada app é UMA: o PNG acima. Os lugares que a mostram apontam
para o arquivo publicado, nunca copiam o desenho.

Nenhum desses lugares escreve o caminho: todos recebem `identity.iconSrc` pelo
`runtimeConfig`, montado por `operatorAppIconSrc()` a partir do `assetVersion` da
identidade. Era o caminho `?v=` que envelhecia num app só.

| Lugar | Fonte | Fallback |
| --- | --- | --- |
| Manifesto / launcher do SO | `operatorAppIcons()` (`appIdentity.ts`); Storefront: `?v=6` em `server/utils/pwaManifest.ts` e `nuxt.config.ts` | — |
| Central de Apps (tile) | `<origem do tile>` + `operatorShortcutIconSrc()` (`tileIconUrl`, hub-nuxt) | Lucide de `fallbackIcon`, vindo do Django (`backstage/projections/hub.py`) |
| Rail de cada app (quadrado de identidade) | `identity.iconSrc` no `<OperatorRail>` (sem prop) | Lucide de `identity.fallbackIcon` |
| Gate de login | `identity.iconSrc` no `<OperatorLogin>` (sem prop) | Lucide de `identity.fallbackIcon` |
| Convite de instalação | título `"Instale {artigo} {rótulo}"` + a frase `install` do app | — |

O fallback Lucide existe para a imagem que não carrega (app fora do ar, build
sem a família, CSP `img-src 'self'` no hub) — cai por `@error`, por tile/app, sem
apagar os demais. Por isso os nomes Lucide de fallback seguem a tabela acima.
Única exceção: **Produção** usa `tabler:baguette` no PNG e os apps só instalam
`@iconify-json/lucide`; o fallback fica em `lucide:croissant`.

Os PNGs de `/pwa/` saem pelo handler estático do Nitro, sem `Cross-Origin-Resource-Policy`;
é isso que permite à Central embutir o ícone de outra origem (`pdv.`, `kds.`…).
