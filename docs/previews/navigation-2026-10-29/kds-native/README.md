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

1. CSS do aviso global: composição horizontal, close no canto, texto completo,
   mesmos tons e callbacks. Sem clamp de texto. Alvos mobile com mínimo de 44px.
2. Segunda ação do OperatorActionBar: ícone vertical sem borda, nome acessível
   "Opções do pedido <código>", abrindo o mesmo `onHold` do toque longo.
3. Ações com rótulo longo conservam a largura inteira. A ciência de cancelamento
   ganha `shortLabel: action.label`: a frase original, com código no contexto,
   para não perder o significado em 320px. Não se altera a ação nem sua confirmação.
4. Atalho Histórico na toolbar desktop. O menu original continua disponível.
5. Fonte dos cards, cores, badges, itens, notas e observações permanecem as atuais.

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

- 390×844: aviso 160px em A e 108px em B; foco y=295 versus y=243.
- 320×740: Pronto 0131 continua escrito, alvos de 44px, sem overflow horizontal.
- 320×740, Cafés: "Recebi o cancelamento" legível; código no contexto e na
  identificação acessível, sem botão secundário tomando sua largura.
- Opções abriu o menu atual e daí o histórico atual.
- Pronto seguido de Desfazer voltou o ticket ao mesmo lugar na interface.
- Ciência de cancelamento retirou só o ticket cancelado, mantendo os demais alarmes.
- Atalho desktop abriu o histórico; Reabrir devolveu 0129 à fila e atualizou contagem.
- Capturas desktop em 1440×900: aviso mais baixo e mais conteúdo da segunda linha.
- Viewport temporário restaurado após inspeção.

As capturas são evidência de prévia, não baselines oficiais de CI.

## Pendências explícitas

- Nomes muito longos ainda ocupam muita altura nas linhas compactas em 320px.
  Não se alterou PhoneQueue para esconder ou abreviar informações do operador.
- Som bloqueado depende do navegador. Push, SSE real, segundo plano, tela cheia,
  identidade/lock e ligação com Central/Gestor precisam de ensaio apropriado.
- O novo menu ocupa largura ao lado do CTA normal. A comparação deve decidir se
  a descoberta compensa esse custo; o toque longo foi preservado.
- A avaliação desta rodada não equivale a aprovação global de navegação da suíte.

Sem alterações em Core, kit, backend ou apps de produto. Sem merge ou deploy.
