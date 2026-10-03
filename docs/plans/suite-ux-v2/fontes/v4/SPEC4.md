# Prévias v4 — o rosto da função (leia SPEC.md e SPEC3.md antes; ESTE arquivo prevalece)

Ferramenta, tokens, partials (`rail3top`, `rail3bottom`, `search3`), pinos e legenda: iguais à v3.
Referências visuais aprovadas (v3): `src/orders-board3.html`, `src/orders-search3.html`,
`src/orders-detail3.html`, e as de dispositivo `src/orders-phone3.html`, `src/purchase-receive-phone3.html`,
`src/prod-floor-phone3.html`, `src/pos-sale3-tablet.html` (veja os `out/*.annotated.png`).
NÃO edite `_*.html` nem `_shared.css` (outros agentes usam); CSS próprio num `<style>` do seu arquivo.

**A fonte de verdade desta rodada é o plano por função**, que o dono aprovou:
`/home/user/django-shopman/.claude/worktrees/ux-reform-plan/docs/plans/SUITE-UX-FUNCTION-PLAN.md`
(leia §2 leis, §3 formas e gestos, §4 especificação de cada forma, §5 e §5.1 ação e guardas, §6–8,
§9 fronteira, §10 dispositivos e as três notas, §13 decisões do dono). As fichas de trabalho de cada
app estão em `docs/plans/suite-ux-v2/funcoes/<app>.md` (use para dados e funções reais).

## O que muda em relação à v3 (aplique sempre)
1. **Uma ação primária por item/tela: o fato humano do momento.** Se o sistema já sabe, o item avança
   sozinho e mostra uma marca discreta "o sistema fez · desfazer"; o gesto manual vai para o menu.
2. **Seis significados de estado, só eles** (tons dos tokens): precisa de você (primary/warning) ·
   em andamento (info/primary) · feito (success) · bloqueado com motivo (destructive, com o motivo
   escrito no item) · o sistema fez (neutro com ícone de automático, ex. `sparkles` ou `bot`, rótulo
   "automático") · atenção ao tempo (um número + intensidade). Nada de cor por canal como estado.
3. **Bloqueio antes do gesto** (L3): o motivo aparece no item, o botão fica tracejado com cadeado.
4. **Densidade pela atenção** (L5): fila mostra 4–6 em foco; o resto vira "+N na fila" e agregado.
   Nunca paginação em fila.
5. **Andares**: telas de Operação abrem na fila do papel; Ajustes é um item próprio no rail ("Ajustes").
6. **Nomes decididos**: o posto de saída do pedido se chama **"Saída"** ("Saída da Cozinha" quando
   couber). A etiqueta de consumo do produto se chama **"Vocação"** (consome aqui · leva · os dois).
7. **Celular**: barra de cima 56px (selo, título, ponto ao vivo, busca, sino) + barra de seções embaixo
   + ação no polegar. Tablet: alvos 48px, sem teclas impressas, teclado numérico na tela só sob
   demanda. Desktop: teclas impressas.
8. Copy: português, sem travessão longo em texto de tela, "dispositivo"/"maquininha" (nunca
   "aparelho"), "lote" (não fornada) nos apps de operador, "Tentar de novo", "Visto" só onde nada
   mais prova a ciência.

Entregue: arquivos gerados e, por tela, 3–6 linhas "o que esta tela mostra da função" (que lei/forma
ela materializa) + qualquer função que não coube. Itere até os PNGs estarem impecáveis (Read neles).
