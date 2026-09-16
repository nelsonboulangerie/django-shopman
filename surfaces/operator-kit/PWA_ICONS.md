# Ícones PWA das superfícies

Os ícones instaláveis usam fundo opaco, símbolo centralizado e desenho creme
`#FCF7EE`. O gerador canônico é `scripts/generate-pwa-assets.mjs`.

| Superfície | Símbolo | Fundo |
| --- | --- | --- |
| Storefront | `lucide:store` | `#6D1F32` |
| Central | `lucide:layout-grid` | `#34373B` |
| Gestor | `lucide:square-kanban` | `#8B2F4D` |
| PDV | `lucide:shopping-basket` | `#A95032` |
| Produção | `tabler:baguette` | `#B9781B` |
| KDS | `lucide:chef-hat` | `#2E7168` |
| Marketing | `lucide:megaphone` | `#7D4B88` |
| Compras | `lucide:package` | `#386F9A` |
| B.I. | `lucide:chart-no-axes-combined` | `#414F91` |

Fontes vetoriais:

- [Lucide](https://lucide.dev/), licença ISC;
- [Tabler Icons](https://tabler.io/icons), licença MIT.

Os PNGs versionados em cada `public/pwa/` são derivados dessas fontes. O
`maskable` reduz o símbolo para preservar a zona segura do launcher.

## Onde a família aparece

A identidade de cada app é UMA: o PNG acima. Os lugares que a mostram apontam
para o arquivo publicado, nunca copiam o desenho.

| Lugar | Fonte | Fallback |
| --- | --- | --- |
| Manifesto / launcher do SO | `public/pwa/*.png?v=2` (via `pwa.config`) | — |
| Central de Apps (tile) | `<origem do tile>/pwa/pwa-192x192.png?v=2` (`tileIconUrl`, hub-nuxt) | Lucide vindo do Django (`backstage/projections/hub.py`) |
| Rail de cada app (quadrado de identidade) | `app-icon-src="/pwa/pwa-64x64.png?v=2"` no `<OperatorRail>` | Lucide de `app-icon` |
| Gate de login da Central | `icon-src="/pwa/pwa-64x64.png?v=2"` no `<OperatorLogin>` | Lucide de `icon` |

O fallback Lucide existe para a imagem que não carrega (app fora do ar, build
sem a família, CSP `img-src 'self'` no hub) — cai por `@error`, por tile/app, sem
apagar os demais. Por isso os nomes Lucide de fallback seguem a tabela acima.
Única exceção: **Produção** usa `tabler:baguette` no PNG e os apps só instalam
`@iconify-json/lucide`; o fallback fica em `lucide:croissant`.

Os PNGs de `/pwa/` saem pelo handler estático do Nitro, sem `Cross-Origin-Resource-Policy`;
é isso que permite à Central embutir o ícone de outra origem (`pdv.`, `kds.`…).
