# WP-UX-8, Fase 0: prova de Nuxt UI e Reka

**Data:** 05/10/2026

**Veredito:** aprovado para adoção híbrida nas oito superfícies de operador

**Escopo desta prova:** infraestrutura compartilhada, dois componentes-piloto, inventário
completo e travas de regressão. A Storefront permanece fora do perímetro.

## Resultado

O Nuxt UI 4.11.3 passa a ser carregado uma única vez pelo `operator-kit`, em modo sem tema,
sem fontes e sem color mode próprios. Os apps continuam donos apenas da composição das telas;
a infraestrutura de componentes fica no kit. O prefixo `Nuxt` separa explicitamente os
componentes da biblioteca dos contratos Shopman.

A prova confirmou a abordagem prevista no WP:

- Nuxt UI é usado quando reduz estados e código de infraestrutura sem impor aparência;
- Reka continua disponível para interações operacionais especializadas;
- HTML semântico continua correto para controles simples;
- toda tela consome um componente Shopman, nunca `@nuxt/ui` diretamente;
- classes, fontes, cores, densidade, copy e comportamento responsivo permanecem Shopman.

`UiButton` e `UiModal` são as provas executáveis dessa arquitetura. Ambos usam componentes
Nuxt UI sem tema e recebem integralmente as classes e o contrato público do Shopman. As cópias
locais ainda prevalecem enquanto cada app é migrado; removê-las progressivamente faz o app
herdar o componente canônico sem reescrever a tela.

## Custo medido

A comparação foi feita no build cliente da Central, antes e depois da integração:

| artefato | base | Fase 0 | diferença |
|---|---:|---:|---:|
| CSS de entrada, gzip | 19,06 kB | 19,77 kB | +0,71 kB, 3,7% |
| JavaScript principal, gzip | 143,82 kB | 149,64 kB | +5,82 kB, 4,0% |
| módulos processados | 915 | 918 | +3 |

O resultado fica abaixo do teto de 5% definido pelo plano. O CSS global do Nuxt UI não foi
importado: os componentes sem tema recebem somente a aparência canônica do Shopman. O Vite
deduplica `reka-ui`, evitando duas instâncias da infraestrutura headless.

## Inventário e trava

O ledger canônico registra:

- 8 apps de operador;
- 60 telas, incluindo o shell da Central;
- 241 variantes e subtelas;
- componentes UI locais, imports diretos de Reka, overlays manuais e controles nativos por app.

O comando `make test-operator-components` valida o ledger contra o registro de superfícies e
contra os arquivos reais. Durante a transição ele permite a dívida inventariada, mas reprova
qualquer aumento. Também reprova import direto de `@nuxt/ui` por um app. A mesma verificação
roda no gate das superfícies.

## Verificação executada

- `make test-operator-components`: 8 apps, 60 telas e 241 variantes validadas;
- `python3 scripts/check_surface_versions.py`: 38 pacotes compartilhados em 11 apps validados;
- `npm run lint` no `operator-kit`: aprovado;
- `npm test -- --run` no Node 22.23.1: 111 arquivos e 1.224 testes aprovados;
- `npm run build` na Central: aprovado com SSR/Nitro;
- testes dos dois componentes-piloto: aprovados.

O `npm audit` continua apontando vulnerabilidades indiretas já presentes na linha de base,
tratadas por uma frente separada. A Fase 0 não cria exceção nem silencia esse gate.

## Decisão para as fases seguintes

A migração prossegue por família e por app. Primeiro, as cópias idênticas são substituídas
pelos contratos do `operator-kit`. Depois, overlays, seletores, steppers, busca e navegação
recebem revisão funcional e visual caso a caso. Cada redução de dívida atualiza o ledger; cada
tela precisa manter seus fluxos, teclado, toque, foco, estados de erro e adaptação ao contexto.
