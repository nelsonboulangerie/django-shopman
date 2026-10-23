# WP destacado: anatomia canônica do Nuxt UI

**Estado:** executado localmente; aguardando aprovação da prévia antes de publicar
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

## Resultado da execução

A varredura cobriu 106 arquivos Vue de operador. Os sete alertas que forçavam a
orientação horizontal foram corrigidos: quatro componentes compartilhados do kit,
`OperatorStationSetup`, `VolumeCheckBar` de Pedidos e a falha de exploração do B.I.
A orientação oficial organiza mensagem, ações e fechar sem disputa de largura.

O PDV teve os 69 usos de `UiButton`, distribuídos em 15 arquivos, migrados para
`NuxtButton`. Os dois usos de `UiTextarea` foram migrados para `NuxtTextarea`. Os dois
adaptadores sem consumidor foram removidos, portanto não existe mais uma API paralela
para ações comuns ou texto longo.

O `UiNativeSelect`, já aposentado e sem uso de produção, também foi removido junto com
o CSS específico e o teste do adaptador. Escolhas novas usam `NuxtSelect` ou
`NuxtSelectMenu`.

Os botões comuns de `OperatorPushSettings` agora são `NuxtButton`. Botões nativos de
numpad, seletor de dia e controles de trilho permanecem porque são partes de widgets
compostos, não substitutos locais para uma ação comum.

`UiStepper` permanece porque acrescenta navegação responsiva e vocabulário de estado ao
`NuxtStepper`. `UiIconButton`, `UiSearchInput` e `UiToggleChip` permanecem como contratos
especializados do catálogo, com foco, semântica e comportamento próprios. Eles não são
adaptadores de compatibilidade para uma peça oficial equivalente.

## Travas e validação

- a trava transversal reprova qualquer `NuxtAlert` que volte a forçar orientação
  horizontal;
- a trava de acessibilidade passou a inspecionar `NuxtButton` diretamente;
- o conjunto mínimo impede reintroduzir tamanhos, cores ou variantes fora do contrato;
- testes, lint, tipos e builds dos apps atingidos são a evidência de equivalência;
- a prévia permanece somente local até a aprovação visual.

Este WP não é mais uma fila de diagnóstico. A implementação está no branch local e não
será enviada nem transformada em PR antes da aprovação da prévia.
