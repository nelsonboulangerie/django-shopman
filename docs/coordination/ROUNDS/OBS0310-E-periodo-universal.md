# OBS0310-E: o Período do kit vira controle universal

- **id:** OBS0310-E
- **pedido do dono (03/10):** "O controle de datas 'universal' poderia replicar todas as opções que temos disponíveis no B.I.? Ex.: 'Período / Últimos / Personalizado'. Aí sim seria um controle realmente universal!"
- **branch:** claude/obs0310-periodo-universal
- **PR:** #1414

## O que mudou

- `operator-kit/app/presentation/dates.ts` e `OperatorPeriodPicker.vue`: o popover tem até quatro grupos,
  sempre na mesma ordem: **Período** (Dia, Semana, Mês, Ano), **Próximos** (7D, 14D, 28D, novo: janelas que
  começam hoje), **Últimos** (7D a Máx) e **Personalizado** (De/Até). Cada consumidor liga os que fazem
  sentido (`presets`, `custom`). Novo `max-span-days`: o personalizado recusa com o motivo o intervalo que
  o servidor cortaria em silêncio. O botão diz o nome por extenso ("Últimos 28 dias · 04/09 a 01/10",
  "Próximos 7 dias · 01/10 a 07/10"): o chip "7D" basta dentro do grupo, o botão não tem grupo.
- Período na URL: `periodFromQuery`/`periodToQuery` (chaves `period`, `from`, `to`; o padrão não ocupa a
  URL; ilegível cai no padrão). `todayIso(agora, STORE_TIME_ZONE)` dá o dia de Londrina em qualquer fuso.
- **B.I.**: já usava o controle do kit (promovido dele em 02/10), então não havia migração a fazer; nenhuma
  opção some (`PAST_PERIOD_PRESETS` é exatamente a lista anterior). O que mudou: a janela saiu do
  `useState` e foi para a URL, e as abas da barra levam a query para trocar de aba não trocar de período.
- **Encomendas (PDV)**: o Período passa de Dia/Semana para Dia, Semana, Mês, Próximos 7/14/28 dias,
  Últimos 7/28 dias e Personalizado (até 62 dias, o teto do servidor). Layout intocado (a OBS0310-D está
  nele): mexeu só no script da página e em `presentation/preorders.ts`. A grade da semana já desenha
  qualquer intervalo que o servidor devolve; o modo Dia continua a lista por janela. A URL mantém o
  vocabulário dela (`mode`, `date`, e `to` só no personalizado), para os favoritos já gravados.
- Produção (grade, Expedição, TV, Preparação, Relatórios) e Projeção do B.I.: sem mudança de código; a API
  nova é compatível.

## Prova

Saída dos comandos no PR.

## O que ficou de fora

- "Hoje / Ontem / Mês passado" como chips próprios: o controle já os cobre com Dia/Mês + ‹, e o botão diz
  "Ontem, sex 02/10". Chip duplicado seria dois caminhos para o mesmo estado.
- Comparação com o período anterior no B.I. (F7): continua como estava. Quem a calcula é o servidor, a
  partir do `date_from`/`date_to` (o período de mesmo tamanho imediatamente antes), e a tela continua
  mandando o mesmo par: só mudou onde a seleção mora (URL em vez de `useState`).

## Perguntas ao dono

Ver o PR (respondíveis com sim/1/2).
