# Auditoria profunda — Payman

> Série "um app por vez", nº 2 · 2026-08-18 · Base: leitura integral do código (main, pós #215)
> Escopo lido: os ~4.400 loc do pacote (models, service completo, protocols, api, admin, 10 arquivos de teste), mais a fronteira — `shop/services/payment.py` (1.196 loc: initiate, `settle_terminal_tenders`, timeout com checagem no gateway, `cancel_stale_intents`), `pix_confirmation.py`, `webhook_idempotency.py`, `webhooks/efi.py`, adapter Efí, comando `reconcile_payments`, e a `financial_reconciliation` do backstage.

---

## Veredito em uma frase

O Payman é um núcleo de máquina de estados exemplar cercado por uma orquestração mais endurecida do que eu esperava — e os problemas reais são quatro: **sinais disparados dentro da transação** (uma armadilha armada para o primeiro consumidor), **chargeback como vocabulário morto que os relatórios fingem medir**, uma **API de pacote não montada e insegura se algum dia for**, e um punhado de assimetrias de auditoria (motivo do refund evapora; refund em dinheiro sem idempotência). Nada pede demolição; tudo pede fechamento de contrato.

---

## Parte I — O que está certo (e o que está *acima* do padrão)

**1. A máquina de estados existe em três camadas que concordam.** `TRANSITIONS` como dado; `save()` valida qualquer mudança de status contra ela (com carimbo automático de timestamp por status); `transition_status()` re-lê sob `select_for_update` para o caso concorrente; e **todo verbo do service** abre com `_get_for_update`. Testes de concorrência dedicados (`test_concurrent_capture`, `test_concurrent_refund_and_capture`). É o rigor que pedi ao Cashman no F1 da auditoria anterior — aqui já está feito.

**2. A verdade financeira é soma, não status.** `REFUNDED` significa "existe ao menos um reembolso"; quem responde "quanto voltou" é `refunded_total` (Σ das transações imutáveis). O status é índice, o livro é prova — coerente com a doutrina da suite, e documentado como contrato explícito no docstring.

**3. Idempotência de criação acima do padrão de mercado.** `create_intent` com chave não apenas devolve o existente: `_require_idempotent_match` **compara os cinco parâmetros** e recusa reuso da chave com outro pagamento (`idempotency_key_conflict`). A maioria das implementações devolve o existente em silêncio e mascara o bug do chamador. Constraint parcial única no banco cobre a corrida do create.

**4. `settle` é a decisão certa com a justificativa escrita.** "Só existe uma forma de capturar dinheiro, e um seam plugável sem duas implementações reais é dívida" — recusa de abstração especulativa, raro. E `asserted_at_terminal` é design fino: pix/cartão atestados no balcão (QR estático, maquininha avulsa em venda mista) ficam **marcados** no `gateway_data` para a reconciliação distinguir "capturado pelo gateway" de "atestado por gente". A porta é estreita e explícita.

**5. Reconciliação cumulativa com deriva bidirecional.** `reconcile_gateway_status` aplica *snapshots* (não deltas), com guardas de monotonicidade nos dois sentidos: refund do gateway menor que o local → erro; captura reportada para intent morto local → erro; moeda/valor/gateway_id divergentes → erro. Refund idempotente por `gateway_id` (at-least-once seguro). `_normalize_gateway_status` traduz o dialeto PT da Efí e o do Stripe num mapa só.

**6. A fronteira é mais madura do que o relatório geral supôs.** Três coisas que eu esperava encontrar faltando, existem: (a) o **timeout de Pix consulta o gateway antes de cancelar** — webhook perdido não vira perda do cliente — e promove `on_paid` sob lock com re-check de `captured_at` contra resolvers concorrentes; (b) **dedupe durável de webhook** na tabela `IdempotencyKey` (mesma durabilidade do checkout), com claim/replay/in-progress; (c) `cancel_stale_intents` mata os pendentes quando um intent vence. E o docstring do webhook Efí é um pequeno tratado de honestidade operacional: admite que sem proxy mTLS na DO o token na URL é a *única* autenticação, exige o strip da query no Sentry como mitigação obrigatória, e trata o segredo como "vazado por design" com doutrina de rotação. Isso é postura de segurança adulta.

---

## Parte II — Falhas e brechas (por severidade)

### P1 · ALTA — Todos os sinais disparam DENTRO da transação atômica

Cada verbo (`settle`, `authorize`, `capture`, `refund`, `cancel`, `fail`, e os quatro pontos do `reconcile`) faz `signal.send(...)` **dentro** do `@transaction.atomic`. O Cashman — pacote irmão, mais novo — usa `transaction.on_commit` em todos os anúncios. A diferença não é estilo:

- **Efeito fantasma sob rollback.** Cenário concreto já existente no código: `_settle_pos_sale` abre um atomic externo, chama `settle_terminal_tenders` (que dispara `payment_captured`) e depois `_record_sale`; se `_record_sale` levantar, **tudo reverte — menos o que o receiver já fez** com a notícia de um dinheiro que, para o banco, nunca existiu.
- **Receiver derruba o pagamento.** Exceção num receiver aborta a transação da captura — o rabo abana o cachorro.
- **Estado não-commitado visível.** Um receiver que consulte por fora (outra conexão) não vê o que o sinal afirma.

Hoje isso é *latente* — verifiquei: **nenhum receiver de sinal do Payman existe no repositório** (o fluxo pago é despachado explicitamente por `pix_confirmation`/webhook). Mas o docstring do pacote *anuncia* `@receiver(payment_captured)` como ponto de extensão: a armadilha está armada exatamente para o primeiro que aceitar o convite — provavelmente o BI incremental ou o Broadcast. **Correção mecânica:** envolver todos os `send` em `on_commit`, como o irmão já faz. Pré-alpha: custo zero de compatibilidade.

### P2 · ALTA — Chargeback é capacidade fantasma, e os relatórios fingem que ela existe

`PaymentTransaction.Type.CHARGEBACK` está no modelo, tem badge vermelho no admin, e a `financial_reconciliation` diária **soma `chargeback_q` e o desconta do `net_q`**. Só que nada no repositório é capaz de criar uma transação desse tipo: não há verbo no service, e o `reconcile_gateway_status` — o único caminho por onde um chargeback real entraria — **não tem parâmetro para expressá-lo** (o snapshot conhece `captured_q` e `refunded_q`, ponto). Para cartão via Stripe, chargeback é certeza estatística; para Pix existe o MED (devolução especial via banco). Quando o primeiro acontecer, o gateway vai reportar e o snapshot não terá onde pôr — provavelmente cairá como `refunded_q` (mentindo a natureza) ou como drift error (travando a reconciliação do intent).

O estado atual é pior que qualquer uma das duas saídas honestas: o relatório diário exibe um zero que se lê como "não houve chargebacks" quando significa "não enxergamos chargebacks". **Decidir:** ou o snapshot ganha `chargeback_q` com a mesma lógica de delta cumulativo do refund (e um issue-code próprio na reconciliação), ou o tipo sai do modelo até existir — vocabulário morto em modelo financeiro é passivo, não reserva.

> **✅ FECHADO (19/08/2026).** Escolhida a primeira saída, em duas metades. A
> primeira deu ao `reconcile_gateway_status` o parâmetro `chargeback_q`
> (snapshot cumulativo, monotônico, consumindo saldo devolvível) e o issue-code
> `intent_has_chargeback` na reconciliação diária. A segunda ligou o gateway ao
> modelo — abaixo o que foi decidido nela, que é semântica de dinheiro e não
> deve ser redescoberto.
>
> **Cartão (Stripe) — automático.** `shopman/shop/adapters/payment_stripe.py::handle_dispute_event`
> escuta os cinco `charge.dispute.*` e traduz o **desfecho** para o snapshot:
>
> | `Dispute.status` | O que aconteceu com o dinheiro | Vira chargeback? |
> |---|---|---|
> | `warning_needs_response`, `warning_under_review`, `warning_closed` | Consulta do emissor; nada se move | Não |
> | `needs_response`, `under_review` | Retirado, **mas reversível** (`funds_reinstated` devolve se ganharmos) | Não (fica como risco) |
> | `won`, `prevented` | Devolvido / nunca retirado | Não |
> | `lost` | Saiu e não volta | **Sim** |
>
> A `PaymentTransaction(CHARGEBACK)` nasce só em `lost`, e a razão é o formato
> do livro: a transação é imutável e o snapshot é monotônico, logo chargeback
> lançado não tem como ser desfeito — lançar na abertura da disputa deixaria a
> loja permanentemente mais pobre no livro toda vez que ela **ganhasse**.
> Enquanto a disputa vive, o valor em risco fica em
> `gateway_data["disputes"]` (contexto, reversível) e o operador é chamado pelo
> alerta novo `payment_disputed`, porque a defesa tem prazo. Entrega
> at-least-once e fora de ordem: estado por id de disputa, status terminal
> grudento, valor cumulativo das perdidas.
>
> **Pix (Efí) — segue manual, e agora está escrito por quê.** A lista
> documentada de eventos do webhook da Efí (`dev.efipay.com.br`, lida em
> 19/08/2026) tem `PIX_RECEBIDO`, `PIX_ENVIADO`, `DEVOLUCAO_RECEBIDA`,
> `DEVOLUCAO_ENVIADA` e os estados do Pix Automático — **nenhum evento de MED
> nem de relato de infração** —, e a API de gestão de Pix só expõe a devolução
> que *nós* pedimos (`PUT/GET /v2/pix/:e2eid/devolucao/:id`). Não há caminho
> automático a implementar: o MED chega ao operador pelo painel/e-mail da Efí e
> entra pelo mesmo `reconcile_gateway_status(chargeback_q=…)`. Isso está no
> docstring de `shopman/shop/webhooks/efi.py`, que é onde a próxima pessoa vai
> procurar. Se a Efí publicar o evento, o destino já existe — o Payman não
> precisa de nada novo.
>
> **O que ainda depende do dono:** ninguém provou o caminho contra o Stripe
> real. O roteiro de sandbox existe e é curto — cobrar com o cartão de teste
> `4000000000000259` (nasce contestado como fraude), responder à disputa com
> `losing_evidence` em `uncategorized_text` para forçar o `lost`, e conferir que
> o chargeback apareceu no Payman e no relatório do dia; `winning_evidence`
> fecha como `won` e não pode criar transação nenhuma. Isso é o que separa
> "provado contra mock" de "provado" — mesma dívida do
> `make smoke-gateways-sandbox`.

### P3 · MÉDIA-ALTA — A API do pacote não está montada — e não pode ser montada como está

O `config/urls.py` confirma: as APIs dos cores (incluindo `payman/api/`) **não são montadas no deployment**. São 130 loc de views + serializers + urls mortos em produção. Pior: se alguém montar, a proteção é `IsAuthenticated` puro — **qualquer usuário logado lista todos os intents da loja e filtra por qualquer `order_ref`**, dados de pagamento de qualquer cliente. Não há checagem de operador nem de dono do pedido. Pré-alpha, duas saídas limpas: apagar o pacote `api/` (a superfície real é o backstage, que já expõe o que o operador precisa), ou mantê-lo com permissão de modelo (`payman.view_paymentintent`) + escopo. O meio-termo atual — código de superfície pública sem trava esperando ser plugado — é a definição de brecha em potencial.

### P4 · MÉDIA — `get_active_intent` promete um e o mundo agora tem vários (e "ativo" inclui capturado)

Dois problemas no mesmo helper do contrato público:

1. **"Não-terminal" ≠ "ativo".** `TERMINAL_STATUSES = {failed, cancelled, refunded}` — logo um intent **CAPTURED é devolvido como "ativo"**. Para a pergunta que o nome sugere ("qual cobrança está em andamento?"), capturado não é resposta.
2. **Venda mista quebrou a cardinalidade.** `settle_terminal_tenders` cria, por design, **um intent por método** no mesmo pedido. Dinheiro capturado + pix pendente coexistem; o helper devolve "o mais recente por created_at" — arbitrário.

Mitigante encontrado: o único consumidor real é a `ActiveIntentView` da API não-montada (P3); o orquestrador usa seu próprio `_existing_active_intent`, que filtra por método e valor. Ou seja: hoje ninguém se machuca — mas o helper está na lista dos "6 verbos + 2 queries + 1 helper" do docstring de capa, é o que um dev novo vai alcançar primeiro, e seu contrato está errado duas vezes. Corrigir a semântica (excluir capturado; aceitar `method=` opcional; ou devolver lista) ou removê-lo junto com a API.

### P5 · MÉDIA — O motivo do reembolso evapora

`refund(ref, reason="item danificado")` — o `reason` vai **para o log e para lugar nenhum**. A transação não tem campo, o `gateway_data` não é tocado. Contraste interno: `cancel_reason` tem coluna própria e **seis testes dedicados** (`test_cancel_reason_*`). A assimetria é exatamente invertida em relação ao risco: cancelamento é dinheiro que não entrou; reembolso é dinheiro que *saiu* — a operação sobre a qual auditoria e contador perguntam "por quê", e a resposta hoje mora num log com retenção de infra. Barato: persistir em `gateway_data` do intent (`{"refunds": [{txn_id, reason}]}`) ou coluna `reason` na transação.

### P6 · MÉDIA — Reembolso sem gateway não tem idempotência

A dedupe do `refund` é por `gateway_id` — que reembolso de **dinheiro** não tem (`gateway_id=""` sempre). Dois disparos do mesmo estorno de balcão (retry de rede, duplo clique que escape do guard de UI) criam **duas** transações de refund enquanto `available_q > 0`, sem nada no pacote que recuse. Hoje o chamador real (`cancel_recent_order` do PDV) é protegido pela idempotência do cancelamento do pedido — mas o contrato do pacote permite o dobro, e a casa tem jurisprudência contra "contrato que só o chamador cobra". Espelhar o `create_intent`: parâmetro `idempotency_key` no `refund`, com a mesma verificação de match.

### P7 · BAIXA — Micro-brecha na chave de settle quando o valor deriva

`idempotency_key = f"order-payment:{ref}:{method}:{amount}:terminal"` — o valor participa da chave. Se entre duas tentativas o total reconciliado do pedido mudar (janela exótica: falha parcial + reedição), a chave muda e nasce um **segundo intent capturado do mesmo método no mesmo pedido** — receita dobrada no Payman com uma gaveta só. A `financial_reconciliation` acusaria (captured > order gross), então há rede; registrar como decisão consciente ou tirar o amount da chave e deixar o `_require_idempotent_match` acusar o conflito, que é para isso que ele existe.

### P8 · BAIXA — Tema da suite: pacotes anunciam, ninguém escuta

Como no Cashman: cinco sinais publicados com docstring de manual, **zero receivers** no repositório — o fluxo real é sempre chamada direta do orquestrador. Dois pacotes irmãos, dois idiomas de emissão (on_commit vs in-transaction), nenhum consumidor: a suite precisa escolher um idioma de eventos e escrevê-lo num ADR, ou os sinais são peso morto com manutenção. (Se a escolha for mantê-los para o BI incremental, P1 vira pré-requisito.)

### P9 · Fronteira (registrar; não é defeito do pacote)

- **Produção autentica o webhook só pelo token na URL.** O docstring lista os mecanismos da Efí — mTLS, *IP allowlist*, hash na URL — e implementa dois; a allowlist de IP, o único reforço viável sem proxy na DO App Platform, ficou de fora. É implementável no próprio view (CIDRs da Efí em settings). Enquanto o smoke sandbox real segue pendente (dívida viva declarada), essa é a superfície de ataque financeira mais exposta do sistema.
- A reconciliação cumulativa — a joia do pacote — continua **provada só contra mock**. O achado F2 do Cashman (cruzamento Payman × livro-caixa inexistente) pertence às duas auditorias: quando for implementado, é o Payman que fornece o lado de cá.

---

## Parte III — Desconstruir ou não?

**Não.** O núcleo é o mais próximo de "pronto" que a suite tem num domínio difícil, e a fronteira surpreendeu positivamente. O plano de ação natural tem quatro movimentos, todos pequenos:

1. **`on_commit` em todos os sinais** (P1) — mecânico, e destrava com segurança o futuro consumidor de eventos.
2. **Decidir chargeback** (P2): implementar no snapshot ou remover o tipo. A pior opção é a atual.
3. **Apagar ou trancar `payman/api/`** (P3) e, no mesmo gesto, consertar ou aposentar `get_active_intent` (P4).
4. **PR de auditoria financeira:** persistir motivo do refund (P5) + `idempotency_key` no refund (P6) + decisão registrada sobre P7.

Fora do pacote, duas ações herdadas que agora têm dono claro: IP allowlist no webhook Efí, e o `make smoke-gateways-sandbox` com credenciais reais — que continua sendo, como no relatório geral, a única coisa que separa "estável contra si mesmo" de "estável".

Próximo da série: **Fiscalman** (fecho o par de risco legal: gate de completude fiscal do catálogo + a emissão de 727 loc que vive fora do pacote) ou **Buyman** (fecho a rachadura filosófica do custo mutável antes que o BI construa em cima). Sua escolha.
