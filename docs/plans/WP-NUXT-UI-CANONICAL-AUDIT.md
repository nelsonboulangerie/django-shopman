# WP destacado: anatomia canônica do Nuxt UI

**Estado:** diagnóstico transversal; correções compartilhadas pequenas aplicadas localmente  
**Origem:** prévia do CRUD humano do Compras, 23/10/2026  
**Alcance:** superfícies Nuxt de operador; Storefront fica fora

## O que significa canônico

Um elemento é canônico quando o componente oficial do Nuxt UI é dono da anatomia,
teclado, foco e ARIA. O `operator-kit` pode fixar tokens, densidade, tamanho de toque e
contratos repetidos, mas não deve reconstruir com classes uma peça que o Nuxt UI já
resolve.

Usar `:ui` não é desvio por si só. Ele é o ponto oficial de adaptação. O desvio começa
quando a adaptação troca a composição do componente, esconde um estado necessário ou
mantém uma API paralela sem necessidade atual.

## Correções compartilhadas desta frente

### Avisos

Os avisos compartilhados estavam no componente oficial `NuxtAlert`, mas forçavam
`orientation="horizontal"`. Isso colocava texto, ação e fechar em disputa na mesma linha,
especialmente no celular. A orientação vertical padrão é deliberada:

- título e descrição permanecem juntos;
- a ação fica abaixo da mensagem;
- o fechar ocupa o canto superior direito da anatomia do próprio alerta;
- fechar oculta somente naquela carga. Se a causa continuar, o aviso volta no próximo
  carregamento.

A correção alcança `OperatorPageHeader`, erro de `OperatorScreenState`, convite de push
e aviso de atualização do PWA. Nenhuma tela precisa remontar essa composição.

### Linhas que abrem registros

`OperatorTable` já delega à `NuxtTable` o contrato de linha selecionável: foco por
teclado, Enter ou Espaço, clique e proteção para controles internos. Agora a linha recebe
`cursor-pointer` somente quando a tela fornece `onSelect`.

O cursor é confirmação, não a única pista. Hover, foco visível, nome acessível e, quando
necessário, chevron ou texto de ação continuam obrigatórios.

## Contrato cross-system para superfícies clicáveis

1. Se toda a linha abre o mesmo registro, toda a linha é o alvo. Em tabela, usar
   `OperatorTable :on-select`; não embrulhar a linha em um botão improvisado.
2. Se um card simples tem um único destino e nenhum controle interno, o link ou botão
   canônico pode ocupar o card inteiro.
3. Se o card contém menu, checkbox, link ou ação secundária, a região principal abre o
   registro e os controles ficam como irmãos. Nunca aninhar elementos interativos.
4. Se o gesto apenas expande conteúdo no lugar, usar um botão de expansão claro com
   chevron e `aria-expanded`. O card inteiro só ganha cursor se o card inteiro expandir.
5. Mouse recebe cursor; teclado recebe foco visível e Enter ou Espaço; toque recebe alvo
   confortável. Nenhum desses sinais substitui os outros.

Para Insumos, a melhor forma é a primeira: a linha inteira abre a ficha. Ela já usa a
seleção oficial da tabela, portanto não precisa de um botão “Abrir” repetido em cada
linha. Ações secundárias futuras devem permanecer controles independentes.

## Inventário inicial

A varredura encontrou alertas em 106 arquivos Vue de operador. Além dos quatro pontos
compartilhados corrigidos, ainda existem dois alertas que forçam horizontalidade:

- Pedidos: `VolumeCheckBar.vue`;
- B.I.: `pages/explore.vue`.

Eles devem ser avaliados no turno dos respectivos apps, pois a barra de aferição de
volume e o erro de exploração têm contextos diferentes.

O PDV mantém 69 usos de `UiButton` em 15 arquivos. O componente encaminha para
`NuxtButton`, mas traduz uma API legada e conserva tamanhos próprios. É dívida de
compatibilidade, não motivo para substituição cega. `UiTextarea` ainda aparece em dois
formulários do PDV e deve entrar na mesma revisão.

Também merecem prova de uso antes de manutenção ou remoção os adaptadores sem uso de
produção encontrado nesta varredura: `UiNativeSelect`, `UiIconButton`, `UiSearchInput`,
`UiToggleChip` e `UiStepper`.

Botões nativos não são automaticamente um erro. Numpad, seletor de dia, controles de
trilho e outras peças compostas têm semântica própria. Já os botões manuais de
`OperatorPushSettings` são candidatos fortes a `NuxtButton`, porque representam ações
comuns, não um widget especializado.

## Ordem de execução

1. Fechar e validar as correções compartilhadas já pequenas.
2. No turno de cada app, revisar os pontos daquele app e comparar a prévia antes/depois.
3. Migrar adaptadores legados por família, com prova de equivalência de foco, tamanho de
   toque e estados. Não fazer busca e troca global.
4. Validar primeiro em 320×568, depois 390×844, tablet e mesa, nos temas claro e escuro.
5. Mostrar a prévia local para aprovação antes de qualquer push ou PR.

Este WP registra um padrão e uma fila de diagnóstico. Ele não autoriza mudar todos os
apps de uma vez.
