# Compras: Receber compacto (prévia A × C, 30/10/2026)

Somente prévia. A = `origin/main` intacto. C = A + `compact-kit` + `apply-compact.mjs`
(só `pages/receive.vue` muda; Painel, Comprar e Base seguem o cabeçalho padrão).
`run.sh` reproduz (mock 38930, A 4321, C 4322; `EVIDENCE=1` refaz `shots/`).

## Medidas (px, Playwright headless; `shots/evidence.json`)

| Conferência | Cabeçalho A → C | Área útil da lista A → C | Rodapé (barra da ação / barra inferior) |
|---|---|---|---|
| 320×568 | 89 → 61 | 298 → 327 (+29) | 387 / 503 em A e C |
| 375×667 | 67 → 59 | 419 → 427 (+8) | 486 / 602 em A e C |
| 320×740 | 89 → 61 | 470 → 499 | 559 / 675 |
| 390×844 | 67 → 59 | 596 → 604 | 663 / 779 |

No começo: cabeçalho 116 → 59 em todas as larguras (a linha "Com NF | Sem NF" sai; "Sem NF"
já está no polegar e "Lançar sem NF" nas Opções). Alvos abaixo de 44px no cabeçalho do
celular: A 5 a 6 (todos de 32px), C 0. Sem rolagem horizontal em nenhuma largura.
Os dois rodapés juntos ocupam 181px (116 + 65) e não mudam em C.

## Preservado
Fluxo, folha do item com `?line=` e "‹ 1 de 3 ›", polegar (Escanear NF / Contei N volumes /
Confirmar entrada), as ações do ⋯ (mesma ordem), a barra inferior, erro de leitura com
"Tentar de novo", faixa "Sem conexão", a mesa (1440: medidas idênticas, OperatorLiveStatus e
rail presentes). Painel, Comprar e Base: medidas idênticas em A e C.

## Melhorado
- Conferência identificada na linha: ‹ | fornecedor + NF + hora da leitura (+ volumes contados).
- Busca ativa tem faixa visível com contagem e Limpar (em A, nenhum sinal na tela).
- Hora da leitura e o modo de leitura sobem para o topo das Opções.

## Precisa de decisão
1. **Gaveta sem "Mais"**: o Compras tem 4 seções, todas na barra inferior, e nenhum "Mais".
   Sem o ☰, C põe "Menu completo" no fim das Opções. Bloqueio da regra 7: decidir entre
   "Mais" na barra inferior ou este item.
2. **Continuidade**: da Base para o Receber, o ☰ some, o título some, o ⋯ vira ⋮ dentro de
   uma moldura e aparece o selo. Só o sino fica no lugar (desloca 4px e 10px). Ou os cadastros
   adotam o mesmo selo e ⋮, ou o salto fica aceito como "tela de tarefa".
3. **Busca no celular não filtra nada visível** (A e C): a conferência por exceção esconde a
   lista abaixo de md; a busca só filtra essa lista e a trilha. C deixa isso explícito ("1 de 3
   itens"), mas o item continua visível no fluxo. Decidir se a busca filtra o fluxo ou sai.
4. **Chip do selo**: o Compras lê só ao abrir e em Atualizar. C usa o tom neutro (↻), cujo
   nome acessível diz "atualização periódica"; o verde diria "ao vivo". O kit não tem o tom
   "leitura sob demanda".
5. Ganho em 375×667 é de 8px; o grosso da altura são os rodapés (181px). Esconder a barra
   inferior durante a conferência é decisão de produto, fora da regra.

## Riscos a 320px e pouca altura
Identidade com cerca de 100px: "NF 12.912 · lida 12:25 · 6 de 6 volumes" quebra em 3 linhas
(o cabeçalho vai a 76px). Nome de fornecedor longo fica limitado a 2 linhas.

## Achados adversariais (também em A)
- Erro ao gravar a contagem (500): o aviso aparece, mas a contagem fica 6 de 6 e o polegar já
  oferece "Confirmar entrada" (estado local avança sem a gravação).
- A ação principal do polegar a 320 e 375 é só o ícone ✓ (o texto "Contei 6 volumes" só existe
  no nome acessível).
- Folha do item a 320px: "Fechar sem conf…" e "Remover ite…" cortados no pé.

## O mock não cobre
Avisos com conteúdo (caixa vazia), sessão expirada, trava de PIN, câmera real, NF sem
fornecedor casado, entrada sem NF com itens, falha do confirmar, cenário global
compartilhado entre A e C (quem mexe num túnel muda o outro).
