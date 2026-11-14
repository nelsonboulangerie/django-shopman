# COMMITMENTS — o que o repo deve, com dono, prazo e prova

> **Isto não é um plano.** É o registro único de tudo que o dono pediu, o time
> adiou, alguém achou ou uma decisão deixou em aberto, e que ainda não está no
> `main` com prova. Se um PR diz "ficou de fora", o item é uma issue com label
> `ficou-de-fora`, e a linha daqui é o índice com dono, prazo e prova.
>
> `make commitments` mostra o que venceu. O CI reprova PR novo sem
> `Compromisso: DEV-AAAA-NNN`; o adiamento tem o gate próprio `Ficou de fora declarado`.
> Um job semanal abre uma issue com os vencidos e a fecha quando a lista zera.

## Regras

1. **Toda solicitação e todo adiamento nascem aqui, no mesmo turno.** A fala do dono é
   registrada antes do primeiro edit; o adiamento, no mesmo PR que o criou. Nada
   de "fica para depois" só no corpo do PR.
2. **Toda linha tem dono nomeado.** "Ninguém", vazio, "a definir" e "TBD" não valem.
   `Coordenação` é um papel ativo: se ninguém assume a esteira no turno, o item é
   `BLOQUEADO`, não `ABERTO`.
3. **Toda linha aberta tem `revisar_em`.** A data é a trava: sem ela, o item não
   vence e portanto não é cobrado. `gatilho` é o evento que fecha o item quando o
   fim não depende de uma data.
4. **`FEITO` exige `prova`**: PR, commit ou comando com saída. Sem prova, o estado
   máximo é `EM_EXECUCAO`.
5. **`DESCARTADO` exige quem decidiu e por quê** na `prova`. Descartar é decisão,
   não sumiço.
6. **`SUPERSEDIDO` aponta o ID que o substituiu.**
7. **Entrada não se apaga.** Estado terminal fica; o histórico é a prova de que
   foi resolvido.

## Vocabulário

`tipo`: `solicitacao` (fala do dono) · `compromisso` (trabalho adiado) · `decisao`
(pergunta que só o dono responde) · `achado` (risco ou defeito a triar).

`estado`: `ABERTO` · `EM_EXECUCAO` · `BLOQUEADO` · `FEITO` · `DESCARTADO` ·
`SUPERSEDIDO`.

`VENCIDO` não se escreve: é calculado quando `revisar_em` passa e o estado não é
terminal.

## Como registrar

```bash
make intake q="<as primeiras palavras do dono, literais>" dono="Engenharia"
```

O comando devolve o ID e a linha pronta para o PR:

```
DEV-2026-007
Compromisso: DEV-2026-007
```

O PR novo cita `Compromisso: DEV-2026-007` e a seção `## Ficou de fora` lista os adiamentos
que ele criou. Solicitação que não virou trabalho também fica `ABERTO`, com
`revisar_em` curto: a linha é o que impede o esquecimento.

## Tabela

<!-- commitments:start -->
| id | tipo | origem | compromisso | dono | criado | revisar_em | gatilho | estado | prova |
|---|---|---|---|---|---|---|---|---|---|
| DEV-2026-001 | compromisso | #2298 / #2300 | B.I.: tempo corrido desde kitchen_released_at e tempo de preparo (Iniciar a Pronto) | Engenharia · B.I. | 2026-11-12 | 2026-11-26 | encomenda futura no ar | EM_EXECUCAO | #2300 |
| DEV-2026-002 | compromisso | #2298 / #2301 | Editar preorder_kitchen no Admin, hoje só JSON em Shop.defaults | Engenharia · Admin | 2026-11-12 | 2026-11-26 | #2298 na fila | EM_EXECUCAO | #2303 |
| DEV-2026-003 | compromisso | #2292 | Aviso antes de salvar o fechamento do dia (padrão de confirmação em dois passos) | Engenharia · Admin | 2026-11-12 | 2026-12-03 | padrão de confirmação existir no Admin | ABERTO | - |
| DEV-2026-004 | compromisso | #2292 | Horário especial que encurta o dia não é conferido contra os horários dos pedidos | Engenharia · Admin | 2026-11-12 | 2026-12-03 | - | ABERTO | - |
| DEV-2026-005 | decisao | #2069 | Aprovar ou recusar o modo compacto x padrão (KDS, PDV, Gestor, Receber) | Pablo | 2026-11-02 | 2026-11-14 | resposta do dono à prévia | ABERTO | - |
| DEV-2026-006 | achado | STATUS-CONSOLIDACAO-2026-11-10.md | Triar o que restou das 5 frentes sem dono (ADR-025 Doorman, ledger C11, ciclo C6, leitura paralela) | Coordenação | 2026-11-10 | 2026-11-19 | - | ABERTO | - |
| DEV-2026-007 | solicitacao | chat 2026-11-12 | Quero poder, SEMPRE que eu discutir algo, seja uma correção, ou um pedido de uma feature nova, NADA seja perdido, nunca mais! | Engenharia | 2026-11-12 | 2026-11-19 | - | EM_EXECUCAO | - |
| DEV-2026-008 | solicitacao | chat 2026-11-12 | o que mais me importo é com a SAÚDE do REPO! Está muito cansativo e desesperador manter esse desenvolvimento!!! Faça algo a respeito. | Engenharia | 2026-11-12 | 2026-11-19 | - | EM_EXECUCAO | - |
| DEV-2026-009 | compromisso | #2303 / #2304 | Preparo da encomenda no painel do produto do Catálogo (Gestor) | Engenharia · Catálogo | 2026-11-12 | 2026-12-03 | - | ABERTO | - |
| DEV-2026-010 | solicitacao | chat | BRIEF ID3A: infraestrutura de IA do Django Shopman. Sua tarefa é produzir um plano de desenvolvimento da ID3A, não código. | Engenharia | 2026-11-12 | 2026-11-19 | - | ABERTO | - |
| DEV-2026-011 | solicitacao | chat 2026-11-12 | Suporte (helpdesk interno): chamado, hub na Central, gate de aprovação do dono e DEV- | Engenharia · Suporte | 2026-11-12 | 2026-11-19 | #2310 na fila | EM_EXECUCAO | #2310 · #2314 · #2315 |
| DEV-2026-012 | solicitacao | chat 2026-11-12 | Pedidos iFood cancelados pelo próprio iFood: causa medida = ninguém aceita em 8 min (09/11 pedido 6957; 12/11 15:30 IFOOD-* entrou no Gestor e caiu às 15:37) | Engenharia · iFood | 2026-11-12 | 2026-11-13 | - | EM_EXECUCAO | - |
| DEV-2026-013 | decisao | chat 2026-11-12 | Aceite dos pedidos iFood: o sistema aceita sozinho na chegada (fim do cancelamento por prazo) ou segue manual no Gestor de pedidos com 8 min | Pablo | 2026-11-12 | - | - | FEITO | chat 2026-11-12, Pablo: "Fica manual" (aceite segue manual no Gestor de pedidos, 8 min) |
| DEV-2026-014 | compromisso | chat 2026-11-12 | Webhook do app de produção do iFood em standby (decisão do dono 12/11: só polling); reavaliar depois de dias estável | Engenharia · iFood | 2026-11-12 | 2026-11-26 | dias estáveis só com polling | ABERTO | - |
| DEV-2026-015 | achado | logs 2026-11-12 | Itens do cardápio iFood sem de-para com SKU do catálogo (alertas stock_unknown_sku no 1º pedido real) | Engenharia · iFood | 2026-11-12 | 2026-11-19 | - | ABERTO | - |
| DEV-2026-017 | solicitacao | chat | Testei. Fiz eu mesmo um pedido. Em tese funcionou sim. Mas com alguns problemas... Pedido IFOOD-261112-3417: observação perdida, pagamento duplicado, entregador chamado antes do Pronto, avisos Não enviado, Primeira compra com ticket médio, chat do cliente | Engenharia | 2026-11-12 | 2026-11-19 | - | ABERTO | - |
| DEV-2026-016 | compromisso | chat 2026-11-12 | Desligar o webhook do app de teste NB Teste (C), que passou a receber 401 com o segredo de produção | Engenharia · iFood | 2026-11-12 | 2026-11-19 | - | FEITO | portal iFood 12/11: webhook do NB Teste (C) desligado, 'Suas alterações foram salvas' |
| DEV-2026-018 | solicitacao | chat | O mais grave que vejo ali é que a coluna quando colapsada está mal diagramada.. Não mereceria um menu lateral Canais? Você contemplou a questão de Juntar entregas? Pode fazer! | Engenharia | 2026-11-13 | 2026-11-20 | - | ABERTO | - |
| DEV-2026-021 | solicitacao | chat | nfce ok, assim que formos pro golive ja estara em producao. faça toda parte do ifood ok | Engenharia | 2026-11-13 | 2026-11-20 | - | ABERTO | - |
| DEV-2026-019 | solicitacao | chat 2026-11-12 | E sim, se for a única solução, teremos que embutir o widget! (Widget do iFood no Gestor, issue #2321) | Engenharia · iFood | 2026-11-12 | 2026-11-19 | - | ABERTO | - |
| DEV-2026-022 | solicitacao | chat 2026-11-14 | O modo Quadro não ia ser o "padrão"? Coluna em preparo, ao expandir, com a mesma largura das demais (as abertas dividem o espaço igualmente). Pedido do iFood: widget de chat do iFood (é o #2323); pagamento ainda parece duplicado; otimizar a página do pedido do iFood (entregador definido pelo iFood, status que o iFood controla) | Engenharia | 2026-11-14 | 2026-11-21 | - | EM_EXECUCAO | - |
<!-- commitments:end -->
