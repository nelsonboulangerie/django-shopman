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

## Fechamento esperado

O primeiro push é deliberadamente draft: a CI produz os `actual.png` que ainda não
existiam. Depois da revisão desses artefatos, um segundo commit incorpora apenas os
retratos aprovados e o job precisa terminar 79/79 verde antes da fila de merge.
