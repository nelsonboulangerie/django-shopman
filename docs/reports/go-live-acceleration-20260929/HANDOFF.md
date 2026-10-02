# HANDOFF — aceleração de go-live

> 🚪 **Este é o documento de ENTRADA ÚNICA** da aceleração de go-live. Sessão nova (Claude, Codex,
> DSH, quem for) começa aqui e só depois abre os outros, na ordem da seção 0m.2. O
> `docs/plans/NIGHT-SHIFT-BRIEF-2026-09-30.md` aponta para cá.
>
> **Atualizado em 2026-10-02, noite** (turno do coordenador noturno).
> A seção 0 é o estado agora; "0-obs", "0-dia", "0-tarde", "0-manhã" e as seções 1 a 5 são histórico: valem as armadilhas, não a fila.

---

## 0. Estado agora (02/10 noite, turno do coordenador noturno)

> Ordem de leitura: esta seção, depois a "0-obs" (o turno paralelo da sessão "Turno: observações do dono") e a "0-dia" (§0d.1b tem as pendências do ManyChat e das
> receitas), depois `PENDING-DECISIONS.md` (D34 a D41 são novas: D34 a D37 da sessão paralela, D38 a D41 deste turno).

### 0.1 O que entrou ou está na fila

| Frente | PR | Estado |
|---|---|---|
| 0: textos de seis modelos (D-023) | #1350 | ✅ mergeado |
| 0: `actions/checkout` 4 → 7 (Dependabot) | #1342 | ✅ mergeado |
| 0: Dependabot `python-runtime` | #1340 | ❌ fechado: reprova por construção (D-024) |
| 0: WP Receitas do dono (inventário) | #1351 | ✅ mergeado |
| 0: docs do contexto `doctl` (`shopman-do-app-admin`) | #1293 | refeito sobre o `main`, na fila; o vermelho do Marketing era o `npm audit`, já corrigido no `main` (343f03e5e) |
| 0: PDV, saldo de encomenda na retirada | #1257 | na fila; o vermelho do `operator-kit` era o piso da varredura de links (7 → 6, o PR tira um link de propósito) |
| 0: drafts #1220 a #1223 | — | fechados com prova (D-025) |
| 0: base de cidades GeoLite2 (rotina semanal que não abre PR sozinha, D37) | #1356 | na fila |
| 0: branches sem PR | — | 3 locais apagadas (já no `main`); `print-layouts` fica (triada no #1120); `geolite2` virou #1356 (D-025) |
| 1A: loja: aviso "Abrindo o cardápio" espera a página; observação por item da sacola ao KDS; a Saída mostra a observação | #1354 | ver 0.2 |
| 1B: PDV > Encomendas: filtros numa linha, busca sem repetição, hoje com dia da semana | #1353 | na fila (sessão "Turno: observações do dono") |
| 1C: o link de pagamento sai? | sem PR | respondido em 0.3 |
| 1D: Threads, Concierge × Jev, chá com sabor, controles de data | #1355 | na fila; perguntas em D34 a D37 |
| 2 e 3: Concierge (passos 0 e 1), corte de escopo sem contradição, pré-flight, matriz de prontidão | este PR | documentos corrigidos (ver 0.4) |
| 4: Receitas: estrutura a partir da Fx (sem números) | #1358 | na fila; perguntas 13 a 15 e o aval em D39 |
| ManyChat: 5 modelos, apagar 3 de Marketing, flows (§0d.1b itens 1 a 3) | #1361 (estado) | **BLOQUEADO**: o acesso ao Chrome para trazer a aba à frente foi negado duas vezes (`request_access` → `user_denied`, 21:20 e de novo pelo coordenador); com a aba em segundo plano (`visibilityState` "hidden") o formulário apaga a digitação. Lido às 21:20: os 5 não existem; `pedido_em_preparo` e `reembolso_processado` já APROVADOS (Utility). Padrão dos botões e campos anotado em `docs/reports/go-live-acceleration-20261002/MANYCHAT-ESTADO-0210.md` |
| CI: `npm audit` acusa `node-forge` (7 high, via `listhen` ← `@nuxt/cli`) no job "Marketing — cadeia completa" (não obrigatório) | em curso | agente dedicado; ver o PR `claude/npm-audit-node-forge` |
| Handoff do turno anterior (pendências vivas) | #1352 | na fila (este PR já está por cima dele) |

### 0.2 Loja (#1354), o que mudou

- **Aviso de navegação:** `useNavigationPending(pending)` (`surfaces/storefront-nuxt/app/composables/useNavigationPending.ts`):
  cada página preguiçosa diz que ainda espera o próprio dado; o `NavigationFeedback` só termina quando
  a rota terminou E nenhuma página está pendente. `lazy` e o limiar de 200 ms intocados;
  `performanceGuardrails.test.ts` ganhou a trava "toda página preguiçosa chama `useNavigationPending(`".
- **Observação por item:** op nova `set_line_meta` no `ModifyService` do orderman (mescla no `meta` da
  linha sem trocar o `line_id`; sem migração); `PUT /api/v1/cart/lines/<line_id>/notes/`; teto de 280
  caracteres (igual ao PDV); `meta["notes"]` entra na cerca de anonimização e no esquecimento.
  Componente `CartLineNote.vue` na `/sacola`.
- **A Saída:** `_build_expedition_card` lia `item.notes` (atributo que não existe); agora lê `meta["notes"]`.

### 0.3 O link de pagamento sai? (pergunta do dono)

1. [FATO] Desde que o #1339 entrou no ar (deploy `82e5d127`, 01/10 14:44 UTC) **não houve nenhum
   pedido no alpha** (`select count(*) from orderman_order where created_at >= '2026-10-01 14:44+00'` → 0),
   então nenhum link saiu pela regra nova.
2. [FATO] Os 4 links anteriores (30/09 e 01/10 de manhã) foram aceitos só pelo ManyChat, sem
   comprovante, e pararam ali (regra antiga): nenhum e-mail saiu. A cadeia viva está certa: `pdv`
   ManyChat → e-mail → SMS; `web` ManyChat → SMS → e-mail; `EMAIL_BACKEND` SMTP real.
3. [INFERÊNCIA] O próximo link do PDV deve sair "Entregue pelo e-mail, com comprovante"; o caminho tem
   14 testes verdes (`shopman/shop/tests/test_notification_delivery_receipt.py`, rodado em 02/10), mas
   **NÃO VERIFICADO no vivo**: falta gerar um link de verdade no PDV.

### 0.4 Achados do turno (não redescubra)

- **Drift do spec agora é `[FAIL]`, de propósito** (D-026): só `SHOPMAN_COURIER_ADAPTER`, ligado no
  painel e fora do arquivo (D-020). ⛔ Nenhum `apps update --spec` sem repor essa chave à mão: o
  arquivo de hoje desligaria a entrega por parceiro.
- **Checks obrigatórios:** 23, sem regressão (`check_canonical_docs.py --live-required-checks`:
  "[OK] ... matches live branch protection (23 contexts)"); espelho em `.github/required-status-checks.json`.
- **Concierge:** passo 0 (`concierge_check`) satisfeito; passo 1 (`observe` → `assist`) decidido na
  D32, execução é escrita no spec vivo (do dono, junto com o passo 2); **passo 2 é do dono** (D40):
  FAQ com 14 perguntas e 0 publicadas, copy, flow do ManyChat. Plano atualizado em `WHATSAPP-CONCIERGE-PLAN.md`.
- **Corte de escopo:** `PRODUCT-V1-SCOPE-BACKLOG.md` corrigido nas linhas 8, 33, 34, 46 ("Agentes de
  atendimento" fora contradizia a D-017), 65, 68 e 76; três itens pós-v1 viraram a pergunta D38.
- **Pré-flight:** restauração ✅; Pix segue simulado (`SHOPMAN_PIX_ADAPTER=payment_mock`,
  `SHOPMAN_EXPOSE_MOCK_CAPTURE=true`): regra de parada do dono; Stripe e Focus NÃO VERIFICADOS;
  `production-readiness` não tem modo só leitura (não rodado); SHA candidato do corte ainda não definido.
- **Jev:** não rodou. Prova: o comparador manda mensagem real de cliente (decisão do dono), o
  `typesafe` não está aprovado, não há `JEV_API_KEY` nesta máquina, e o gabarito tem 0 conferidas (D35).
  Achado: o concorrente `regex` do comparador mede a regra velha de 4 causas, não a de 12
  (`intent_benchmark.py:135-145` × `triage.py:175-184`).
- **Controles de data:** 14 campos em 11 arquivos, todos o seletor nativo, nenhum compartilhado.
  Padronizar primeiro o trio do PDV (agendar, reagendar, Encomendas), depois do #1353.

### 0.5 O que depende do dono

D34 (Threads) · D35 (Jev) · D36 (chá com sabor) · D37 (permissão do GitHub Actions) · D38 (três
pós-v1) · D39 (receitas 13 a 15 e o aval do plano) · D40 (Concierge passo 2: FAQ, copy, flow) ·
**ManyChat:** deixar a aba "Criar modelo" do ManyChat na frente (ou liberar o Chrome no pedido de acesso) e dizer "segue": a sessão envia os 5 modelos, cria os flows e liga no Admin · `fulfillment.courier="auto"` quando quiser (clique pronto: `/admin/shop/channel/66/change/`, aba
"Preparo e entrega", acrescentar `"courier": "auto"` ao JSON; chama a TaOn de verdade) · gerar um link
de pagamento no PDV para provar 0.3 · o Pix real antes da virada (D-016) · e as abertas de antes:
D2, D8, D18 (b, d, e), D22, D23, D25, D26, D27, D30, D31.

---

## 0-obs. Turno das observações do dono, 02/10 (histórico; #1354 fechado como duplicado do #1357)

### 0o.1 O que entrou

| Frente | PR | Estado |
|---|---|---|
| Ordem 1: link de pagamento no vivo | sem PR | **meia verificação**: cadeia viva confere com o seed; nenhum link saiu depois do #1339; envio de teste não disparado (0.2) |
| A1: aviso "Abrindo o cardápio" espera a página (`useNavigationPending`) | #1354 | na fila; única falha é `Marketing — cadeia completa` (`npm audit`, alerta novo no `listhen` via `nuxt`/`nitropack`, não é deste PR e não é check obrigatório) |
| A2: observação por item da loja chega ao KDS; Saída lê `meta["notes"]` | #1354 | idem. ⚠️ toca o Core: op nova `set_line_meta` no `ModifyService` do orderman, com a cerca de texto pessoal |
| B1 a B4: Encomendas do PDV, filtros numa linha (`FilterBar` com opção `touch`), busca sem repetição, "Hoje, ter 29/09" | #1353 | na fila, 50 de 50 checks verdes. Primeira encomenda sobe 206 px em 1440x900 |
| C1 opções de produto, C2 controles de data, C3 Threads, C4 Jev | este PR (docs) | PENDING D34 a D37 |

### 0o.2 Achados do turno (não redescubra)

- **Link de pagamento, o que o vivo mostra (01/10).** Cadeia no banco: `pdv` = `manychat → email → sms`;
  `web` e `whatsapp` = `manychat → sms → email`. Igual ao seed. Os quatro `payment_link_sent` que
  existem (30/09 e 01/10 de manhã) são TODOS anteriores ao #1339 e pararam no ManyChat, sem
  identificador e sem tentativa no e-mail. Nenhum envio depois do #1339, então o "segue para o
  e-mail" **não está provado no vivo**. O Gestor já mostra a verdade no pedido
  (`PDV-261001-N83`: "Aceito pelo provedor, sem comprovante").
- **Por que o teste não rodou:** o token do contexto `shopman-do-app-admin` não tem `exec`
  (`apps console` devolve 403); o `PDV-261001-N83` já está pago (sem botão de reenvio); uma venda
  nova no PDV pede o operador. Próximo passo: o dono faz UMA venda por link no PDV para ele mesmo,
  e a sessão lê a trilha em `orderman_directive.payload->'notification_delivery'->'attempts'`
  (somente leitura, conexão direta 25060).
- **Piloto de intenções:** 147 amostras *sugeridas*, **0 conferidas** (o placar pede 30); sem
  `JEV_API_KEY`; `typesafe` fora da lista aprovada. O placar não roda para ninguém, não só para o
  Jev (D36).
- **Encomendas, imagens de referência:** o POS não roda teste visual em nenhum workflow da CI e
  nenhum workflow regera; as 4 imagens nasceram no ambiente local (Playwright 1.63.0 e chromium-1243,
  iguais ao lock) e foram regeradas nele.
- **Filtrar nas Encomendas custa 3 toques** (Filtrar, dimensão, opção) em vez de 1; a contagem por
  opção foi para o menu. Se o balcão reclamar, é o preço do espaço ganho.

## 0-dia. Estado de 02/10, turno das ordens de 01/10 noite e 02/10 (histórico)

### 0d.1 O que entrou

| Frente | PR | Estado |
|---|---|---|
| 0: fechar o turno anterior (#1343) | #1343 | ✅ mergeado 01/10 15:58 UTC; D25 a D32 no `main` |
| 1: escopo do go-live: fora só Marketing e B.I. (D28 → D-017) | #1344 | ✅ mergeado 01/10 18:57 UTC |
| 1b: Concierge: visão do dono, distância, proposta de triagem (D32) | #1344 | ✅ mergeado |
| 2: courier Machine: `/api` no detalhe, cotação com endereço, link de rastreio, webhook no payload documentado, chaves no spec, roteiro de homologação | #1345 | ✅ mergeado 01/10 18:57 UTC |
| 3: triagem do Concierge implementada ("aprovo a triagem", D-018) + `check_concierge_readiness` + `concierge_check` | #1347 | ✅ mergeado 01/10 21:07 UTC (antes: `except` silencioso em `triage.py`, corrigido no próprio PR) |
| 4: ManyChat: contrato de campos cobre toda variável do modelo; botão do `link_pagamento_enviado` | #1346 | ✅ mergeado |
| 5: token do `doctl` rotacionado | sem PR (painel + `doctl`) | ✅ feito |
| 6: ensaio de restauração pelo fork (dono, no painel) | este PR (runbook) | ✅ feito e conferido; falta o dono apagar o cluster |
| 7: Machine: User-Agent próprio (a borda recusa `python-requests` com 403) | #1348 | ✅ mergeado 01/10 20:49 UTC; imagem `web-b6f0459fc` no ar |
| 7b: Machine: 4 credenciais (SECRET) e `SHOPMAN_COURIER_ADAPTER` no painel da DO | sem PR | ✅ feito pelo dono; deploys `fd5c3921` e `227a0acb` ACTIVE, sem `SHOPMAN_E011`; drift `[OK]` |
| 7c: `fulfillment.courier="auto"` no canal de entrega | sem PR | **espera o dono**: ligado, pedido de entrega chama a TaOn de verdade |
| 8: modelos no ManyChat | sem PR | 6 enviados à Meta pela sessão + 1 aprovado (dono); 4 esperam ajuste de texto (0.2) |
| 9: receitas do Drive | sem PR | **espera o dono** (nomes dos arquivos) |

### 0d.1b Pendências vivas ao fim do turno (02/10, noite): a próxima sessão começa aqui

1. **ManyChat, enviar 5 modelos** (textos aprovados, D-023, corpos em `whatsapp-templates-meta.md`):
   `pagamento_falhou`, `pontos_fidelidade`, `pedido_entregue_v2` (sem botão),
   `fila_vaga_disponivel_v2` (botão "Confirmar pedido", `/pedido/` + `order_ref`),
   `produto_chegou_v2` (botão "Garantir já", `/produto/` + `product_sku`). `pedido_em_preparo` já foi
   enviado em 02/10. **Armadilha:** o formulário só aceita digitação com a aba do ManyChat VISÍVEL
   (`document.visibilityState == "visible"`); em segundo plano a digitação some sem erro. A primeira
   digitação depois de carregar também é apagada: digite um caractere, espere ~20 s, localize o campo
   por referência e digite de novo. Variável no corpo só pelo botão `{}` (chaves digitadas viram texto).
2. **Apagar** `pedido_entregue`, `fila_vaga_disponivel` e `produto_chegou` (Marketing) quando os `_v2`
   forem aprovados. O nome `_v2` fica.
3. **Flows** (dono: "Flow você vai fazer"): um flow por modelo aprovado no ManyChat e o namespace no
   `NotificationTemplate` do evento (Admin). Sem isso a mensagem segue como texto livre.
4. **Entrega por parceiro:** `fulfillment.courier="auto"` **NÃO ligar** (dono, 02/10: "Não ligue agora o Taon ainda").
5. **Receitas (WP-RECEITAS-DO-DONO, #1351):** respostas do dono em 02/10: (1) a **Fx** é a fonte para
   tradição, campagne e ciabatta; (2) etapas, tempos e temperaturas **não existem**, ele edita depois;
   (3) a aba LEVAIN pode ser lida, mas está desatualizada; (4) **PH é massa de Tradição** e **Focaccia é
   massa de ciabatta**. Próximo passo: propor estrutura a partir da Fx, sem inventar nada que ela não diga.

### 0d.2 Achados do turno (não redescubra)

- **ManyChat: contrato de campos (#1346).** O adapter só regrava no perfil os campos declarados
  (`notification_manychat.py:587-593`). `order_cancelled`, `order_rejected` e `order_preparing`
  não declaravam `status_note`; `order_cancelled`, `preorder_reminder` e `payment_confirmed` não
  declaravam `order_ref`. O `pedido_cancelado` e o `pedido_nao_confirmado` estão APROVADOS com
  `status_note` no corpo: o cliente recebia o motivo e o link do pedido anterior. Trava:
  `shopman/shop/tests/test_manychat_template_contract.py` lê o documento dos modelos.
- **Modelos enviados em 01/10 (ManyChat > Enviar para análise):** `link_pagamento_enviado`,
  `pagamento_lembrete`, `pagamento_expirado`, `fila_vaga_disponivel`, `fila_vaga_liberada`,
  `produto_chegou` (em análise); `pagamento_confirmado` já APROVADO (dono). O ManyChat recusou
  antes da Meta, por formato: `pedido_em_preparo` ("Minimum of 7 words required for 2 variable
  parameter") e `pagamento_falhou` ("Template body cannot start or end with a variable": o ponto
  final sozinho não conta). `pontos_fidelidade` tem o mesmo defeito; `reembolso_processado` não foi
  enviado (a aba do ManyChat em segundo plano não aceita digitação). Textos novos: PENDING D33.
  Armadilha do formulário: a primeira digitação depois de carregar é apagada; localizar o campo por
  referência e digitar de novo.
- **Catálogo no ManyChat (lido em 01/10):** 20 modelos, 19 aprovados, `OTP` recusado (desnecessário).
  Faltam 11 de cliente com texto revisado em 25/09. ⚠️ A Meta reclassificou o `pedido_entregue`
  como **Marketing**: custa mais e quem recusou marketing deixa de receber.
- **Botão do `link_pagamento_enviado`:** vai para `/pedido/{{order_ref}}` (D-019). A tela do pedido
  já mostra o link de cobrança (`PaymentBlock.vue:53-62`).
- **Machine, credenciais:** o usuário da API é o próprio login Gestor da empresa no painel
  (`cloud.taximachine.com.br`, "Nhk Panificadora", cargo de administrador com permissões fixas,
  já com API Empresa, Entrega e Webhook). Não existe seção "Machine API" no painel da empresa
  (equívoco da coordenação, confirmado pelo dono) nem Joyce; a chave o dono já tinha. Ficam num
  arquivo local do dono (`~/.config/shopman/machine.env`, `600`), nunca no repositório.
- **Machine, User-Agent (#1348):** a borda recusa `python-requests/x.y` com 403 HTML nos dois
  ambientes; com User-Agent próprio a produção responde. Sem o #1348 no ar, ligar o interruptor
  faz toda chamada falhar.
- **Machine, homologação: não há chave.** A chave de produção é "inválida" na homologação, e a
  TaOn não tem chave de homologação (dono, 02/10). ⛔ **Nenhuma chamada completa à TaOn**: a chave
  é de produção, e abrir corrida chama entregador de verdade. Feito só leitura: cotação
  (R$ 8,00, 11 min, 3,43 km) e `listarWebhook` (vazio). Abrir, status, detalhes, posição, link,
  cancelar e webhook seguem NÃO VERIFICADOS contra a API viva (só contra a doc e o mock).
- **Machine, API v1:** o limite que pesa é **3 consultas de status por minuto por corrida**
  (polling de 60 s cabe; abaixo de 20 s estoura). Os 800/min e 60/min são da v2.
- **Machine, webhook:** a assinatura HMAC (`Signature-V2`) ainda não é conferida; a borda se
  autentica só pelo token na URL. Pendência declarada.
- **Ressalva da senha:** a API usa o login do painel. Se a senha desse usuário mudar, a entrega
  para até o `MACHINE_API_PASSWORD` ser trocado no painel da DO. Um usuário só para a API evitaria;
  não bloqueia (dono, 02/10: não criar usuário novo).
- **`SHOPMAN_COURIER_ADAPTER` fica FORA do arquivo do spec** (D-020): aplicado sem credenciais,
  o deploy reprova (`SHOPMAN_E011`). Teste impede a volta; entra pelo painel, por último.
- **Concierge:** em `observe`, ligar `SHOPMAN_CONCIERGE_ENABLED` não muda nada (`service.py:89-91`).
  A sequência para ligar está no `WHATSAPP-CONCIERGE-PLAN.md`, com o passo 0 `manage.py concierge_check`.
  `manychat_flows --check` e `check_whatsapp_flow_coverage` NÃO cobrem o Concierge; quem cobre é o
  `check_concierge_readiness` (`SHOPMAN_W022`/`W023`, só Warning de propósito).

### 0d.3 Token do `doctl` (D-022)

`shopman-spec-update` (8 escopos, vazado numa auditoria) → `shopman-do-app-admin-2026-10`, mesmos 8
escopos (`actions:read`, `regions:read`, `sizes:read`, `app:read`, `app:update`, `database:read`,
`database:view_credentials`, `registry:read`), **expira em 2 meses** (fim de nov/2026: renovar).
Validado por `doctl auth init` ("Validating token... ✔"). Identificação do antigo: o "último uso" virou "há 27 segundos" logo após um `apps list` pelo contexto.
Validação: `apps list` OK, `check_do_spec_drift.py --context shopman-do-app-admin` → `[OK] spec_drift`.
O antigo não aparece mais na lista do painel.

### 0d.4 Ensaio de restauração: FEITO pelo fork (o portão fechou)

Decisão do dono (D-021): sem token temporário; ele fez o fork no painel. Cluster
`shopman-staging-postgres-oct-1-backup`, criado 19:28:28 UTC, cerca de 7 min até `online`.
191 tabelas, 186 com a mesma contagem; as 5 diferentes são de conversa e explicadas pela rotina de
retenção (o restaurado tem a mais); pedidos 4817 e 306 migrações nos dois; `migrations-pending` = 0.
Detalhe: `docs/runbooks/backup-e-restore.md` §1b; item do pré-flight marcado. O dono já apagou o cluster (só restam
`shopman-staging-postgres` e o cache, `doctl databases list`). Reapontar o app não foi ensaiado.

### 0d.5 O que depende do dono

D33 (textos de 4 modelos) · `fulfillment.courier="auto"` no canal de entrega · nomes dos arquivos de
receita · e as abertas de antes: D2, D8, D18 (b, d, e), D22, D23, D25, D26, D27, D30, D31.

⚠️ Continua valendo a 0t.4: o Pix real se ensaia ANTES da virada (D-016).

### 0d.6 Em voo que não é deste turno

- #1293 (docs: contexto doctl renomeado) em `CONFLICTING`, de 30/09.
- #1257 (PDV: saldo de encomenda) com `operator-kit` vermelho, de 29/09.
- Drafts #1220 a #1223 (snapshots WIP de outras frentes).

---

## 0-tarde. Estado de 01/10, fim do turno da tarde (histórico)

### 0t.1 O que entrou

| Frente | PR | Estado |
|---|---|---|
| 0: destravar o #1330 (check `operator-kit` vermelho: a trava "clique nunca inerte" pegou o `chooseOther` do `OrderReasonDialog.vue`, async só pelo `nextTick`; NÃO era CodeQL) | #1330 | ✅ mergeado |
| 1: mapa WP-DATA-E-PROMESSA (só documento) | #1335 | ✅ mergeado |
| 2: receitas D11, D19, D20, D24 | #1338 | ✅ mergeado |
| 3: recibo de envio crítico (D3) | #1339 | ✅ mergeado |
| 4: checks obrigatórios conferidos contra o vivo, proposta de corte, Pix no checklist, ensaio de restore | #1336 | ✅ mergeado |
| 5: loja, data da sacola na resolução | sem PR | **espera o dono** (D25: P1 a P3 do mapa) |
| 6: loja, versão nova forçada (D9) e trilho no `shell/` (D10) | #1341 | ✅ mergeado; o trilho NÃO saiu do `shell/` (a `/sacola` o exibe na primeira pintura): D31 |
| 7: R2 pronto e desligado (D6) | #1337 | ✅ mergeado; ligar é do dono (D30) |
| 8: `DATABASE_CONN_MAX_AGE=0` no spec vivo (D21) | spec vivo + #1334 | ✅ feito e mergeado |

Decisões novas registradas: `docs/coordination/DECISIONS.md` D-011 a D-016. Perguntas novas ao
dono: `PENDING-DECISIONS.md` D25 a D31.

### 0t.2 Frente 8, como foi feita (não refaça)

Drift `[OK]` antes, nada em SUMIRIAM → backup `spec get` (965 linhas, 42 `type: SECRET`) → uma linha
(`133c133`, `DATABASE_CONN_MAX_AGE` `"60"` → `"0"`) → `apps update` → deployment `c4f07630` ACTIVE →
`spec get` de novo: só a linha 133 difere, 42 SECRET idênticas chave a chave → drift `[FAIL]` só nessa
env até o #1334 trazer o arquivo, depois `[OK]` → `/health/live/` e `/health/ready/` 200.
`connect;dur` no `shell/` (n=10): média 42,5 ms antes, 37,4 ms depois (ruído; o ganho é não deixar
backend ocioso). Depois de 30 requests concorrentes: 3 conexões ociosas no banco `shopman` (as do
PgBouncer). Não havia contagem viva de "antes". Os workers também recebem 0 e reconectam por ciclo.

### 0t.3 Ensaio de restauração: o que foi e o que NÃO foi feito

- **Fork (o de verdade): NÃO FEITO.** `doctl databases fork` → `403`; falta `database:create` no
  `shopman-do-app-admin`. É do dono (D29). Continua portão duro.
- **Lógico (complemento):** `pg_dump` pela conexão direta 25060 em 104 s (7,1 MB), `pg_restore -j4`
  local em 23 s, 4815 pedidos, último `PDV-260930-R62`, 306 migrações: tudo bate; `make
  migrations-pending` contra o restaurado: 0 pendente. Banco e dump locais apagados depois.
  Runbook corrigido (`DJANGO_DEBUG=true`, fork herda o plano): `docs/runbooks/backup-e-restore.md`.

### 0t.4 ⚠️ Pix: última chave a LIGAR, não a ENSAIAR

O botão público que deixa o cliente marcar o próprio pedido como pago (Pix no simulador, D-006)
**continua aberto**, por decisão do dono. O ensaio do Pix real (`payment_efi` + `EFI_SANDBOX=true` +
`SHOPMAN_EXPOSE_MOCK_CAPTURE=false`, que fecha o botão por construção) e a rotação do
`EFI_WEBHOOK_TOKEN` (D22) têm de acontecer **ANTES** da virada. Está no
`docs/runbooks/go-live-preflight.md` §4 e é regra de parada no `go-live-cutover.md` §0 (D-016).

### 0t.5 O que depende do dono

D25 (data e promessa, destrava a Frente 5) · D26 (editar publicada no app) · D27 (mais eventos
críticos, alerta frequente) · D28 (corte de escopo) · D29 (token para o fork) · D30 (R2) · D31 (trilho do `shell/`) · e as
abertas de antes: D2, D8, D18 (b, d, e), D22, D23.

### 0t.6 Em voo que não é deste turno

- #1293 (docs: contexto doctl renomeado) em `CONFLICTING`, com check do Marketing vermelho; de 30/09.
- #1257 (PDV: saldo de encomenda) com `operator-kit` vermelho (trava de links cross-app), de 29/09.
- Drafts #1220 a #1223 (snapshots WIP de outras frentes).

---

## 0-manhã. Estado de 01/10 depois da Frente 0 (histórico)

### 0m.1 Onde as coisas estão

| O quê | Estado | Onde |
|---|---|---|
| Turno autônomo 30/09 → 01/10 | encerrado; 28 PRs mergeados | NIGHT-REPORT (abaixo) |
| NIGHT-REPORT + PENDING-DECISIONS (D1–D16) | **na fila de merge** (PR #1299; até entrar, leia no branch `claude/turno-autonomo-coordenacao-76dc5f`) | `docs/reports/go-live-acceleration-20260930-diag/` |
| Diagnósticos D4, D5, D14, D16 (turno DSH de 01/10) | **na fila** (PR #1325); estavam só na worktree do DSH, o D16 nem commitado | `docs/reports/go-live-acceleration-20261001/` |
| #1324 (margem da vitrine comia a unidade da sacola) | ✅ mergeado 01/10 09:00 UTC | `main` |
| **D14 token da Efí no access log** | ✅ **FECHADO** 01/10 09:21 UTC (detalhe em 0.3) | spec vivo |
| D13 republicar fichas com insumo repetido | ✅ **nada a fazer**: no alpha, 72 receitas com versão atual e 74 versões no total, **zero** com o mesmo SKU em duas linhas (consulta só-leitura, conexão direta 25060) | — |
| D15 picos Cloudflare ↔ DO | medido 01/10 09:23–09:27 UTC: **não reproduz** (400 requisições, 0 erro, 0 acima de 5 s; tamanho, encoding, IPv4/6 e H1/H2 descartados; H3 e outra rede não medidos). Deployments explicam no máximo 2 de 4 picos; o 520 das 04:44:41 caiu fora de troca. Chamado na DO só para pedir log da madrugada | NIGHT-REPORT |

### 0m.2 Ordem de leitura

1. **Este arquivo** (estado, em voo, armadilhas).
2. `docs/reports/go-live-acceleration-20260930-diag/NIGHT-REPORT.md` (o que entrou no turno, medições de produção).
3. `docs/reports/go-live-acceleration-20260930-diag/PENDING-DECISIONS.md` (D1–D16: o que é do dono).
4. `docs/reports/go-live-acceleration-20261001/` (D14, D4, D5, D16: diagnósticos com caminho:linha).
5. Só para regras de convivência e deploy: `docs/plans/NIGHT-SHIFT-BRIEF-2026-09-30.md` §1 a §5.

### 0m.3 D14, como foi fechado (não refaça)

- `make deploy-spec-drift context=shopman-do-app-admin` acusava **uma** divergência: o `run_command`
  do `web` sem `--access-log=/dev/null` (a flag está em `.do/app.alpha-subdomains.yaml` desde 05/09).
- Backup do spec vivo, edição textual de **uma linha**, `apps update`. SECRET antes × depois:
  **42 = 42, idênticos** (chave e hash do valor cifrado). `spec get` depois: diff de uma linha só.
- Deployment `50988cd5` ACTIVE 09:24 UTC. Drift agora: **[OK]**. `/health/live/` e `/health/ready/` 200.
- Prova: POST no webhook da Efí com token **falso** (sonda) → 401, e a sonda **não** aparece no log;
  a única linha é a do `django.request`, que já grava `token=[redacted]`.
- Busca no log antes do update: só o deployment ativo tem log recuperável pelo `doctl` (347 linhas,
  09:05–09:19 UTC): **0** `token=`, **0** `efi/pix`. Os 59 deployments anteriores não devolvem log.
- ⚠️ **O token NÃO foi rotacionado.** É de sandbox (`EFI_SANDBOX=true`, Pix no simulador), mas é a
  mesma variável `EFI_WEBHOOK_TOKEN` que irá para produção, onde é a autenticação **única** do
  webhook (sem mTLS, allowlist de IP vazia). **Rotacionar é OBRIGATÓRIO antes de ligar a Efí de
  produção** (item de checklist do corte do Pix). Ver `d14-token-efi.md` §7.

### 0m.4 Turno de 01/10: frentes (atualizado ~10:35 UTC)

| Frente | PR | Estado |
|---|---|---|
| 1: token da Efí fora do access log (D14) | spec vivo | ✅ feito |
| 2: loja 1 pedido = 1 data + 409 de ajuste mostra o teto da linha | #1329 | ✅ mergeado |
| 3: "Etapa/Etapas" + guardrails + processo das 11 massas (92 etapas) | #1326 | ✅ mergeado |
| 4: motivos de recusa (lista de 11 + "Outros", agrupada) | #1328 | ✅ mergeado |
| 5: botão "Adicionar" ativo desde o primeiro quadro (D1) + `usePendingAction` | #1330 | na fila |
| 6: D12 pool de Redis por processo + `gc.freeze()` | #1331 | na fila |
| 7: D6 referências externas + D7 nota com critérios editáveis | #1332 | na fila |
| 8: D15 medição de rede | sem PR | sem sintoma hoje |

Detalhe e medições: NIGHT-REPORT, seção "Turno de 01/10". Decisões novas: D17 a D24.

⚠️ **O balcão NÃO tem "1 linha = 1 data".** A comanda tem uma data por sessão; o
`TestOneLineOneDate` é teste da loja. Ver D17 antes de supor o contrário.

⚠️ **O processo das 92 etapas NÃO é dado da casa.** O próprio artifact de origem (claude.ai
`b8cd4fc0-…`, 05/09) o chama de "proposta minha, é a parte que eu menos sei". Ele está no repo para
não se perder, não para ir ao seed.

⚠️ **D12, degrau 1 (`CONN_MAX_AGE=0`) pede escrita no spec vivo** (`DATABASE_CONN_MAX_AGE="60"` está
no spec, e o deploy não escreve spec). Fora da autorização deste turno: é do dono.

---

## Histórico de 30/09 (seções 1 a 5)

## 1. O que foi resolvido hoje

| Item | Estado | Prova |
|---|---|---|
| **App congelado 21 h** | ✅ RESOLVIDO | O spec vivo tinha perdido o bloco `databases` (só `- name: postgres`). Devolvido. Deployment `3a3b0053` ACTIVE 18:21 UTC |
| **Storefront lento (queixa nº1)** | ✅ RESOLVIDO | `/` de **3,06–4,49 s → 0,49–0,92 s**. `/menu` 3,79 s → **0,40–0,49 s** |
| **Deploy: até 4 deployments por run** | ✅ RESOLVIDO | Run `36774871663`: **1** deployment, causa `manual`, `deploy_mode: single_deployment`, smoke passou |
| **Prova de origem do BFF (IP do cliente)** | ✅ LIGADA | Auditoria gravava IP de saída da DO (`206.189.202.53`); agora grava o IP real do cliente |
| **VAPID (notificação push)** | ✅ LIGADO | 5 chaves aplicadas; `check --deploy` sem E024/W024 |
| **Contexto doctl cego** | ✅ REMOVIDO | Era o **default**, mutilava `databases` na leitura SEM ERRO. 8 docs corrigidos |
| **Guard de drift do spec** | ✅ NO AR | `scripts/check_do_spec_drift.py` cobre `databases`, imagens e tamanho de componente |

## 2. Armadilhas — leia antes de tocar em qualquer coisa

1. ⛔ **NUNCA** `doctl apps update --spec` com um arquivo que não veio do spec VIVO. O update
   **substitui** o spec inteiro, não faz merge. Foi assim que o app congelou.
2. ⛔ **Sempre** `--context shopman-do-app-admin` (o antigo `shopman-spec-update` foi renomeado). O default do doctl agora é vazio e **falha alto**
   de propósito — não "conserte" isso pondo um token no default.
3. **Antes de aplicar qualquer spec:** `make deploy-spec-drift context=shopman-do-app-admin`.
   Se houver linha em SUMIRIAM, **pare**.
4. **Depois de aplicar:** `spec get` de novo e compare os SECRET antes × depois. Hoje são 42.
5. `deploy_on_push` está `false` nos 8 componentes. **Quem criar o deployment é o
   `deploy-images.yml`**, um por run. Não religue sem motivo.
6. A **primeira requisição após um deploy é lenta** (3–5 s); depois estabiliza. Não é regressão.

## 3. Em voo (verifique antes de abrir frente)

- PRs `#1291` (`deploy_on_push` false no arquivo `.do/`) e `#1292` (docs do contexto doctl).
  Quando o #1291 mergear, `make deploy-spec-drift` fica **verde**.
- O **caminho de deploy por push** (merge → 1 deployment) usa o mesmo passo do teste manual, mas
  ainda não foi exercitado por um merge real.

## 4. Próxima frente: ONDA 1 — o backend do Storefront

O cache de borda resolveu o **anônimo**. O que **não** foi resolvido é o custo do backend:

```
/api/v1/storefront/menu/   → ~3,3 s
  server-timing: projection;dur=2719 · availability;dur=1680 · db;dur=614 · shadow;dur=0.00
```

**93 consultas por request** para 44 cards. A disponibilidade é calculada **4× por request** e custa
`O(linhas de stockman_quant)`, não O(SKUs). **Análise completa e medida:**
`docs/reports/go-live-acceleration-20260929/13-hot-path-projecao.md` — não refaça.

### ATUALIZAÇÃO 2026-09-30 ~22:00 UTC — parte segura ENTREGUE (PR #1295, na fila)

P3 + P8 + P4 feitos, **nada em `packages/`**. Medição **local** (a de produção sai depois do deploy):

| | antes | depois |
|---|---|---|
| `menu/` consultas | 93 | **65** |
| `home/` consultas | 97 | **57** |
| `shell/` consultas | 4 | 2 |
| consultas a `shop_channel` | menu 9 / home 11 | **2 / 2** |

**Contrato do `home/` provado intacto:** 0 diferenças em **14.513 campos** contra 5 payloads do main.
E existe um teste que **falha se a home voltar a chamar `build_catalog`** — **não desfaça esse teste**.
De carona: a promoção ignorava o prefetch dos canais e fazia 1 consulta por promoção.

**MEDIDO EM PRODUÇÃO** (30/09, medianas de 5 amostras; deploy `405e3f25` ACTIVE às 23:17 UTC,
causa `manual` — **o caminho por push funciona**):

| | antes | depois |
|---|---|---|
| `home/` TTFB | 3,13 s | **~1,29 s** ✅ |
| `menu/` TTFB | 2,63 s | 2,51 s |
| `menu/` projection | 2.292 ms | 2.155 ms |
| `menu/` availability | 1.395 ms | 1.294 ms |
| `menu/` db | 396 ms | 292 ms |
| `menu/` query_count | 83 | **55** |

O `response_bytes` ficou **idêntico** (136.681 B antes e depois) — prova em produção de que o JSON
não mudou. E a produção tinha **83** consultas, não as 93 da bancada.

**O `menu/` quase não caiu (−6% de tempo, com −34% de consultas)** porque o que resta é a
**disponibilidade: ~1,3 s, 60% da projeção**. Isso é o **P2, no Core** — é o próximo grande ganho.

---

## ⛔ P7 — NÃO FAÇA (provado perigoso em 30/09)

A recomendação de aplicar `_quantity__gt=0` em `tracked_skus`
(`packages/stockman/.../services/availability.py:432`) **estava ERRADA** — veio do relatório 13 e foi
refutada por quem tentou executá-la.

Com o filtro, **um SKU esgotado deixa de ser "rastreado"** (o quant zerado nunca é apagado), e o gate
aprova SKU não rastreado com disponível `999999` — **venderia sem limite justamente o que acabou de
esgotar**. O executor provou na bancada e deixou a trava
`shopman/shop/tests/test_sold_out_sku_stays_tracked.py`, que reprova com o filtro aplicado.
**Não remova essa trava e não reaplique o filtro.** Resolver isso exige a frente do Core.

## ❌ P9 — NÃO VALE A PENA (medido)

O laço por item custa **~1,5 ms por request**, não os 100–250 ms que o relatório 13 estimou.
Medido com profiler. O custo real está na disponibilidade.

🔎 **Descoberta fora do escopo, para a próxima frente:** **com sacola**, `home/` e `menu/` fazem
**~200 consultas**, e o custo está na **projeção da sacola**, não no catálogo. Isso **não** está no
relatório 13.

Ordem sugerida (P1, P6, P3, P8 e P4 já foram feitos):

| # | Ação | Ganho | Risco |
|---|---|---|---|
| **P7/P9** | `tracked_skus` com `_quantity__gt=0` · higiene do laço por item | −100 a −250 ms | baixo |
| **P2** | Disponibilidade 1× por request (waitlist re-chama o batch por data; bundle faz 3ª passada) | **−0,9 a −1,3 s** — `availability` mede ~1,4 s em produção | **ALTO — é Core** |
| **NOVO** | Projeção da sacola (~200 consultas com sacola) | não medido | a medir |
| P5 | Cortar duplicação do payload (120 cópias de card; 85 KB de 135 KB são `sections`) | −100 a −200 ms | médio (BE+FE atômico) |

**Antes de atacar: MEÇA a produção depois que o #1295 entrar.** O ganho de P3+P8+P4 pode já ter
comido parte de P2 — e não se otimiza o que não se mediu.
**P2 toca o Core** e exige revisão própria e `make test-stockman`.

## 5. Outras frentes abertas (não começadas)

- **Onda 2 (CI):** `test-shop` ainda é o caminho crítico (12,5 min por shard); `make install` roda
  13× por evento; falta escopo por diff nos gates caros.
- **Onda 4 (go-live):** cortes de escopo — inclusive derrubar a regra auto-bloqueante
  `PRODUCT-V1-SCOPE-BACKLOG.md:77` ("todas as 11 frentes").
- **WP-5** (trava por dispositivo no PDV) — só quando o atendimento/concierge estiver desenhado.
- `docs/guides/deploy-digitalocean.md:55` ainda diz que "publicar a tag nova já é o deploy" —
  deixou de ser verdade. Está no PR #1292.
