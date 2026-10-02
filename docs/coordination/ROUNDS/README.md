# ROUNDS — o registro de uma frente

Um arquivo por frente: `docs/coordination/ROUNDS/<id>-<slug>.md`. É o que a sessão escreve ao
terminar, e é o que o coordenador lê em vez de pedir que alguém cole o relatório no chat.

**Campos fixos.** Campo fixo se lê sem tradução. Não invente campo, não omita campo. Onde não houver
o que dizer, escreva "nada".

O registro entra no MESMO PR da frente (ou num PR de seguimento, se a frente já mergeou). A linha
do `BOARD.md` sai no mesmo PR, quando o registro entra: a fila mergeia sem a sessão voltar, e linha
`EM_PR` de PR que já saiu é o `make coordination` acusando `BOARD desatualizado`.

## Molde

```markdown
# <id> — <frente, em uma linha>

- **id:** <o id do BOARD: R1, F4…>
- **sessão:** <nome da sessão ou do agente; fornecedor se não for Claude>
- **branch:** <nome do branch>
- **PR:** <#número, ou "nada">
- **estado final:** <mergeado #N | na fila #N | PR aberto vermelho #N: causa | esperando decisão do dono: pergunta>
- **início / fim (UTC):** <AAAA-MM-DD HH:MM> / <AAAA-MM-DD HH:MM>

## O que mudou
<o que o sistema faz agora que não fazia; arquivos principais com caminho>

## Prova
<comando rodado e a saída que importa; teste novo e o que ele reprova sem a mudança.
"N testes verdes" não é prova sozinho>

## O que ficou de fora
<cada item com nome e motivo>

## Perguntas ao dono
<a pergunta inteira, respondível com sim/1/2; registrar também em PENDING-DECISIONS.md>

## Armadilhas novas
<o que a próxima sessão vai pisar se não souber; "nada" se nada>

## Próximo passo
<a ação seguinte e de quem ela é>
```
