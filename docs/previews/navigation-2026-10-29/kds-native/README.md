# Cozinha/KDS: conciliação reversa

Somente prévias, aguardando avaliação visual. Entrada: `../kds-native.html`.
Fonte: `origin/main` fixado em `e0c22ba1ffe28e20c5c453db09160e941dfae8c6`.

## Preservação

`preservation.json` registra SHA-256 e igualdade com a fonte de nove componentes:
TicketCard, PhoneQueue, HistoryDialog, HoldSheet, SettingsDialog, TicketModal,
CardButton, AllDayStrip e StationControls. Não se reescreveu nenhum deles nem a
ordenação, cálculo de foco, gestos ou estados dos composables. O painel público
`pickup.vue`, para TV, também não foi editado.

Mudanças exclusivas da cópia temporária, aplicadas por `apply-preview.mjs`:

1. Somente o dismiss do aviso global vai para o canto superior direito.
   Composição, padding, descrição, cores e botão Visto ficam como na fonte.
   Reserva de espaço no título impede sobreposição com o dismiss.
2. Botão Nuxt de três pontos verticais, ghost e sem borda, na extremidade direita
   da linha de contexto do rodapé, acima do Pronto. Abre o mesmo `onHold`.
   O OperatorActionBar fica sem ação secundária e conserva toda a largura do CTA.
3. O `shortLabel: action.label` da rodada anterior fica preservado: a frase original
   de ciência, com código no contexto, permanece legível em 320px.
4. O atalho Histórico na toolbar desktop permanece da rodada anterior.
5. Cards, cores, badges, itens, notas e observações permanecem como na fonte.

O menu de contexto tem alvo de 44px. A linha de contexto ganha 12px de altura em
relação à proposta anterior para acomodá-lo sem sobrepor a ação. A barra inteira,
incluindo o novo menu, segue a regra de ocultação quando o teclado está aberto.

Não se aplicou ao KDS o card de busca do PDV nem um template genérico de ERP.
O operador continua com um ticket em foco no mobile; na mesa, filas em ordem de
leitura, sem masonry e sem forçar tickets a uma altura uniforme.

## Reprodução

Com Node 22 no PATH e portas 38798, 4192 e 4193 livres:

```
bash docs/previews/navigation-2026-10-29/kds-native/run.sh
```

O script arquiva fonte e kit em diretório temporário exclusivo, instala os locks,
compila A intacto e aplica B. Não escreve em `surfaces/` da worktree. `apply-preview`
se destina a uma extração nova, não deve ser reaplicado à mesma cópia.

## Simulador

`prepare-mock.mjs` parte do mock e dos quadros existentes do KDS. `preview-state.mjs`
extende somente o estado fictício: iniciar, Pronto, histórico, reabrir, ciência,
contagens, tamanho, som, separação, volumes e revisão. Reset e falha única passam
pelo BFF da cópia. O teste `verify-mock.mjs` sobe outro processo em 38799 e o encerra.
Saída real em `verification.txt`: nove cenários passaram.

Atenção global e mudanças por ticket continuam distintas: Visto global marca
recebimento dos novos tickets, sem apagar mudanças ou cancelamentos individuais.
Ticket já despachado não reabre; volumes com revisão antiga falham. O simulador
não reproduz as políticas reais do orquestrador nem valida integrações físicas.
Os tempos e códigos dos tickets são exemplos fixos das fixtures originais.

## Verificação visual

Build Nuxt de A e B concluído. Navegador por túnel, sem Django real:

- 390×844: aviso 160px em A e 118px em B; foco y=295 versus y=253.
- 320×740: Pronto 0131 continua escrito, alvos de 44px, sem overflow horizontal.
- 320×740, Cafés: "Recebi o cancelamento" legível; código e menu na linha
  de contexto, sem tomar largura da confirmação.
- Opções abriu o menu atual e daí o histórico atual.
- Pronto seguido de Desfazer voltou o ticket ao mesmo lugar na interface.
- Ciência de cancelamento retirou só o ticket cancelado, mantendo os demais alarmes.
- Atalho desktop abriu o histórico; Reabrir devolveu 0129 à fila e atualizou contagem.
- Capturas desktop em 1440×900: dismiss no canto; alerta com composição original.
- Viewport temporário restaurado após inspeção.

As capturas são evidência de prévia, não baselines oficiais de CI.

## Pendências explícitas

- Nomes longos na fila: resolvidos na composição abaixo de 375px, conforme
  a revisão a seguir. Nenhum resumo foi cortado ou abreviado.
- Som bloqueado depende do navegador. Push, SSE real, segundo plano, tela cheia,
  identidade/lock e ligação com Central/Gestor precisam de ensaio apropriado.
- O menu não divide mais a linha do CTA. A linha de contexto fica 12px mais alta
  que na proposta anterior. O toque longo foi preservado.
- A avaliação desta rodada não equivale a aprovação global de navegação da suíte.

Sem alterações em Core, kit, backend ou apps de produto. Sem merge ou deploy.

### Revisão de dismiss e contexto

Verificada pelo túnel em 390px, 320px e desktop 1440×900. Em 390px, dismiss a 8px
do topo e da direita do alerta; CTA e contexto com 342px. Em 320px, Pronto e
Desfazer mantiveram 272px de largura e a mesma posição. Menu abriu o drawer
atual, e Desfazer retornou o ticket. Sem overflow horizontal. Capturas atualizadas.
Build Nuxt concluído em 16,1s. Simulador e os nove componentes preservados não
foram alterados nesta revisão. Sem implementação no produto ou deploy.

### Revisão da fila compacta em 320px

Somente CSS de composição dos filhos existentes de `data-kds-queue-row`, até
374px. Código, posição/alarme e tempo/bloqueio ocupam a primeira linha; o mesmo
resumo completo ocupa a largura da segunda. Sem clamp, reticências, limite de
linhas, fonte menor, truncamento ou alteração dos dados. Sem mudança de template,
handlers, card em foco, ordem da fila ou cálculo de urgência.

Evidência no navegador, com aviso inicial reconhecido nos dois lados:

- 320px: primeiro resumo longo com texto idêntico, de 182px para 96px; largura
  do resumo 255px. Linhas curtas de 64px para 76px. Total das três: 310px para 248px.
- Toque na linha 0138 trouxe o card completo, incluindo observações por item e
  alergia a castanhas, e atualizou o CTA para Pronto 0138.
- Cafés em 320px: alarmes Mudou e cancelamento preservados.
- 390px: layout flex original; alturas 82px, 64px, 64px.
- Desktop 1440px: fila mobile fora da árvore; grade original com três colunas.
- Sem overflow horizontal nas três larguras. Viewport restaurado.
- Build Nuxt concluído em 20,2s. Nenhuma mudança no simulador.

Capturas: `queue-before-320.png` e `queue-after-320.png`.

### Navegação e cabeçalho: proposta isolada

`apply-navigation.mjs` altera apenas a cópia temporária. Acrescenta slots opcionais
no título do PageHeader e na identidade do SuiteShell, sem mudar os respectivos
conteúdos padrão. Não altera o kit da worktree de produto.

- Ícone da Cozinha no canto abre a Central simulada. No desktop aparece uma vez:
  na lateral visível, ou no cabeçalho quando a lateral está oculta.
- Nome da estação abre seletor com nomes e contagens do índice atual. Histórico,
  atualização e som/tamanho continuam usando os callbacks e diálogos existentes.
- Menu completo continua sendo a gaveta nativa. Atalhos inferiores mantêm posição
  entre estações; Mais indica quando a estação atual está fora dos atalhos.
- Controle da lateral no desktop oferece Expandida, Compacta e Oculta explicitamente,
  usando a máquina de estados existente.
- Central e destinos de apps são simulações de navegação, sem reconstruir operação
  de outros apps. Saída continua sendo fronteira com o Gestor. Voltar restaura a
  estação e o foco selecionado quando o ticket ainda existir.
- A finalização pendente ao sair segue o comportamento nativo de desmontagem do
  quadro. Não se promete manter a janela de Desfazer entre aplicativos.

O card em foco recebe contorno claro com a mesma espessura do estado de urgência.
Vermelho prevalece em atraso, mudança e cancelamento. Finalização mantém seu estado
tracejado. Os componentes originais continuam intactos; o marcador de Agora no
layout desktop é passado pelo template da página da cópia.

A simulação no mesmo domínio não comprova instalação PWA, abertura entre origens,
login real, push, SSE ou som em segundo plano. Esses ensaios seguem pendentes.

Verificação desta rodada pelo túnel: 320×740 sem overflow (scrollWidth 320),
contorno claro rgb(240,230,210) de 2px no card em foco. Toque na fila mudou
o foco para 4821. Seletor abriu as quatro estações e ações atuais; Encomendas
não reordenou os atalhos. Central → PDV simulado → retorno trouxe Encomendas.
Desktop 1440×900 sem overflow, Agora atrasado com 2px rgb(233,120,108).
Oculta removeu a lateral e deixou um único ícone do app no cabeçalho; Compacta
restaurou a lateral só com ícones. Build Nuxt concluído. Capturas navigation-*.png.
