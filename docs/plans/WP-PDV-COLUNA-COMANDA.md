# WP-PDV-COLUNA-COMANDA: a coluna da comanda com ordem

Estudo de 10/10/2026, pedido do dono: "todas essas possibilidades que estão sendo tratadas
pelos controles da coluna direita ainda não estão bem resolvidas". Inventário lido do código
da branch do #1636 (`claude/pdv-comanda-altura-total`), de `shop/services/pos.py` e do núcleo
`orderman`. **Só desenho: nenhum código de app neste PR.** A página com diagrama e wireframes
dos sete estados é publicada à parte (estudo-coluna-comanda.html).

## 1. O diagnóstico

A coluna mistura três objetos (a **comanda**, **uma linha**, **várias linhas**) e cada um
ganhou um lugar e um jeito próprio de agir: a linha tem editor; várias linhas têm um MODO
(cabeçalho trocado, pé encolhido para "Total parcial"); a comanda tem botões no pé e um ato
inteiro (transferir, dividir, juntar) que só se alcança pelo F10. O operador precisa saber em
que modo está antes de saber o que pode fazer.

## 2. Inventário (resumo)

| Objeto | Ação | Frequência | Atalho | Sem conexão | Observação |
|---|---|---|---|---|---|
| linha | abrir no editor | muito alta | clique, ↑↓ | sim | |
| linha | quantidade − + dígitos | muito alta | dígitos, Backspace | sim | peça pesada sem quantidade |
| linha | remover | média | Del | sim | confirma + Desfazer; na cozinha NÃO cancela |
| linha | observação | média | | sim | 3 portas (grade, expansão, toque) |
| linha | desconto % ou R$ + motivo | baixa | Enter/Esc | não | PIN só no Validar, acima do teto |
| linha | cancelar envio | rara | | não | só cancelável e não pronta |
| linha | ver na cozinha / detalhes | baixa | → ← | sim | |
| marcadas | transferir | baixa | F10 anunciado | não | o F10 global abre vazio |
| marcadas | desconto, remover, enviar, cancelar envio | baixa/média | | parcial | remover em lote sem Desfazer |
| comanda | enviar à cozinha | alta (mesa) | F9 | não | "Enviado" quando nada falta |
| comanda | envio automático | config. | | não | por estação, 90 s parada ou ao sair |
| comanda | dividir a conta | baixa | F10 no Pagamento | parcial | modal no Pagamento (decisão 05/09) |
| comanda | transferir · dividir · juntar | rara | F10 | não | sem porta visível sem selecionar |
| comanda | liberar | baixa | | não | menu ⋯ da barra; cancela na cozinha |
| comanda | pagamento | muito alta | F4 | dinheiro, maquininha | |

## 3. Interações: defeitos, buracos e conflitos

Lidos no código; a prova por teste é o primeiro passo do WP de implementação.

**Defeitos**
- **Transferir perde a cozinha.** `ModifyService.move_lines` dá `line_id` novo à linha movida
  e o livro da cozinha é por `session_key` + `line_id` (`kds_adapter.fired_line_ids_for_session`).
  A linha chega "a enviar" no destino (F9 duplica no KDS) e o ticket da origem fica órfão.
- **F10 promete outra coisa.** O botão Transferir da seleção mostra F10; o F10 global
  (`index.vue`, `openMoveWith()` sem argumento) abre o diálogo vazio, ignorando as marcadas.

**Buracos (a cozinha fica sabendo pela metade)**
- Remover linha enviada: o modal diz "avise o preparo"; o ticket segue vivo. Liberar a comanda,
  ao contrário, cancela na cozinha.
- + numa linha enviada soma na mesma linha (`setQty`); a contagem a enviar ignora linha enviada,
  então a unidade nova nunca vai ao KDS. (O produto lançado pela grade já cria linha nova.)
- − numa linha enviada: só o selo "3 na cozinha · 1 na conta", sem ação.
- Observação nova numa linha enviada grava na conta e não chega ao KDS.
- Desconto acima do teto do gerente: nada avisa no Aplicar; o PIN aparece só no Validar.
- Desconto em R$ no lote passa em peça pesada (vira por quilo); na linha aberta é bloqueado.

**Conflitos (o mesmo gesto em dois jeitos)**
- "Dividir conta" (Pagamento, por pessoa) e "Dividir" (diálogo da comanda, separar numa
  comanda nova): mesmo verbo, dois atos, e o mesmo ícone de Transferir.
- Remover 1 tem Desfazer; remover N não.
- Depois do lote: Enviar sai da seleção; Desconto fica; Remover limpa e fica no modo.
- Com marcas, um dígito abre o desconto do lote.
- Desconto: rascunho na mesa, grava a cada tecla no toque.
- Envio automático: o texto diz "ligado" se UMA estação tem, e não diz quando vai; o relógio
  de 90 s não pausa com rascunho de observação aberto nem com marcas.

## 4. A proposta

**Princípios**
1. **Objeto antes do verbo.** O bloco de ação diz no título sobre o que age ("Quiche Lorraine ·
   R$ 24,90 cada" ou "3 linhas marcadas · 5 itens · R$ 61,70").
2. **Posição fixa por verbo.** Remover no alto à direita, Desconto embaixo à esquerda,
   Observação embaixo à direita, para 1 ou para N. Só o canto da Quantidade (1) vira
   Transferir (N).
3. **Distância por frequência.** Um toque: quantidade, remover, enviar, pagar. Segunda fileira:
   desconto, observação. Menu ⋯: transferir esta, enviar só esta, cancelar envio, separar,
   juntar, liberar. Configuração fica fora da coluna e aparece como estado.
4. **Um padrão por gesto.** Ajuste do que está na tela: inline no bloco, Aplicar e Cancelar.
   Escolha de algo fora da tela (outra comanda, divisão por pessoa): modal. Destruição:
   confirma e oferece Desfazer, para 1 ou para N.
5. **A cozinha não fica sabendo pela metade.** Toda mudança numa linha enviada diz o que
   acontece lá e oferece a ação, na cor do aviso.
6. **Estado em palavra, com o quando.** "4 a enviar · envio automático: ao sair da comanda";
   sem conexão, apagado com o motivo, nunca escondido.
7. **Nada pula.** Cabeçalho h-16 sem troca de conteúdo; pé com a mesma altura sempre; o bloco
   cresce para cima, colado no pé.

**Zonas**

| Zona | Mora aqui |
|---|---|
| Z1 Cabeçalho | itens e linhas; a cozinha em palavra; **Comanda ⋯** (Transferir itens F10, Separar, Juntar, Liberar) |
| Z2 Lista | linhas; caixa de marcar sempre à mão; o fato da linha; o selo da cozinha abre o card dela; a expansão só lê |
| Z3 Bloco de ação | só com foco: título com o objeto, dica do teclado, grade 2×2, aviso acionável, ⋯ com o raro |
| Z4 Pé fixo | Enviar à cozinha \| Dividir a conta (seguem o foco: "Enviar 3 marcadas" \| "Cobrar marcadas") e o Pagamento F4 (sempre a comanda inteira) |

**Seleção sem modo.** Caixa ao lado da quantidade, Espaço, Shift + clique, toque longo. A
linha aberta é a primeira marcada; marcar outra transforma o bloco de 1 no de N. Ato em lote
concluído limpa as marcas; Esc desmarca tudo; dígito não faz nada com marcas.

**Quando estreita.** Tecla cai primeiro, depois o rótulo curto escrito à mão, ícone só no fim.
A grade nunca vira uma coluna; "em 9 linhas" cai antes; o total do Pagamento nunca corta. Na
folha (tablet e celular) valem as mesmas zonas; o toque longo marca.

**Sem conexão.** Funcionam: abrir, quantidade, remover, observação, Pagamento em dinheiro e
maquininha ("total sem conexão"). Apagados com motivo: Enviar ("cozinha sem conexão: avise de
voz"), Desconto ("volta com a conexão"), Transferir, Separar, Juntar, Liberar, Cancelar envio,
Cobrar marcadas.

## 5. As perguntas do dono

- **Só aparecer Transferir depois de selecionar é bom?** Não. Transferir tem dois objetos: a
  comanda inteira (juntar, separar, transferir tudo) não precisa de marca e hoje só existe pelo
  F10. A porta da comanda fica no cabeçalho; a das linhas aparece com o foco.
- **O que mais se faz com vários?** Cobrar só esses ("eu pago o meu"), enviar só esses à
  cozinha, transferir ou separar, desconto, observação em lote, remover, cancelar envio.
  Quantidade não.

## 6. Oportunidades

| Oportunidade | Custo |
|---|---|
| **Cobrar marcadas** (dividir por item): fecha só as linhas marcadas, o resto segue aberto com o mesmo número. O fechamento parcial por `line_id` já existe na venda sem conexão (`pos_offline_sale`, `kds_inherited_lines`). | M |
| **Transferir leva a cozinha junto** (corrige o defeito; pré-requisito de separar e juntar) | S a M |
| **Linha enviada fala com a cozinha** (remover e cancelar, + vira linha nova, − oferece cancelar a diferença, observação oferece reenviar) | S |
| **Comanda ⋯ no cabeçalho** | S |
| **Marcar sem modo** (some Selecionar, cabeçalho trocado e "Total parcial") | M |
| **Aviso do gerente no Aplicar** (o teto já vem na projeção) | S |
| **Segurar para depois** (com envio automático, a sobremesa espera) | M, depois |

## 7. Para decidir

1. Marcar linhas: (1) sem modo; (2) manter Selecionar como modo. **Recomendo 1.**
2. Verbo: (1) o ato da comanda vira "Separar" e "Dividir a conta" fica só para pagar em partes;
   (2) manter "dividir" nos dois. **Recomendo 1.**
3. Cobrar só as marcadas: (1) próximo WP do PDV; (2) depois do go-live. **Recomendo 1.**
4. Com marcas, o Enviar (F9): (1) envia só as marcadas e diz isso; (2) segue enviando tudo.
   **Recomendo 1.**
5. Linha na cozinha que sai ou diminui: (1) perguntar "só da conta" ou "da conta e da cozinha";
   (2) só avisar. **Recomendo 1.**
