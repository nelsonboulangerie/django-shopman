# V6-SEG-MKT-VISUAL-GATE: a v4 volta a ter prova visual

**Data:** 05/10/2026  
**Branch:** `codex/suite-ux-v4-visual-gate`

## Por que esta frente existe

O `main` recebeu a conformidade v4 da suíte nos PRs #1453 a #1482, mas o job
`Marketing — cadeia completa` do PR #1482 terminou com **62 falhas e 17 testes
passando**. O código foi mergeado mesmo com o gate vermelho.

As falhas misturavam três causas diferentes:

1. retratos anteriores à nova casca e à fila da v4;
2. testes que ainda procuravam a anatomia anterior, como a prévia sempre aberta,
   filtros em bloco e a lista de campanhas em `<li>` também no desktop;
3. uma regressão real: `Criar cupom` deixou de ser alcançável no celular quando o
   cabeçalho passou a mostrar apenas a ação primária `Criar oferta`.

## O que esta frente muda

- devolve `Criar cupom` ao celular no menu canônico da página;
- preserva `Criar oferta` como ação primária de um toque;
- faz a matriz operar a anatomia v4 por nomes e papéis acessíveis;
- mantém a prévia do anúncio recolhida na decisão e a abre somente nos cenários que
  realmente testam a prévia;
- testa a prévia congelada da confirmação no tablet, onde a caixa cobre a revisão;
- incorpora 40 imagens `actual` produzidas pelo próprio runner macOS/Chromium do
  job oficial, depois de separar mudança intencional de falha funcional.

## Prova antes da CI

- `npm run lint`: verde;
- `npm run typecheck`: verde;
- `npm test -- --run`: **51 arquivos, 441 testes verdes**;
- matriz visual local após a primeira reconciliação: **56/79 verdes**; as 23 falhas
  restantes eram 19 diferenças de imagem e quatro contratos antigos de teste;
- os quatro contratos foram corrigidos e chegam ao retrato. As imagens novas não
  são gravadas localmente: a baseline canônica só nasce no navegador pinado da CI.

## Prova no navegador oficial

O primeiro push do PR #1483 deixou toda a cadeia anterior à comparação visual
verde: build, testes unitários e de componente, E2E e acessibilidade. A matriz
terminou com **57/79 retratos verdes** e 22 diferenças puramente visuais, sem erro
de navegação, seletor ou comportamento.

Os 22 `actual.png` vieram do artefato `marketing-browser-gates` da execução
`37254086207`. Todos foram inspecionados antes da promoção: painel responsivo,
busca e filtros, formulário de cupom, formulários de campanha, conflito de edição,
confirmações simples e em duas pessoas, prévias simuladas, indisponibilidade de
plataformas, handoff e espaçamento WCAG. Três retratos eram novos e 19 substituíam
baselines da anatomia anterior.

A execução seguinte (`37254821053`) chegou a **78/79**. A única diferença não era
de layout: o teste fotografou a busca da suíte ainda em `Buscando…`, antes de a
resposta de indisponibilidade aparecer. A matriz agora espera explicitamente esse
estado final antes do retrato; o cenário isolado passou localmente sem alteração da
imagem canônica.

Na execução `37255238187`, o gate de acessibilidade mediu o primeiro frame do tema
escuro enquanto o rótulo `Mais` ainda herdava a cor clara. O mesmo código havia
passado nas duas execuções anteriores e os três testes passaram localmente. O teste
agora aguarda a cor herdada convergir para o token do tema antes de chamar o axe;
isso preserva a exigência AA e elimina a medição intermediária.

Durante a conferência da prévia local, o dono apontou que o fundo dos itens ativos
do rail ficava próximo demais das bordas. A peça canônica `RailSection` passou de
64 px para 60 px dentro do trilho de 76 px: são 8 px de respiro por lado em toda a
suíte, sem reduzir o alvo abaixo do mínimo de toque. O teste do kit fixa essa medida.

A execução `37255932603` aprovou a matriz da Produção, o kit e **78/79** retratos de
Marketing com o novo rail. O retrato restante alternava entre o topo do diálogo e o
campo de data que o navegador acabara de focar. O cenário agora espera o salvamento
do rascunho e reposiciona explicitamente o scroll interno no topo; o retrato isolado
passou sem mudar a baseline.

## Critério de fechamento

O segundo commit incorpora somente esses retratos produzidos pelo Chromium pinado
da CI. A frente só entra na fila quando a nova execução terminar 79/79 verde.
