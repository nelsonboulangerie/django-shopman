# COMMITMENTS — o que o repo deve, com dono, prazo e prova

> **Isto não é um plano.** É o registro único de tudo que o dono pediu, o time
> adiou, alguém achou ou uma decisão deixou em aberto, e que ainda não está no
> `main` com prova. Se um PR diz "fora deste PR", "seguimento", "pendência" ou
> "ficou de fora", ele aponta para uma linha daqui ou para uma issue com label.
>
> `make commitments` mostra o que venceu. O CI reprova PR que abre um adiamento
> sem linha e PR novo sem `Pedido: C-AAAA-NNN`. Um job semanal abre uma issue com
> os vencidos e a fecha quando a lista zera.

## Regras

1. **Todo pedido e todo adiamento nascem aqui, no mesmo turno.** A fala do dono é
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

`tipo`: `pedido` (fala do dono) · `compromisso` (trabalho adiado) · `decisao`
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
C-2026-007
Pedido: C-2026-007
```

O PR novo cita `Pedido: C-2026-007` e a seção `## Compromissos` lista os adiamentos
que ele criou. Pedido que não virou trabalho também fica `ABERTO`, com
`revisar_em` curto: a linha é o que impede o esquecimento.

## Tabela

<!-- commitments:start -->
| id | tipo | origem | compromisso | dono | criado | revisar_em | gatilho | estado | prova |
|---|---|---|---|---|---|---|---|---|---|
| C-2026-001 | compromisso | #2298 / #2300 | B.I.: tempo corrido desde kitchen_released_at e tempo de preparo (Iniciar a Pronto) | Engenharia · B.I. | 2026-11-12 | 2026-11-26 | encomenda futura no ar | EM_EXECUCAO | #2300 |
| C-2026-002 | compromisso | #2298 / #2301 | Editar preorder_kitchen no Admin, hoje só JSON em Shop.defaults | Engenharia · Admin | 2026-11-12 | 2026-11-26 | #2298 na fila | EM_EXECUCAO | #2303 |
| C-2026-003 | compromisso | #2292 | Aviso antes de salvar o fechamento do dia (padrão de confirmação em dois passos) | Engenharia · Admin | 2026-11-12 | 2026-12-03 | padrão de confirmação existir no Admin | ABERTO | - |
| C-2026-004 | compromisso | #2292 | Horário especial que encurta o dia não é conferido contra os horários dos pedidos | Engenharia · Admin | 2026-11-12 | 2026-12-03 | - | ABERTO | - |
| C-2026-005 | decisao | #2069 | Aprovar ou recusar o modo compacto x padrão (KDS, PDV, Gestor, Receber) | Pablo | 2026-11-02 | 2026-11-14 | resposta do dono à prévia | ABERTO | - |
| C-2026-006 | achado | STATUS-CONSOLIDACAO-2026-11-10.md | Triar o que restou das 5 frentes sem dono (ADR-025 Doorman, ledger C11, ciclo C6, leitura paralela) | Coordenação | 2026-11-10 | 2026-11-19 | - | ABERTO | - |
| C-2026-007 | pedido | chat 2026-11-12 | Quero poder, SEMPRE que eu discutir algo, seja uma correção, ou um pedido de uma feature nova, NADA seja perdido, nunca mais! | Engenharia | 2026-11-12 | 2026-11-19 | - | EM_EXECUCAO | - |
| C-2026-008 | pedido | chat 2026-11-12 | o que mais me importo é com a SAÚDE do REPO! Está muito cansativo e desesperador manter esse desenvolvimento!!! Faça algo a respeito. | Engenharia | 2026-11-12 | 2026-11-19 | - | EM_EXECUCAO | - |
| C-2026-009 | compromisso | #2303 / #2304 | Preparo da encomenda no painel do produto do Catálogo (Gestor) | Engenharia · Catálogo | 2026-11-12 | 2026-12-03 | - | ABERTO | - |
<!-- commitments:end -->
