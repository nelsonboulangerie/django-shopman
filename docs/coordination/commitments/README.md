# Compromissos: o que o repo deve, com dono, prazo e prova

> **Isto não é um plano.** É o registro de tudo que o dono pediu, o time adiou,
> alguém achou ou uma decisão deixou em aberto, e que ainda não está no `main` com
> prova. Se um PR diz "ficou de fora", o item é uma issue com label `ficou-de-fora`,
> e a entrada daqui é o índice com dono, prazo e prova.
>
> `make commitments` mostra o que venceu. O CI reprova PR novo sem
> `Compromisso: DEV-AAAA-NNN`; o adiamento tem o gate próprio `Ficou de fora declarado`.
> Um job semanal abre uma issue com os vencidos e a fecha quando a lista zera.

## Um arquivo por entrada

Cada entrada é um arquivo `DEV-AAAA-NNN.json` nesta pasta, com exatamente as dez
colunas de antes (`id`, `tipo`, `origem`, `compromisso`, `dono`, `criado`,
`revisar_em`, `gatilho`, `estado`, `prova`), todas texto. O nome do arquivo é o ID.

Por quê: até 18/11/2026 o ledger era uma tabela única em
[`COMMITMENTS.md`](../COMMITMENTS.md), e todo PR escrevia a sua linha no mesmo
lugar. Com vinte PRs em voo, cada merge deixava os seguintes CONFLICTING, a fila os
derrubava e eles esperavam a CI inteira de novo (#2556, #2622, #2623, #2627, #2629,
#2651, #2668, #2670, no mesmo dia). Com um arquivo por ID, dois PRs nunca tocam o
mesmo arquivo.

**Não existe índice commitado.** Um arquivo que todo PR atualiza é o mesmo conflito
de volta. A tabela legível sai na hora:

```bash
make commitments-index
```

Mudar o estado de uma entrada (`FEITO`, `DESCARTADO`...) é editar o arquivo dela, no
PR que faz o trabalho.

## Regras

1. **Toda solicitação e todo adiamento nascem aqui, no mesmo turno.** A fala do dono é
   registrada antes do primeiro edit; o adiamento, no mesmo PR que o criou. Nada
   de "fica para depois" só no corpo do PR.
2. **Toda entrada tem dono nomeado.** "Ninguém", vazio, "a definir" e "TBD" não valem.
   `Coordenação` é um papel ativo: se ninguém assume a esteira no turno, o item é
   `BLOQUEADO`, não `ABERTO`.
3. **Toda entrada aberta tem `revisar_em`.** A data é a trava: sem ela, o item não
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

O comando cria o arquivo e devolve o ID e a linha pronta para o PR:

```
DEV-2026-007
Compromisso: DEV-2026-007
```

O ID novo pula os que já estão em voo: os arquivos e as linhas da tabela congelada
em cada PR aberto (via `gh`), em cada branch local e em cada worktree deste clone.
Sem `gh` ou sem rede, o intake **falha** em vez de chutar (foi assim que dois PRs
nasceram com o mesmo DEV-2026-051). Quem precisa seguir offline, sabendo do risco,
usa `make intake q="..." offline=1`.

O PR novo cita `Compromisso: DEV-2026-007` e a seção `## Ficou de fora` lista os
adiamentos que ele criou. Solicitação que não virou trabalho também fica `ABERTO`,
com `revisar_em` curto: a entrada é o que impede o esquecimento.
