# EXCELÊNCIA-PDV: plano

> Brief: `docs/coordination/ROUNDS/EXCELENCIA-PDV.md` e `EXCELENCIA-base.md` (PR #2483).
> Compromisso: DEV-2026-028. Base medida: `main` em `d48286ec4`, 16/11/2026.
> Nenhum código de produção foi alterado. Capturas em
> `docs/coordination/EVIDENCE/EXCELENCIA-PDV/` (abaixo, `EV/`).

Abreviações de caminho: `FE/` = `surfaces/pos-nuxt/app/`; `OPS` =
`shopman/backstage/api/operations.py`; `BPOS` = `shopman/backstage/services/pos.py`;
`PPOS` = `shopman/backstage/projections/pos.py`; `SPOS` = `shopman/shop/services/pos.py`
(fronteira).

## 0. Como foi medido

- **Pilha isolada**: Django `:8050` (banco `shopman_exc_pdv`, `seed --flush`), PDV `:3152` e
  Cozinha `:3153` em build de produção, worker de directives ligado. Host próprio
  (`excpdv.localhost`), porque o cookie de sessão é por host e as revisões irmãs usam
  `127.0.0.1` no mesmo navegador.
- **Papéis**: Joyce (Gerente) iniciou o dispositivo e assinou com o próprio PIN; Fran
  (Caixa, só PIN) operou. Nunca o superusuário, nenhum atalho de API ou Admin para chegar a
  estado. O banco foi lido só para conferir o que a tela gravou.
- **Dois ajustes de ambiente, declarados**: a trava automática do terminal de teste passou de
  60 s para 900 s (`cashman_terminal.metadata.auto_lock_seconds`), e o pool de conexões foi
  ligado como no deploy. Nenhum dos dois muda regra de negócio.
- **O que foi percorrido pela tela, em 1366 px**: iniciar o dispositivo e vincular o posto;
  troca de operador por PIN (jornada 9); venda de balcão em dinheiro com troco (2); venda com
  desconto, maquininha e gerente (3); item feito na hora na comanda (4, parcial); encomenda
  para amanhã e para 26/11, com cliente, retirada, dia e horário, a pagar na retirada (5); aba
  Encomendas e "Receber e entregar" (6).
- **Lacunas, ditas com nome**: cancelar e estornar (7), sem conexão (8), fechar e abrir o
  caixa (10 e 1), a Tela do cliente, a Cozinha aberta pelo PDV e a passada em 375 px **não
  foram percorridos pela tela**. A máquina estava disputada pelas três revisões ao mesmo
  tempo, e o navegador da sessão ficou em segundo plano no fim (sem captura e com toques
  caindo fora do alvo). Para essas jornadas, os achados abaixo vêm de leitura de código, com
  `caminho:linha`, e estão marcados **[código]**. O roteiro de operador de cada uma está
  preso ao WP que a canoniza (seção 4); nenhum deles fecha sem a passada em 375 px.
- **Histórico**: os 22 PRs do laudo de 07/11 (#2209 a #2230) foram conferidos como mergeados e
  não foram reauditados (seção 8).

## 1. Laudo

Dois P0, onze P1, dezesseis P2. Cada achado traz a lente, a prova e a causa.

### P0

**P0-1. A autorização do gerente não fica presa ao que ele viu.** Lente: segurança.

- Prova pela tela: na venda `PDV-261116-U44` a Fran lançou desconto de R$ 6,00. O diálogo
  mostrou à Joyce "Desconto de R$ 6,00, acima de R$ 5,00" (`EV/p0-01-gerente-autoriza-6.jpg`)
  e ela assinou com o PIN. Na tela da maquininha a Fran tocou em "Voltar", reabriu o desconto,
  trocou para R$ 30,00, e o aviso "Esta venda precisa de um gerente" sumiu: o botão virou
  "Validar" (`EV/p0-02-desconto-30-sem-gerente.jpg`). A venda fechou em R$ 13,35
  (`EV/p0-03-venda-concluida-u44.jpg`). No banco: `manual_discount = {"value": 30.0,
  "discount_q": 3000, "approved_by": "joyce"}`. O registro diz que a Joyce aprovou um
  desconto que ela nunca viu.
- Causa: a tela guarda usuário e PIN do gerente no carrinho e os reenvia em todo fechamento
  (`FE/composables/usePosSale.ts:2332-2333`); só limpa ao zerar o carrinho, trocar de comanda
  ou receber recusa (`:2040-2041`, `:2123-2124`, `:3761-3762`). Com o PIN presente, o bloqueio
  desliga (`FE/components/PosPaymentWorkspace.vue:293-296`). O servidor confere só a
  credencial; o gesto e o valor vão para o log e não amarram nada (`SPOS:3503-3540`).
- Alcance: o mesmo PIN guardado serve para qualquer valor de desconto na mesma comanda.

**P0-2. A encomenda acima da fornada planejada é prometida sem lastro e sem aviso a ninguém.**
Lente: a promessa de produção.

- Prova pela tela: encomenda `PDV-261116-K16`, Maria Santos, retirada em 17/11 a partir das
  15h, 200 Baguette de Tradition, R$ 2.747,00 a receber na retirada. O pagamento mostrou só
  uma linha recolhida, "1 ressalva nos itens". Aberta, ela diz: "Baguette de Tradition: só 44
  em estoque. A venda de balcão vale; confira o estoque depois."
  (`EV/p0-promessa-01-ressalva-44-de-200.jpg`). A frase fala de balcão numa encomenda e chama
  de estoque o que é plano. A tela final manda: "CONFIRME COM O CLIENTE · Retirada · Amanhã, a
  partir das 15h" (`EV/p0-promessa-02-encomenda-registrada.jpg`).
- Prova no banco: o plano da baguette para 17/11 é de 22 unidades (`stockman_quant`). A
  reserva das 200 ficou sem fornada (`stockman_hold` 4: `quantity 200`, `quant_id` nulo). O
  pedido gravou `availability_decision: approved true, available_qty 200`. Nenhum alerta foi
  criado, e a cliente recebeu a confirmação com "200x Baguette de Tradition".
- Causa: no PDV a reserva é branda e o fechamento não tem portão de estoque
  (`shopman/shop/lifecycle.py:216-217`, `SPOS:409-427`); a encomenda para outra data registra
  demanda (`shopman/shop/services/stock.py:178-182`); a ressalva usa a frase do balcão
  (`SPOS:1371`) e a tela a mostra como nota terciária (`FE/components/PosPaymentWorkspace.vue:368`).
- Régua dupla: com saldo zero na data a grade bloqueia o item (P1-1); com saldo parcial,
  passa calado. A loja online recusa o mesmo caso.

### P1

**P1-1. Encomenda para além do plano de produção: a grade bloqueia todos os pães.** Lente:
promessa de produção, beco sem saída.

- Prova: com a data 26/11 (dez dias), Baguette de Tradition, Baguete Gergelim, Brioche Burger
  Bun, Campagne, Ciabatta e mais quinze itens da casa aparecem "Sem saldo para 26/11"; o toque
  responde "Baguette de Tradition: Sem saldo para 26/11." e mais nada
  (`EV/p1-encomenda-26-11-sem-saldo.jpg`). O pacote do mesmo brioche e o cappuccino seguem
  liberados. Medido: 35 de 122 produtos bloqueados em D+10, contra 15 hoje; o plano do seed
  termina em 23/11.
- Causa: `_pos_sold_out_on` trata "sem plano na data" como "esgotado" (`PPOS:3340-3355`,
  `packages/stockman/shopman/stockman/services/availability.py:337-339`); o motivo é montado
  na tela (`FE/presentation/catalog.ts:124-138`).

**P1-2. A grade não ouve o estoque, e o cabeçalho diz "Ao vivo".** Lente: contrato.
**[código]**

- O servidor publica `stock-update` (`shopman/shop/handlers/_sse_emitters.py:131-133`,
  `:677-686`). O PDV assina só caixa e comandas (`FE/composables/usePosEvents.ts:20-24`). Com
  o push vivo o poll de 60 s não roda (`FE/presentation/events.ts:24-26`), e o aviso de comanda
  relê só o quadro (`FE/components/PosOperatorShell.vue:87`). O selo "Esgotado" só muda quando
  o próprio balcão vende ou salva. O cabeçalho promete "Mudanças de outras estações chegam na
  hora" (`FE/presentation/events.ts:59`).

**P1-3. "Receber e entregar" é uma segunda tela de pagamento, sem as travas da primeira.**
Lente: UX, segurança. Apontado pelo dono em 16/11.

- Prova: na encomenda `PDV-261116-B13` (R$ 93,00) o diálogo aceitou R$ 9.000 recebidos,
  mostrou "Troco: R$ 8.907,00" em letra pequena e concluiu sem conferência
  (`EV/p1-troco-8907-na-retirada.jpg`). Não há Pix, cédulas, Exato nem dividir conta.
- Causa: `FE/components/PosPreorderHandOverDialog.vue` (144 linhas) e
  `FE/presentation/preorderActions.ts` (`COUNTER_METHODS`, linha 20) refazem forma e troco
  fora de `PosPaymentWorkspace`. O alerta de troco de R$ 200 ou mais (#2212) existe só na
  tela da venda; o servidor recusa apenas recebido menor que o total (`SPOS:4470`).

**P1-4. O PIN do gerente fica em claro no navegador.** Lente: segurança. **[código]**

- O corpo do fechamento, com `manager_approval`, é gravado no `localStorage` como guarda do
  fechamento incerto (`FE/composables/usePosSale.ts:416-423`, `:166-174`,
  `FE/utils/posIntent.ts:249`) e permanece em estouro de tempo ou 5xx. O mesmo corpo vai ao
  IndexedDB na venda sem conexão (`:3927-3929`) e viaja em `tabs/save` e `sale/review`. Com o
  PIN lido, a Caixa assina sangria.

**P1-5. Repetir um gesto de caixa aprovado troca a chave de idempotência.** Lente: contrato.
**[código]**

- A chave nasce de `caminho + JSON(corpo)` (`FE/composables/usePosCashSession.ts:98-103`); com
  a aprovação no corpo, a assinatura muda. O servidor já tira a aprovação da impressão digital
  (`OPS:5506`), então a chave poderia ser a mesma. Depois de um estouro de tempo, a sangria
  pode gravar duas vezes.

**P1-6. O gerente assina sem ver o valor em quatro gestos.** Lente: segurança. **[código]**

- Cancelar venda mostra só o número do pedido (`FE/components/PosCancelSaleDialog.vue:45-49`);
  cancelar encomenda (`FE/pages/preorders/[ref].vue:484-494`), devolução na edição de
  encomenda (`FE/pages/index.vue:2008-2019`) e fechar o caixa com vendas a conferir
  (`FE/pages/session/index.vue:454`) também não. Na venda, o diálogo convida a passar o
  crachá, mas a tela não escuta o evento (`FE/components/PosPaymentWorkspace.vue:2584-2596`).

**P1-7. A Caixa recebe números que a contagem cega esconde.** Lente: segurança, contrato.

- Prova: como Fran, `GET /api/v1/backstage/pos/` devolveu `shift: {"count": 11,
  "total_display": "882,95", ...}`; a tela só usa a contagem. A aba Encomendas mostra "A
  receber R$ 547,00" e "20 encomendas · R$ 4.241,00"
  (`EV/encomendas-lista-entregues-no-topo.jpg`).
- Causa: `PPOS:957`, `:977` (total do turno), `PPOS:3483-3524` (últimas vendas do canal
  inteiro), `shopman/backstage/projections/preorders.py:345`, `:366`.

**P1-8. A base de clientes é enumerável pela busca.** Lente: segurança. **[código]**

- A busca casa `ref__icontains` com dois caracteres
  (`packages/guestman/shopman/guestman/services/customer.py:178`, `PPOS:1238`), vai por GET com
  o termo na URL (`FE/composables/usePosSale.ts:3098-3101`, `OPS:6794-6795`) e não tem limite
  de taxa (`OPS:6790-6792`). O lookup entrega CPF, e-mail, telefone e endereços (`OPS:6760`).
  O erro da busca vira lista vazia, um falso "não existe" (`usePosSale.ts:3108-3110`). Parte já
  está em #2335 e #2336.

**P1-9. Erro de caixa chega cru ao balcão.** Lente: contrato. **[código]**

- `_falha_do_caixa` devolve `str(exc)` com 400 para qualquer exceção (`OPS:5454-5469`), em
  abrir, fechar, sangria, gaveta, troco, devolução, estorno e entrega. `sale/close` responde
  fora do dialeto `{detail, field, errors}` (`OPS:5682-5683`, #2347). A gaveta pós-venda engole
  o erro (`FE/composables/useDrawerOpening.ts:199-201`).

**P1-10. Encomenda de qualquer valor entra "Na retirada", sem cobrança e sem gerente.** Lente:
segurança. Decidido em D3: a opção some para encomenda de outro dia.

- Prova: os R$ 2.747,00 da K16 foram registrados com "Sem cobrança agora: recebe no balcão
  quando o cliente buscar" (`EV/encomenda-na-retirada-sem-sinal.jpg`), pela Caixa sozinha. Não
  há sinal. A regra da casa de 28/08 é "encomenda cobra antes".

**P1-11. A aba Encomendas abre com o que já foi entregue.** Lente: continuidade, omotenashi.

- Prova: em "Hoje", as dez primeiras linhas são "Entregue"; as nove a entregar, entre elas a
  única "Pronto", ficam abaixo da dobra (`EV/encomendas-lista-entregues-no-topo.jpg`). Todas
  mostram "A combinar" na coluna do horário.

### P2

| # | Achado | Lente | Prova e causa |
|---|---|---|---|
| P2-1 | O chip "Consumir aqui" do balcão é a porta da encomenda: um toque troca o modo e abre o cadastro de cliente; voltar pede confirmação. Quem quer "para levar" cai ali | copy | `EV/consumir-aqui-vira-encomenda.jpg`; `FE/pages/index.vue:616-730`, `FE/components/PosTabHeader.vue:388-394` |
| P2-2 | O tile mostra R$ 16,00 e a linha cobra R$ 13,60 (Semana do Pão). O operador lê o preço errado para o cliente | contrato | `EV/tile-16-linha-1360.jpg`; o tile só risca preço na Hora da Xepa (`FE/components/PosProductTile.vue`, `productStrikePrice`) |
| P2-3 | "Nova venda (F2)" volta ao quadro de comandas; Enter no campo vazio é mudo. Cada venda custa um toque a mais | UX | tela; `FE/components/PosSaleResult.vue`, `PosTabBoard.vue` |
| P2-4 | "Ao finalizar, o item vai para a cozinha." O ato é validar, e o vocabulário proíbe finalizar | copy | `FE/presentation/kitchen.ts:82`; também #2400 (`usePosSale.ts:3767`) |
| P2-5 | "Passe na maquininha" e, na linha de baixo, "Digite este valor no terminal" | copy | `FE/presentation/payment.ts:319` |
| P2-6 | "Tipo, valor e motivo. A loja confere e aplica." e "Cliente e data não definem como o pedido será recebido." são notas do engenheiro | copy | `FE/components/PosPaymentWorkspace.vue:2538`, `PosFulfillmentModal.vue:391` |
| P2-7 | A encomenda registrada oferece "Cancelar venda"; o aviso diz "1 encomenda está... e elas não entram" | copy | `FE/components/PosSaleResult.vue:379`, `FE/presentation/preorders.ts:449` |
| P2-8 | No assistente da encomenda cada etapa é um botão que abre um diálogo; o calendário não fecha ao escolher o dia; com "Outra data" sem data, os horários de hoje seguem na tela | UX | `EV/encomenda-recebimento-modal.jpg`; `FE/components/PosOrderEntry.vue`, `PosScheduleModal.vue`, `PosSchedulePicker.vue` |
| P2-9 | Tiles de produto, os dois botões de modo (Balcão, Encomendas) e as teclas do PIN não têm nome acessível | UX | leitura da árvore de acessibilidade; `PosProductTile.vue`, `PosTabHeader.vue`; o teclado do PIN é do kit (fronteira) |
| P2-10 | "Repetir último pedido" lança item esgotado | promessa | `usePosSale.ts:1718`, `:3204-3212` **[código]** |
| P2-11 | Fechar o caixa não olha comanda enviada à cozinha, troco pedido nem devolução pendente; o bloqueio por fila sem conexão é por navegador | segurança | `BPOS:780-836`, `usePosCashSession.ts:165-171`, `PPOS:2262` **[código]** |
| P2-12 | Conferir o PIN não grava nada e cinco erros bloqueiam o gerente: a Caixa consegue travar quem autoriza | segurança | `OPS:6875-6905`, `packages/doorman/shopman/doorman/conf.py:46` **[código]** |
| P2-13 | Atalhos e estação da cozinha gravam com `operate_pos`, lendo `terminal_ref` do corpo | segurança | `shopman/backstage/api/pos_settings.py` **[código]** |
| P2-14 | A trava de 60 s cai com o "Receber e entregar" aberto; na venda o pagamento a segura | continuidade | tela; `FE/composables/usePosAutoLock.ts` (`holdWhen`) |
| P2-15 | Quando a sessão é derrubada logo após o login, a tela volta ao login vazio, sem dizer por quê; a mensagem de tempo esgotado aparece três vezes | continuidade | `EV/login-tempo-esgotado.jpg`; gate de login do PDV |
| P2-16 | O contrato de superfície ainda diz "sem commit offline" e "polling"; a Tela do cliente usa canal global, sem estação | contrato | `docs/reference/backstage-pos-surface-contract.md:300-302`, `:380-381`; `FE/composables/useCustomerDisplay.ts:11`, `:19-21` **[código]** |

### O que o PDV já faz bem (não mexer)

- O servidor é dono do número: total recalculado e selado, `expected_total_q` obrigatório,
  turno e terminal vindos da estação.
- Ao lançar a baguette para amanhã às 9h, a tela avisa "Baguette de Tradition sai às 15:00" e
  oferece "Mudar para A partir das 15h" (`EV/bom-sai-as-15-mudar-horario.jpg`).
- O troco aparece grande, com "Total a cobrar" ao lado (`EV/troco-a-vista.jpg`).
- O fechamento que respondeu 504 foi reenviado com a mesma chave e concluiu sem duplicar.
- Sangria com duas assinaturas, fechamento cego, cancelar não é devolver.

## 2. O salto

1. **Promessa com lastro.** Cada linha de encomenda mostra a fornada da data ("Ter 17/11: 22
   planejadas, 6 livres") e a promessa em três estados: cabe, pede reforço à Produção, não dá.
   O reforço sai num toque e a resposta da Produção volta à comanda. Ganho: o balcão para de
   prometer no escuro. Nenhum dos seis concorrentes pesquisados liga a promessa a um plano de
   produção. Custo: alto (WP-E2, WP-E3 e a fronteira F2).
2. **Autorização que assina o que viu.** O gerente aprova um gesto, um valor e uma venda; mudou
   qualquer um, pede de novo. O relatório mostra o que cada assinatura cobriu. Ganho: fim do
   desvio por desconto. Toast pede o motivo depois; Saipos usa senha compartilhada. Custo:
   médio (WP-E1 e a fronteira F1).
3. **Venda de um fôlego.** "Nova venda" já cai na grade, com o que mais sai naquela hora
   primeiro; dinheiro exato numa tecla; cédulas sugeridas pelo total (26, 30, 50). Meta: três
   toques além dos itens, contra cinco hoje. Custo: médio (WP-E8).
4. **Fechamento que explica.** Ao fechar, a gerência vê a diferença com as causas prováveis:
   troco alto, venda em dinheiro cancelada sem devolução, saída sem comprovante, venda trocada
   de forma. Nenhum concorrente aponta a causa. Custo: médio (WP-E11).
5. **Grade viva de padaria.** O tile mostra as últimas unidades e "fica pronto às 15h" em
   tempo real, e o esgotado diz quando volta. Custo: médio (WP-E4, depois WP-E8).

## 3. WPs

Todo brief manda seguir "Teste como um operador de verdade" de `EXCELENCIA-base.md`, com Fran
(Caixa) e Joyce (Gerente), em 375 px e 1366 px, e ler `docs/reference/suite-vocabulary.md` §3
e `docs/reference/backstage-pos-surface-contract.md`.

### WP-E12. Chão das provas: harness ao vivo do PDV

- Objetivo: um comando sobe Django semeado, PDV e Cozinha, e entrega ao Playwright uma sessão
  de operador real (login da Gerente, vínculo do posto, PIN).
- Fecha: a lacuna de medição da seção 0. Dependências: nenhuma.
- Arquivos: `surfaces/pos-nuxt/tests/e2e-live/` (fixtures `operator.ts`, README),
  `playwright.live.config.ts`, `scripts/run_pos_e2e_live.sh`.
- Fora do escopo: qualquer jornada além da fumaça (entrar, vincular, trocar de operador).
- Pronto quando: (a) roteiro: Joyce entra com senha, vincula "PDV principal", trava, Fran entra
  com PIN e vê as comandas, em 375 e 1366, com capturas; (b) `npm run test:live` verde local e
  o spec `operador.live.spec.ts` no repositório.
- Muda tela: não. Tamanho: P.
- Brief: "Leia `surfaces/pos-nuxt/tests/e2e-live/README.md`, `scripts/run_storefront_e2e.sh` e
  `shopman/shop/management/commands/setup_operators.py`. Monte o harness ao vivo do PDV. A
  trava automática do terminal de teste fica em 900 s por configuração do harness. Não use o
  superusuário nem `force_login`. Aviso: em 16/11, numa máquina carregada, o Chromium sem cabeça ficou preso em
  'Entrando…' depois do login da Gerente; não foi diagnosticado, comece por aí."

### WP-E1. Autorização presa ao gesto e ao valor (P0)

- Objetivo: a tela pede o gerente de novo sempre que o que ele assinou mudar, e nunca guarda o
  PIN.
- Fecha: P0-1, P1-4. Dependências: WP-E12. A amarração no servidor é a fronteira F1.
- Arquivos: `FE/composables/usePosSale.ts`, `FE/components/PosPaymentWorkspace.vue`,
  `FE/utils/posIntent.ts`, `FE/utils/offlineSaleStore.ts`, testes de `tests/`.
- Fora do escopo: `OperatorManagerAuth` do kit, `SPOS`, os outros diálogos (WP-E6).
- Pronto quando: (a) roteiro: Fran lança desconto de R$ 6, Joyce assina, Fran volta da
  maquininha e troca para R$ 30; a tela pede a Joyce de novo mostrando R$ 30; o
  `localStorage` não contém PIN em nenhum momento; (b) vitest da regra e a jornada J3 em
  Playwright.
- Muda tela: sim, o diálogo reaparece (prévia local ao dono). Tamanho: M.
- Brief: "Leia P0-1 e P1-4 deste plano e `SPOS:3503-3540`. A aprovação passa a valer para um
  retrato (gesto, valor, comanda): qualquer mudança no desconto, nos itens ou na forma apaga a
  aprovação. O PIN não entra no carrinho, no guarda do fechamento, no IndexedDB, em
  `tabs/save` nem em `sale/review`; a retentativa pede a assinatura de novo."

### WP-E4. A grade ouve o estoque

- Objetivo: o selo de esgotado muda sem ninguém tocar, e o "Ao vivo" passa a ser verdade.
- Fecha: P1-2. Dependências: WP-E12.
- Arquivos: `FE/composables/usePosEvents.ts`, `FE/presentation/events.ts`,
  `FE/components/PosOperatorShell.vue`, `surfaces/pos-nuxt/server/routes/sse/`.
- Fora do escopo: permissão de canal no `ShopmanChannelManager` (fronteira F5), saldo numérico
  no tile (WP-E8).
- Pronto quando: (a) roteiro: dois dispositivos; Fran vende a última unidade num e o outro
  mostra "Esgotado" em até 5 s, sem toque; (b) vitest de `events.ts` e jornada J4.
- Muda tela: não. Tamanho: M.
- Brief: "Leia P1-2, ADR-016 e `shopman/shop/handlers/_sse_emitters.py`. Assine o canal de
  estoque do PDV pelo BFF e releia só a disponibilidade no evento."

### WP-E7. O que a Caixa não vê

- Objetivo: a projeção do PDV entrega à Caixa só o que a tela dela usa.
- Fecha: P1-7, P1-8 (lado do PDV), #2335, #2336. Dependências: nenhuma (D4 decidida: a Caixa não vê).
- Arquivos: `OPS` (POSView, busca e lookup de cliente), `PPOS` (resumo do turno e últimas
  vendas), `shopman/backstage/projections/preorders.py`, `FE/composables/usePosSale.ts` (só a
  chamada da busca), `shopman/backstage/api/throttles.py`.
- Fora do escopo: `guestman` (fronteira F4).
- Pronto quando: (a) roteiro: como Fran, a resposta de `/pos/` não traz total do dia e a aba
  Encomendas não mostra soma em dinheiro; como Joyce, mostra; a busca vai por POST e trava
  depois do limite; erro de busca diz "não consegui buscar"; (b) pytest por papel e jornada J9.
- Muda tela: sim, os totais somem para a Caixa (prévia). Tamanho: M.
- Brief: "Leia P1-7 e P1-8 e `docs/guides/rbac-personas.md`. Quem não tem `audit_shift` não
  recebe soma em dinheiro em nenhuma projeção do PDV."

### WP-E10. Aba Encomendas: a próxima ação no topo

- Objetivo: a lista abre com o que falta entregar, e o assistente pergunta sem diálogo no meio.
- Fecha: P1-11, P2-7 (segunda frase), P2-8. Dependências: WP-E12.
- Arquivos: `FE/pages/preorders/index.vue`, `FE/presentation/preorders.ts`,
  `FE/components/PosPreorderRow.vue`, `PosOrderEntry.vue`, `PosFulfillmentModal.vue`,
  `PosScheduleModal.vue`, `PosSchedulePicker.vue`.
- Fora do escopo: `pages/preorders/[ref].vue` (WP-E5).
- Pronto quando: (a) roteiro: Fran abre Encomendas e a primeira linha é a "Pronto, a receber";
  cria uma encomenda escolhendo Retirada e o dia no próprio cartão; (b) vitest de ordenação e
  jornada J5.
- Muda tela: sim (prévia). Tamanho: M.
- Brief: "Leia P1-11 e P2-8 e a rodada `T4-pdv-encomenda-assistente.md`. A ordem do fluxo
  (cliente, recebimento, quando, produtos) é decisão do dono e não muda."

### WP-E2. Promessa com lastro na encomenda (P0)

- Objetivo: a linha da encomenda mostra a fornada da data; o que passa do plano bloqueia o
  Validar e só o gerente libera, vendo os dois números. Encomenda de outro dia não oferece "Na
  retirada".
- Fecha: P0-2, P1-10. Dependências: WP-E1 (mesmo arquivo de pagamento). D1 e D3 decididas.
- Arquivos: `PPOS` (`build_pos_schedule` passa a devolver planejado e livre por SKU na data),
  `FE/types/pos.ts`, `FE/components/PosCartPanel.vue`, `FE/components/PosPaymentWorkspace.vue`,
  `FE/presentation/payment.ts`.
- Fora do escopo: a frase de `SPOS:1371` e o alerta à Produção (fronteira F2).
- Pronto quando: (a) roteiro: Fran pede 200 baguettes para amanhã; a linha diz "22 planejadas
  para ter 17/11"; Validar fica travado com "200 pedidas, 22 planejadas" e pede o gerente,
  que vê os dois números e assina; sem a assinatura a encomenda não fecha; a forma "Na
  retirada" não aparece para outro dia; (b) pytest da projeção e J5.
- Muda tela: sim (prévia). Tamanho: G.
- Brief: "Leia P0-2, ADR-040, `shopman/shop/services/stock.py:170-190` e
  `shopman/shop/tests/test_pos_encomenda_reserva_na_data.py`. O PDV não decide estoque: mostra
  o lastro que o servidor apura. Regras do dono (D-041): acima do plano bloqueia e só o gerente
  libera; encomenda de outro dia não tem 'Na retirada'. A liberação usa a autorização presa ao
  gesto e ao valor do WP-E1."

### WP-E6. Gesto de caixa sem brecha

- Objetivo: todo gesto de dinheiro tem chave estável, valor na frente do gerente e erro que o
  operador entende.
- Fecha: P1-5, P1-6 (venda, devolução, fechamento), P1-9, P2-12, P2-13, #2347.
  Dependências: WP-E7 (mesmo `OPS`).
- Arquivos: `FE/composables/usePosCashSession.ts`, `FE/components/PosCancelSaleDialog.vue`,
  `FE/pages/session/index.vue`, `FE/pages/index.vue` (só o diálogo de devolução), `OPS`
  (`_falha_do_caixa`, `sale/close`), `shopman/backstage/api/pos_settings.py`.
- Fora do escopo: `pages/preorders/[ref].vue` (WP-E5), o kit.
- Pronto quando: (a) roteiro: Fran pede saída de R$ 50, Joyce vê "Saída de R$ 50,00" e assina;
  com a rede cortada no meio, repetir grava uma vez só; cancelar venda mostra o valor; (b)
  pytest do dialeto de erro, vitest da chave e jornada J7.
- Muda tela: sim, os diálogos ganham o valor (prévia). Tamanho: M.
- Brief: "Leia P1-5, P1-6 e P1-9 e `docs/reference/errors.md`. A chave do gesto ignora a
  aprovação, como o servidor já faz em `OPS:5506`."

### WP-E3. Encomenda além do plano

- Objetivo: data ainda sem fornada planejada não vira "Sem saldo"; vira pedido à Produção, dito
  assim.
- Fecha: P1-1, P2-10. Dependências: WP-E2. D2 decidida: libera como pedido à Produção.
- Arquivos: `PPOS` (`_pos_sold_out_on`, `_sold_out_skus`), `FE/presentation/catalog.ts`,
  `FE/components/PosProductTile.vue`, `FE/composables/usePosSale.ts` (só `addProduct`).
- Fora do escopo: a antecedência por produto no servidor (fronteira F2).
- Pronto quando: (a) roteiro: Fran abre encomenda para daqui a dez dias, lança 30 croissants e a
  linha diz "Ainda sem fornada planejada para 26/11: vira pedido à Produção"; "repetir último
  pedido" não lança item esgotado de hoje; (b) pytest das duas réguas e J5.
- Muda tela: sim (prévia). Tamanho: M.
- Brief: "Leia P1-1 e `packages/stockman/shopman/stockman/services/availability.py:325-345`.
  Separe 'plano esgotado' de 'sem plano'. Não mexa no stockman."

### WP-E5. Receber o saldo pelo Pagamento

- Objetivo: "Receber e entregar" abre a mesma tela de Pagamento, em modo "receber o saldo"; o
  diálogo próprio morre.
- Fecha: P1-3, P1-6 (cancelar encomenda), P2-14. Dependências: WP-E2.
- Arquivos: `FE/pages/preorders/[ref].vue`, `FE/components/PosPreorderHandOverDialog.vue`
  (remoção), `FE/presentation/preorderActions.ts`, `FE/components/PosPaymentWorkspace.vue`,
  `FE/composables/usePosPreorderActions.ts`.
- Fora do escopo: `operator_orders.hand_over_at_counter` (fronteira; o endpoint não muda).
- Pronto quando: (a) roteiro: Fran abre a encomenda pronta, toca em "Receber R$ 93,00 e
  entregar", paga por Pix ou com R$ 100 e vê o troco grande; R$ 9.000 pede conferência; a Tela
  do cliente acompanha; (b) vitest, remoção sem resíduo e jornada J6.
- Muda tela: sim (prévia). Tamanho: G.
- Brief: "Leia P1-3 e a regra do dono de 16/11: gesto de dinheiro tem uma tela só. Nenhuma
  forma, troco ou alerta é reimplementado fora de `PosPaymentWorkspace`."

### WP-E11. Fechar e abrir o caixa

- Objetivo: o fechamento confere o que ficou pendurado e a gerência lê a diferença com a causa
  provável.
- Fecha: P2-11, o item 16 do histórico (veredito de tolerância). Dependências: WP-E6.
- Arquivos: `BPOS` (fechamento), `shopman/backstage/projections/closing.py`,
  `cash_session.py`, `FE/pages/session/closing.vue`, `FE/composables/useDayClosing.ts`.
- Fora do escopo: `packages/cashman`.
- Pronto quando: (a) roteiro: Joyce fecha com uma comanda enviada à cozinha em aberto e a tela
  nomeia a comanda; conta cédula por cédula; vê a diferença e as causas; Fran abre o caixa
  seguinte; (b) pytest do fechamento e jornadas J10 e J1.
- Muda tela: sim (prévia). Tamanho: M.
- Brief: "Leia P2-11, a decisão D-004 (contagem cega) e `docs/coordination/ROUNDS/V4-PDV-pdv.md`.
  A Caixa continua sem ver o esperado."

### WP-E8. Venda de um fôlego

- Objetivo: três toques além dos itens na venda em dinheiro.
- Fecha: P2-2, P2-3. Dependências: WP-E3 (mesmo tile). D5 decidida: cai direto na grade.
- Arquivos: `FE/components/PosSaleResult.vue`, `PosTabBoard.vue`, `PosProductGrid.vue`,
  `PosProductTile.vue`, `FE/presentation/payment.ts` (cédulas sugeridas), `PPOS` (ordem da
  grade).
- Pronto quando: (a) roteiro cronometrado: baguette e café em dinheiro com R$ 50, da venda
  concluída anterior até o troco, em 375 e 1366; (b) vitest e jornada J2.
- Muda tela: sim (prévia). Tamanho: M.
- Brief: "Leia P2-2, P2-3 e o salto 3. Meça os toques antes e depois e ponha os dois números no
  PR."

### WP-E9. Varredura final de copy e acessibilidade

- Objetivo: nenhuma frase do PDV com os oito defeitos, e todo controle com nome.
- Fecha: P2-1, P2-4 a P2-7, P2-9, P2-15, P2-16, #2400. Dependências: todos os anteriores.
- Arquivos: `FE/presentation/kitchen.ts`, `payment.ts`, `FE/components/PosTabHeader.vue`,
  `PosSaleResult.vue`, `PosPaymentWorkspace.vue`, `docs/reference/backstage-pos-surface-contract.md`.
- Pronto quando: (a) roteiro: leitura das dez jornadas em voz alta, com capturas; (b) guardas de
  vocabulário e a sonda `copy-overflow.live.spec.ts` verdes.
- Muda tela: sim (prévia). Tamanho: M.
- Brief: "Leia `docs/reference/omotenashi-copy.md` e a tabela P2 deste plano."

## 4. Jornadas a canonizar

Todas em `surfaces/pos-nuxt/tests/e2e-live/`, contra o Django da pilha.

| Jornada | Papel | Passos | WP dono |
|---|---|---|---|
| J0 Entrar | Gerente, depois Caixa | senha, vínculo do posto, trava, PIN | WP-E12 |
| J1 Abrir o caixa | Caixa | fundo de troco, primeira venda | WP-E11 |
| J2 Balcão em dinheiro | Caixa | dois itens, R$ 50, troco, próxima venda | WP-E8 |
| J3 Desconto com gerente | Caixa e Gerente | desconto, assinatura, mudança de valor, nova assinatura | WP-E1 |
| J4 Fornada sem saldo e feito na hora | Caixa, dois dispositivos | última unidade, selo ao vivo, café na Cozinha | WP-E4 |
| J5 Encomenda de outro dia | Caixa | cliente, retirada, dia, horário, acima do plano, pagamento | WP-E2 (WP-E3 e WP-E10 estendem) |
| J6 Receber e entregar | Caixa | encomenda pronta, saldo, troco, Tela do cliente | WP-E5 |
| J7 Cancelar e estornar | Caixa e Gerente | cancelar pela lista, valor na assinatura, devolução | WP-E6 |
| J9 Troca de operador e trava | Caixa e Gerente | trava por ociosidade, troca, o que cada um vê | WP-E7 |
| J10 Fechar o caixa | Gerente | pendurados, contagem, diferença | WP-E11 |

J8 (sem conexão) segue nos specs que já existem; a chave nasce desligada por decisão de 03/11.

## 5. Ondas

Dois WPs da mesma onda nunca tocam o mesmo arquivo.

- **Onda 0**: WP-E12.
- **Onda 1**: WP-E1, WP-E4, WP-E7, WP-E10.
- **Onda 2**: WP-E2, WP-E6.
- **Onda 3**: WP-E3, WP-E5, WP-E11.
- **Onda 4**: WP-E8.
- **Onda 5**: WP-E9.

## 6. Decisões do dono

Respondidas em 16/11/2026 e registradas como D-041 em `docs/coordination/DECISIONS.md`.

- **D1. Encomenda acima da fornada planejada da data.** Bloqueia acima do plano e só o gerente
  libera (opção 2). Vale para WP-E2.
- **D2. Encomenda para data ainda sem plano de produção.** Sim: entra no PDV como pedido à
  Produção. Vale para WP-E3.
- **D3. Encomenda de outro dia "a pagar na retirada", sem sinal.** A opção some (opção 2; "KISS").
  Vale para WP-E2.
- **D4. A Caixa vê o faturamento do dia e as somas de encomendas?** Não. O dono lembrou que a
  contagem do fechamento é cega: a resposta já estava dada e a pergunta não devia ter sido
  feita. Vale para WP-E7.
- **D5. "Nova venda" cai direto na grade da próxima comanda livre?** Sim. Vale para WP-E8.

## 7. Fronteiras

Registradas, não mexidas. Cada uma tem issue `ficou-de-fora` aberta pelo PR #2557: F1 #2558,
F2 #2559, F3 #2560, F4 #2561, F5 #2562, F6 #2563, F7 #2564, F8 #2565. A lacuna de medição da
seção 0 é a #2566.

| # | O que é | Por que afeta o PDV | De quem é | Quem mais sente |
|---|---|---|---|---|
| F1 | `validate_manager_override` confere só a credencial; a aprovação não é amarrada a gesto, valor e venda (`SPOS:3503-3540`). O diálogo `OperatorManagerAuth` não obriga o valor | o P0-1 só fecha de verdade no servidor | `shopman/shop`, `operator-kit` | Gestor, Cozinha, Produção, Compras |
| F2 | Encomenda acima do plano registra demanda sem alerta e grava `available_qty` igual ao pedido; a frase da ressalva é de balcão (`shopman/shop/services/stock.py:178-182`, `SPOS:1371`); a Produção precisa ver a demanda sem fornada | o P0-2 e o P1-1 dependem disso | `shopman/shop`, Produção | Storefront, Gestor |
| F3 | "sai às HH:MM" é hora declarada ou mediana de 30 dias, não a fornada de hoje, e a janela não tem capacidade (`shopman/shop/services/product_readiness.py:124-167`). A regra de copy de 16/11 pede "fica pronto" | a promessa de horário do PDV herda a imprecisão | `shopman/shop` | Storefront, Gestor |
| F4 | A busca de clientes casa `ref__icontains` (`packages/guestman/.../services/customer.py:178`) | P1-8 | `packages/guestman` | Gestor, Marketing |
| F5 | Permissão do canal de estoque no `ShopmanChannelManager` | WP-E4 | `shopman/shop` | Storefront, Cozinha |
| F6 | Teclado do PIN sem nome acessível; menu do operador sem "Trocar operador"; PIN de quatro dígitos não envia sozinho | P2-9 e a troca de operador | `operator-kit` | os oito apps |
| F7 | Venda sem conexão: o despacho à Cozinha não distingue venda guardada (`shopman/shop/services/kds.py:108-112`), e o alerta de falta nomeia a venda de balcão em vez do pedido remoto que vai faltar (`stock.py:1106-1116`) | vale quando a chave for ligada | `shopman/shop`, Cozinha | Gestor |
| F8 | `sale/close` aceita venda sem `client_request_id` (`shopman/shop/services/pos_intent.py:772-775`) | idempotência do fechamento | `shopman/shop` | nenhum |

## 8. Histórico conferido e benchmarks

**Histórico.** Não reauditado: os 22 PRs de #2209 a #2230 (laudo de 07/11) e os achados F01,
F02, F06, F08, F09 e F10 do plano de 10/09, que caíram no código. Decisões que restringem este
plano: sangria pede gerente em qualquer valor (12/08); gerente sempre da lista, uma autorização
só (28/10); fechar o caixa é da gerência e a contagem é cega (D-004); uma gaveta, vários
dispositivos (D-007); total esperado obrigatório (D42); venda sem conexão nasce desligada
(03/11); aniversário uma vez por ano e busca com contato mascarado (07/11); no balcão o balcão
vence (25/09); a casa dita o fluxo da encomenda (16/09); trava por ociosidade do dispositivo
(17/09).

**Benchmarks** (documentação oficial, 16/11/2026). O que os melhores fazem melhor: quantidade
no botão com bloqueio em zero (Toast); volta automática do esgotado com hora marcada (Square,
Lightspeed); dinheiro exato num toque e troco sugerido (Toast); contagem cega e completa como
permissões distintas, com teto de diferença (Toast); aprovação exigida resolvida por PIN no
mesmo dispositivo (Shopify); motivo obrigatório em todo movimento de gaveta (Shopify, Toast);
troca de operador automática após a venda (Toast); pedido agendado que dispara à cozinha em
horário menos preparo (Toast). O que nenhum faz: promessa de horário derivada de um plano de
fornada; venda contra produção futura planejada; reconciliar a promessa feita sem conexão;
aprovação com valor e motivo no mesmo gesto; fechamento que aponta a causa da diferença. As
fontes estão no corpo do PR.
