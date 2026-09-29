# GO-LIVE-ACCELERATION — diagnóstico e plano de aceleração

> Aberto em 2026-09-29. **Documento de plano: nada foi implementado.** Toda afirmação
> abaixo tem evidência de repositório vivo, comanda executado ou medição ao vivo, e está
> marcada `[FATO]`, `[INFERÊNCIA]` ou `[NÃO VERIFICADO]`.
>
> **Evidência de apoio (13 relatórios):** `docs/reports/go-live-acceleration-20260929/`
> (01 perf storefront · 02 perf operador · 03 Continuum · 04 segundo clique · 05 PWA ·
> 06 Pix default · 07 alterar pedido · 08 CI/deploy · 09 coordenação e decisões perdidas ·
> 10 caminho crítico · 11 observabilidade · 12 risco de regressão · 13 hot path).
>
> Worktree: `.dsh-worktrees/go-live-acceleration` · branch `dsh/go-live-acceleration-20260929`
> · base `origin/main` = `f0ffd02fd` (2026-09-29 15:36Z).

---

## 0. Resumo executivo

O objetivo é entrar em go-live com as principais funcionalidades no menor tempo, com fluxo
de atualização sem fricção. O diagnóstico diz que **os dois objetivos têm o mesmo inimigo:
trabalho que não precisava existir.**

1. **A lentidão está concentrada no Storefront, e não é a plataforma.** Medido ao vivo hoje:
   `/api/v1/storefront/menu/` **2,6–4,4 s**, `/home/` **3,2–5,5 s**, SSR da home
   **3,9–4,4 s**. No mesmo instante, as cascas de operador respondem em **0,35–0,50 s** e os
   dois health checks **melhoraram** desde 17/09. `[FATO]`
2. **A causa é fan-out de requisições + cálculo repetido + zero cache na leitura pública.**
   93 consultas por request de cardápio, com a disponibilidade calculada **4×** e custo
   `O(linhas de stockman_quant)`; `home/` constrói **o catálogo inteiro para guardar 3 cards**.
   E tudo responde `cache-control: private` + `Vary: Cookie` → **BYPASS em toda a borda**. `[FATO]`
3. **A piora de ~2× desde 17/09 não é código.** O diff do caminho quente no intervalo só
   acrescenta instrumentação. É **dado** (catálogo +33%, tabelas de estoque lidas inteiras) +
   **carga** (dois polls de 30 s por aba de cardápio, no mesmo `web` de 1 vCPU). `[FATO]`
4. **O Continuum não causa os 3 s, mas causa carga e uma regressão visível.** `shadow;dur=0.00`
   é campo incondicional e não prova nada; a flag é que prova (`SHADOW_ENABLED=false`). O que
   ele fez: dois polls de 30 s por aba, e **o cardápio passou a ser servido sem preço no
   primeiro quadro** (44 placeholders, zero `base_price_q`). `[FATO]`
5. **O maior ganho isolado não é Python: é cache de borda.** O mesmo app, na mesma borda,
   serve o snapshot estrutural a **0,151 s em HIT** contra **2,59 s em MISS**. `[FATO]`
6. **A CI tem um dono só e ele é removível.** `Runtime Gate` = **23–31 min**, caminho crítico
   `test-shop` com **20–30 min**, porque `test-shop`/`test-storefront` são os **únicos** alvos
   sem `-n auto`. Somando: 47 jobs por evento × 2 eventos, `make install` 13× a ~3 min,
   `npm ci` 46×, 9 builds Docker frios sem cache, e a suíte **triplicou** (23.045 testes hoje;
   o `CLAUDE.md` ainda diz "~6.500"). `[FATO]`
7. **Há bloqueadores de go-live no ar agora, e um deles é irreversível.** Pix = `payment_mock`,
   `SHOPMAN_EXPOSE_MOCK_CAPTURE=true` (botão público de quitar o próprio pedido), WhatsApp de
   Marketing em `MODE=open` com `DELIVERY_ENABLED=true`. `[FATO]`
8. **O mecanismo de coordenação não existe — só a trava de saída.** 77 worktrees, 894 branches
   locais, **115 branches fora do main somando 1.093 commits**. `grep -rn lease_id` devolve
   **uma** ocorrência: a linha de template do próprio documento que desenhou o lease. `[FATO]`
9. **Os agentes estão cegos.** O token do `gh` está inválido nesta máquina (HTTP 401), e é ele
   que alimenta `make inflight` — o inventário do que está em voo. Sem ele, cada sessão
   trabalha às cegas, que é a definição operacional de retrabalho. `[FATO]`

**A boa notícia:** nenhum dos itens acima exige reescrita. O caminho de menor tempo é
**configuração + remoção**, não construção. O plano abaixo ordena por isso.

---

## 1. Queixa a queixa: o que procede, o que não, e por quê

| Queixa do dono | Veredito | Causa apurada |
|---|---|---|
| "Performance extremamente lenta, sobretudo no Storefront" | **PROCEDE** | 93 consultas/request, disponibilidade 4×/request, zero cache. `[FATO]` |
| "O processo de atualização é moroso: CI, merge, deploy" | **PROCEDE** | Runtime Gate 23–31 min; sem `-n auto`; 47 jobs × 2 eventos. `[FATO]` |
| "Depois do Continuum parece mais lento e instável" | **PROCEDE EM PARTE** | Não é o custo por request (shadow off). É carga (2 polls/30 s por aba) + cardápio sem preço no 1º quadro. A piora de 2× é dado+carga, não Continuum. `[FATO]` |
| "Adicionar ao carrinho: erro, cliquei de novo e foi" | **PROCEDE** | Clique 1 faz handshake de CSRF (2 a 6 chamadas ao Django); clique 2 faz 1. `[FATO]` — a string exata "Não foi possível adicionar" **não existe** no repo; a real é "Não foi possível atualizar o carrinho" (`useCartState.ts:342`). |
| "Algumas coisas só funcionam no segundo clique" | **PROCEDE** | Botão nasce `disabled` até a hidratação; primeiro toque é no-op silencioso, sem feedback, num botão que *parece* ativo. `[FATO]` |
| "PWA desatualizado travado, sem opção de atualizar" | **PROCEDE, risco de cliente real** | Aviso dispara **uma vez** e é descartável; nada sonda versão; nenhum fetch tem timeout. O `operator-kit` já resolveu isso para o PDV em 17/09 — o storefront não recebeu. `[FATO]` |
| "Testador confirmou sem ver que Pix estava selecionado" | **PROCEDE** | Posição na lista vira default em 3 saltos; o rótulo "(padrão)" **não existe na tela**. O default é 100% front. `[FATO]` |
| "Preciso alterar pedido da loja online pelo Gestor" | **PROCEDE, com correção** | O mecanismo canônico **já existe** (`Order` selado + `data.adjustment`, `order_edit.py`) e **não** é exclusivo de encomenda. Falta **exposição**, não mecanismo. ⚠️ Trocar **forma de pagamento** não é coberto — é capacidade nova. `[FATO]` |

---

## 2. Bloqueadores de go-live (ordem de severidade)

### B1 — Marketing/WhatsApp é o único risco IRREVERSÍVEL aberto `[FATO]`

`.do/app.alpha-subdomains.yaml` (spec do ambiente vivo):
`SHOPMAN_MARKETING_WHATSAPP_MODE=open` (:481-483) · `SHOPMAN_MARKETING_WHATSAPP_DELIVERY_ENABLED=true`
(:485-487) · `CONCIERGE_OBSERVATION_ALLOW_ALL_SUBJECTS=true` (:637-639).

Um clique errado na janela manda WhatsApp real para cliente real, e **não há desfazer**.
**Ação:** desligar Marketing da janela de go-live. São ~2 minutos de env e é a maior redução
de risco irreversível disponível.

### B2 — Botão público de quitar o próprio pedido `[FATO]`

`SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true` (:321-323) + `SHOPMAN_EXPOSE_MOCK_CAPTURE=true`
(:325-327), com Pix resolvendo para `payment_mock`. Rota
`storefront/api/urls.py:182` (`payment/<ref>/mock-confirm/`). O guard de runtime exige as duas
condições — e as duas valem. Auto-quitação alcançável pelo cliente.

### B3 — Pix em gateway simulado; NFC-e em homologação `[FATO]`

`EFI_SANDBOX` nasce `true` (`config/settings.py:1904`) e `FOCUS_NFE_ENVIRONMENT` nasce
`homologacao` (`:1795`). **Nenhum dos dois tem trava em runtime**, e o perfil de produção
(`scripts/check_release_readiness.py:377-418`) checa 7 flags — **não checa nenhum dos dois**.
Silencioso nas duas pontas: dinheiro que não entra e nota que não existe.

### B4 — Ensaio de restore nunca aconteceu `[FATO]`

Backup/PITR estão verificados; o **ensaio** não. Gate duro aberto (R8 §92-98 está desatualizado:
o `--read-only` já existe, commit `145ff129c`).

### B5 — Os 21 checks obrigatórios não estão versionados `[NÃO VERIFICADO]`

Não existem em arquivo nenhum do repositório (`gh` sem auth impediu confirmar a lista viva).
Renomear um job vira trava permanente e invisível. Versionar é pré-requisito de qualquer
mexida segura na CI.

---

## 3. Plano de aceleração — ondas

Regra de ouro: **uma frente = um branch = um PR**. Nada termina o turno dormente.

### Onda 0 — freio de mão e visibilidade (horas, não dias)

| # | Ação | Por quê | Prova de pronto |
|---|---|---|---|
| 0.1 | Reautenticar `gh` (`gh auth login`) | Sem isso **nenhum** agente vê o que está em voo; `make inflight` fica cego | `make inflight` roda e lista PRs |
| 0.2 | Desligar Marketing/WhatsApp da janela (B1) | Único risco irreversível | `MODE` ≠ `open`; env aplicada |
| 0.3 | Desligar `EXPOSE_MOCK_CAPTURE` e `ALLOW_MOCK_PAYMENT_ADAPTERS` (B2) | Botão de auto-quitação | Rota responde 403/404 |
| 0.4 | `EFI_SANDBOX`/estado fiscal explícitos + entrar no perfil de produção (B3) | Silêncio de dinheiro/fiscal | `production-readiness` reprova se ausente |
| 0.5 | Ler o log que já existe: `storefront_catalog_observation` | Separa CPU × SQL × nº de consultas sem escrever código | 3 números registrados no ledger |
| 0.6 | Ligar `%{time_starttransfer}` no smoke pós-deploy | Fix de regressão de produção mais barato que existe (~1 linha) | Smoke falha se TTFB estourar |

### Onda 1 — performance do Storefront (o que o cliente sente)

**Alvo:** cardápio ≤ 0,6 s para visitante anônimo; home SSR ≤ 1,2 s. Hoje: 2,6–4,4 s e 3,9–4,4 s.

| # | Ação | Ganho estimado | Risco | Evidência |
|---|---|---|---|---|
| 1.1 | **Cache público de borda** para GET anônimo em `menu/`,`home/`,`catalog/` (hoje `private` + `Vary: Cookie` + `csrftoken`) | **−2,2 a −3,0 s** | médio | o mesmo app serve snapshot a 0,151 s HIT × 2,59 s MISS |
| 1.2 | **Disponibilidade 1× por request** (a fila de espera re-chama o batch por data; bundle faz 3ª passada) | −0,9 a −1,3 s | **alto (Core)** | 93→71 consultas desligando a fila; 2.472 quants = 121 ms |
| 1.3 | **`home/` para de construir o catálogo** para guardar 3 cards (`home.py:379`) | −2,0 a −2,5 s | médio-baixo | 97 consultas / 67,9 ms vs 4 / 2,4 ms do `shell/` |
| 1.4 | `published_products_by_collection`: 1 consulta + agrupamento Python | −0,15 a −0,25 s | baixo | 27 das 93 consultas (3 × 9 coleções) |
| 1.5 | Índice em `orderman_order.created_at` + `OrderItem.sku` | mata 13 mil seq scans/dia | baixo | `OrderItem.sku` é `db_index=False` |
| 1.6 | Memo de `ChannelConfig.for_channel`/`is_channel_active` por request | −5 consultas; limpa 100.974 seq scans/dia em tabela de 6 linhas | baixo | era o "causa não identificada" do WP §3.8 |
| 1.7 | Cortar duplicação do payload do cardápio (120 cópias de card; 85 KB de 135 KB são `sections`) | −100 a −200 ms, −63% bytes | médio (BE+FE atômico) | medido |
| 1.8 | **Devolver o preço ao primeiro quadro do cardápio** | regressão de UX do Continuum | decisão de produto | 44 placeholders, 0 `base_price_q` |
| 1.9 | Matar/alongar o poll canônico de 30 s (`menu.vue:260-267`) | corta ~metade da carga nova | baixo | ~4,7 s CPU/min por aba ≈ 7,7% de 1 vCPU |

**Cerca obrigatória:** cachear `build_catalog` foi **rejeitado** em 01/08 por vazamento de
preço/favoritos/carrinho entre clientes. Regra: **cachear estrutura pública, nunca estado de
sessão.** `build_shell` carrega `customer_name` — mesmo problema.

### Onda 2 — pipeline (o que o time sente)

| # | Ação | Ganho | Evidência |
|---|---|---|---|
| 2.1 | `-n auto` em `test-shop` e `test-storefront` — **os únicos dois alvos sem paralelismo** | **−8 a −16 min** no caminho crítico | Runtime Gate 23–31 min, `test-shop` 20–30 min |
| 2.2 | Pré-requisito de 2.1: `test_account_privacy.py:937` usa `uuid.uuid1()` em `parametrize` → coleta não-determinística | destrava 2.1 | reproduzido: 7 ERRORS |
| 2.3 | Escopo por diff nos gates caros (o padrão **já existe** em `operator-groups-gate.yml`) | tira 39 `npm ci` + 16 builds de PR que não toca front | nenhum gate caro tem path filter hoje |
| 2.4 | Parar de rodar o fan-out inteiro **duas vezes** (`pull_request` **e** `merge_group`) | ~metade do consumo, sem perder garantia | 6 workflows nos dois eventos |
| 2.5 | `buildx` + `cache-from/cache-to` nos 9 builds Docker frios | 9 builds por PR | só o deploy tem cache hoje |
| 2.6 | Desligar `OPERATOR_PER_APP_IMAGES` antes de 01/10 | 8 imagens publicadas que **nenhum spec referencia** | tags em `deploy-images.yml:55-79` |
| 2.7 | Podar o cache do Actions (12,28 GB contra teto de 10 GB) | hipótese forte do install de 3 min | despejo LRU |
| 2.8 | **Um deployment por run, não dez** (P5 do WP, nunca feito) | 391 deployments/7 dias → rajadas de 9–11 viram 1; 184 cancelados | 39 erros vieram todos do `release` |
| 2.9 | Remover duplicações (test-migrations em 2 workflows, 331 testes 2×, 4 `seed --flush`) | min-runner | medido |

**Meta:** PR com feedback em ≤ 6–8 min; merge queue ≤ 12–15 min **mantendo a suíte inteira**
na árvore que pousa.

### Onda 3 — fluxo de incremento sem fricção (coordenação)

O problema não é falta de regra — é que **a regra não tem mecanismo**. `CLAUDE.md` já descreve
tudo; `lease_id` não existe em lugar nenhum.

| # | Ação | Por quê |
|---|---|---|
| 3.1 | **`docs/coordination/IN-FLIGHT.md`** (claim de área): `make claim` / `make release`, materializando o lease **já desenhado** na §6 do programa R0–R8 | Trava de saída não impede dois trabalhos no mesmo arquivo; `inflight.sh` passa a cruzar worktree suja × lease → 🔴 COLISÃO |
| 3.2 | **`docs/coordination/DECISIONS.md`**: ledger append-only, vocabulário fechado (`DECIDIDA/EM_EXECUCAO/EXECUTADA/ADIADA/SUPERSEDIDA/BLOQUEADA`), `revisar_em` obrigatório | Plugar em `check_canonical_docs.py`, que **já roda no CI** |
| 3.3 | Gate de coerência: "não iniciado" no índice + branch ancestral do main ⇒ falha; ADR com número duplicado ⇒ falha; cada ⬜ exigindo `id` no ledger | Pega hoje: 2 planos mergeados marcados "não iniciado", 2 ADRs implementados marcados "Proposto", **dois `adr-026` e dois `adr-029`** |
| 3.4 | Resolver a duplicação de ledger (matriz × ledger; nenhum cita o outro) | Caso B2 do relatório 09 |
| 3.5 | `inflight.sh` declarar estado degradado quando `gh` falha | Hoje cai em `PRS="[]"` e mente |
| 3.6 | Retomar o WP de higiene com **trava**, não com mutirão | O volume **se repõe mais rápido do que a limpeza**: +22 worktrees e +33 branches em ~11h, no mesmo dia em que R7 foi declarado executado |

### Onda 4 — essenciais e corte de escopo

O registro que hoje governa o escopo é auto-bloqueante: `PRODUCT-V1-SCOPE-BACKLOG.md:77` diz que
o go-live só dispara com **todas** as 11 frentes entregues. `[FATO]` Essa regra precisa cair.

**Cortes propostos (do relatório 10, 13 no total):**

| Corte | Fundamento |
|---|---|
| **Marketing/WhatsApp fora da janela** | maior risco irreversível (B1) |
| **iFood fora** | homologação **nunca iniciada**; certificação é externa |
| **Media persistente** | raio de impacto = **1 campo** (`Shop.logo`); fotos já moram no repo |
| **Cupom no dia 1, teleporte/rating/troca de telefone** | zeram trabalho |
| **Machine, ManyChat** | desligamento de config |

**Caminho crítico de go-live (menor cadeia):**
`K0 escopo assinado → K1.1 resolver 403 do efi_webhook → K2 flip de env (1 spec, ~9 chaves)
→ K3.1 production-readiness --read-only verde → K4.1 canário de um → K5 tag + deploy`.

Só **K2 é engenharia nova**. O elo mais provável de atrasar é o 403 da Efí, sem diagnóstico
desde 22/09.

---

## 4. As duas queixas operacionais pontuais

### 4.1 "Só funciona no segundo clique" — dois bugs distintos

- **Bug A (com alerta):** o clique 1 é o único que faz handshake. Semente de CSRF no cliente
  (`useShopmanCsrfHeaders.ts:17-20`, com erro **engolido** por `.catch(() => null)`), segunda
  semente no BFF (`djangoProxy.ts:191-196`), e a resposta ainda monta a projeção completa do
  carrinho. **Clique 1 = 2 a 6 chamadas; clique 2 = 1.** A medição já existe e ninguém usa:
  `bff;dur` do BFF inclui a semente no 1º PUT e não no 2º. `[FATO]`
- **Bug B (sem alerta):** botão `disabled` até a hidratação → no-op silencioso. `[FATO]`
- **Armadilhas provadas:** lost update (`queueDepth` checado **na chegada**, não no disparo) e
  decremento duplo sem `finally` — o carrinho para de reconciliar. `[FATO]`
- **Lacuna estrutural:** nenhum teste cobre o clique 1 sem cookie — 10 arquivos semeiam
  `csrftoken` no `beforeEach`. A assimetria é invisível para a suíte **por construção**.

### 4.2 PWA travado — risco de cliente real

Aviso dispara **uma vez** (`PwaUpdateToast.vue:7`), é descartável, e **nada sonda versão**
(`usePwaUpdate.ts` tem 10 linhas; `registration.update()` nunca é chamado).
Nenhum fetch tem timeout no BFF (`djangoProxy.ts:202-207`) nem no shell → "tela travada" é literal.
Não há identidade de versão no cliente (o Django **já aceita** `app_version`; ninguém envia) e
não há kill switch.

**O `operator-kit` já resolveu o mesmo incidente em 17/09** (sonda de 30 min + banner
persistente + telemetria, `pwaRuntime.ts:5-7`). **Portar, não reinventar** — sem auto-reload
ocioso no storefront.

---

## 5. As duas decisões de produto pendentes

Ambas devem ser decididas **na mesma mesa** — a segunda depende da primeira.

### D1 — Forma de pagamento padrão na loja online

O Pix é o primeiro da lista `["pix","card"]`, e **posição vira default em 3 saltos**
(`config.py:92-120` → `presentation/checkout.py:445-452` → `finalizar.vue:743-745`).
A ordem foi decidida **para o concierge do WhatsApp**, onde o bot *pergunta*. O formulário web
herdou a ordem e a converteu em escolha silenciosa. Não existe plano/ADR que decida isso.

**Fato que muda o diagnóstico:** o backend **não inventa** forma de pagamento (obrigatório no
serializer, revalidado, com teste travando 400). **O default é 100% decisão de front** — corrigir
só o backend não resolve, e o `|| methods[0]?.ref` em `finalizar.vue:744` fecha a porta de
qualquer correção parcial.

**Risco real:** o pedido nasce em `new` com **estoque reservado na transação do commit**
(backstop 48 h); **nenhuma cobrança nasce no checkout** (só no aceite do operador, por 10 min);
entre confirmar e aceitar o cliente vê "Estamos conferindo a disponibilidade" — **sem QR, sem a
palavra Pix, sem prazo**. Reversível pelo cancelamento, **não pela forma**.

**Contraste:** o PDV começa `paymentTenders: []` e o concierge exige escolha explícita. O web é
a **única** superfície que decide pelo cliente. Aplicar rigor menor ao cliente do que ao
operador, justamente no dinheiro, é incoerente.

**Recomendação (B):** default **só quando foi dito** (preferência lembrada do cliente, ou
`payment.default_method` declarado e validado em config); `is_default` dinâmico; **remover o
fallback `methods[0]`**; e tornar a forma audível no resumo com troca em 1 clique sempre
disponível. Alternativa A (nunca pré-selecionar) é coerente mas descarta a preferência lembrada;
C (só tornar visível) **não resolve**, porque a falha é atencional, não informacional.

**Pergunta ao dono:** a casa quer um default? Sem essa resposta, B entrega "sem default".

### D2 — Alterar pedido da loja online pelo Gestor

**O mecanismo canônico já existe e não é exclusivo de encomenda.** O `Order` fica selado
(`SEALED_FIELDS`) e a alteração vive ao lado, em `Order.data["adjustment"]`, com **um único
escritor** (`order_composition.record`) e **um único caminho de leitura**
(`effective_items()`/`effective_total_q()`). A regra é `shopman/shop/services/order_edit.py`
(`plan` = prévia que nada grava; `edit` = sob lock, transacional), reconciliando estoque e
cozinha pelo **mesmo caminho do `ORDER_PATCHED` do iFood**. O corte é status (`new|accepted|
preparing`), canal iFood, pedido de teste e NFC-e autorizada. `[FATO]`

**O que falta não é mecanismo, é exposição** — declarada fora de escopo por escrito em
`ENCOMENDAS-PDV-PLAN.md:229`. O servidor só monta o bloco `counter` no contexto `"pos"`, e
nenhuma tela de `orders-nuxt` chama as rotas. Há até **um teste prendendo isso**
(`test_order_detail_context.py:90`).

⚠️ **A porta já tem a permissão do Gestor** (`shop.manage_orders`) e `revisions.edit` **já chega**
ao detalhe do Gestor — é o `base_revision` que a edição exige.

⚠️ **Mas "alterar a forma de pagamento" NÃO é coberto.** `order_edit` mexe no **valor** e no
destino da diferença; nunca reescreve a **forma** de um pedido cujo valor não muda. Isso é
**capacidade nova, não transposição**.

**Sequência proposta:** R1 expor os gestos no Gestor (alto/baixo) → R2 "Reagendar" (médio-alto/baixo)
→ R3 editar itens (decidir entre deep-link para o PDV ou editor no Gestor) → R4 desenhar troca de
forma de pagamento com **uma das três semânticas**: (i) cobrança pendente, (ii) pedido já pago
(estornar+recobrar), (iii) no ato (já existe).

**Perguntas ao dono:** (1) qual das três semânticas? (2) pedido imediato entra, ou só com data?
(3) quem opera o Gestor tem caixa aberto? (4) o Gestor é a superfície do atendimento por WhatsApp?

---

## 6. Riscos de regressão silenciosa

- **O contrato FE↔BE do PDV é manual.** `posContract.ts` tem **14 linhas** (só enums); a forma da
  projection está em `app/types/pos.ts`, **345 chaves escritas à mão**, sem nenhum teste que a
  ligue ao backend. **74 dessas chaves nunca são nomeadas por teste algum.** Um rename
  coordenado **passa por todos os gates** e quebra no balcão — exatamente o defeito de 26/08 que
  o contrato compartilhado foi criado para fechar: fechado no storefront, **aberto no PDV**.
  Fix barato: `export_pos_schema` já existe; falta gerar as dataclasses como os outros 6 já fazem.
- **Zero `assertNumQueries` no repositório inteiro**, e nenhum budget de queries no caminho do
  dinheiro. Produção dá 93–94 consultas; o único guard manual mede fixture e aceita `n<=55`.
- **Nenhum browser vende no PDV.** O gate de browser só navega e audita DOM; 14 specs Playwright
  existem e **nenhum roda** (vitest exclui `tests/e2e/**`).
- **A suíte alpha do storefront não roda na CI**, e o `criticalFlow.spec.ts` está `skip` permanente.
- **`make test` verde ≠ PR verde** (9 gates fora do alvo) e `make lint` não passa `ruff` em
  `shopman/storefront/` nem `backstage/`.
- **~30 mil 403/dia invisíveis** no log (WARNING não chega ao Sentry; sem alerta).

**Camada que protege SEM encarecer:** `-n auto` (**encurta**), gates baratos no `make test`,
asserção de contrato no `alpha-smoke` pós-deploy, `django_assert_num_queries` dentro de testes
que já rodam (custo zero), `make contracts-check` no job `Quality` que já existe.

---

## 7. Decisões perdidas silenciosamente — o padrão

O padrão **não é esquecer**: é que **o registro não é a verdade**. Casos verificados:

| # | Decisão | Evidência de que não foi feita |
|---|---|---|
| 1 | **`WP-PERFORMANCE-2026-09`** (17/09): 9 itens medidos e priorizados | **Só P1 e P2 executados.** P3/P4/P5/P6 parados — inclusive o P5 (cascata de deploys) |
| 2 | **`fallbacks-perigosos-go-live.md`**: 12 itens ⬜ | **9 abertos sem dono** — e **3 já corrigidos que continuam ⬜** (o doc erra nas duas direções) |
| 3 | Dois ledgers canônicos concorrentes | Cada um se declara "única fonte"; **nenhum cita o outro**; nenhum índice; fora do `check_canonical_docs` |
| 4 | `plans/README.md:31,70` | Diz "não iniciado" para **dois planos já mergeados** |
| 5 | ADR-018 e ADR-019 "Proposto" desde 08/08 | **Implementados** (o código cita "ADR-018 §3") |
| 6 | Colisão de numeração | **Dois `adr-026` e dois `adr-029`** num esquema que o README chama de "endereço" |
| 7 | Decisão do dono | Enterrada em runbook de Sentry, "sem lugar melhor para morar", 18 dias, três lugares, nenhum dono |

**Mecanismo proposto:** Onda 3 (ledger + claim + gate). Não é regra nova — é dar mecanismo à
regra que já existe, plugando no `check_canonical_docs.py` que **já roda no CI**.

---

## 8. Organização do trabalho

### Frentes propostas (uma = um branch = um PR)

| Frente | Escopo | Depende de | Paralelizável |
|---|---|---|---|
| **F0 · contenção** | B1, B2, B3 (env, não código) | `gh` reautenticado | imediato |
| **F1 · borda** | cache público + remover `csrftoken` do GET anônimo | — | sim |
| **F2 · disponibilidade** | 1× por request (Core — **revisão obrigatória**) | F1 medindo | não (Core) |
| **F3 · home** | `home/` deixa de construir o catálogo | — | sim |
| **F4 · índices** | `orderman_order.created_at`, `OrderItem.sku`, memo de `Channel` | — | sim |
| **F5 · instrumentação** | `Server-Timing` em home/shell/site/cart/checkout/tracking | — | sim (habilitador) |
| **F6 · CI** | `-n auto` + escopo por diff + 1 deploy/run | F6.0 (`uuid1` no parametrize) | sim |
| **F7 · coordenação** | ledger + claim + gate | `gh` | sim |
| **F8 · PWA** | portar sonda/banner do kit + timeouts + identidade de versão | — | sim |
| **F9 · carrinho** | remover semente de CSRF do cliente + botão antes da hidratação | — | sim |
| **F10 · contrato PDV** | gerar dataclasses da projection do POS | — | sim |

### Ordem recomendada

`F0` primeiro (é contenção e não depende de código). Depois **`F1` sozinho** — é o maior ganho
isolado, e sozinho já leva o visitante anônimo ao alvo. `F5` em paralelo desde o início, porque
**sem ele o ganho de F1–F4 não é demonstrável**. `F2` só com revisão de Core. `F6`/F7 podem
rodar em paralelo a tudo. `F8`–`F10` são independentes e de risco baixo.

### Regras de convivência (já escritas no `AGENTS.md`; aqui viram critério)

1. Uma frente = um branch = um PR. Nada termina dormente.
2. Antes de abrir frente, `make inflight` + `gh pr list`. **Chip que duplica PR aberto se dispensa.**
3. `git add` só com arquivo nomeado; nunca `-A`/`.`/`-u` no principal.
4. Conflito se resolve no branch, nunca no principal.
5. Migração: checar colisão de numeração antes do PR.
6. Números canônicos precisam de correção: o `CLAUDE.md` diz **"~6.500 testes"** e a suíte tem
   **23.045** (3,5×). É o número usado para calibrar orçamento de CI.

---

## 9. Como saberemos que funcionou

| Métrica | Hoje | Alvo | Como medir |
|---|---|---|---|
| `menu/` TTFB (anônimo) | 2,6–4,4 s | **≤ 0,6 s** | `curl -w` + `cf-cache-status` |
| home SSR TTFB | 3,9–4,4 s | **≤ 1,2 s** | `curl -w` |
| Consultas por request de cardápio | 93 | ≤ 35 | log `storefront_catalog_observation` |
| `test-shop` no caminho crítico | 20–30 min | ≤ 8 min | `gh run view` |
| PR → feedback | runtime 23–31 min | ≤ 6–8 min | `gh run view` |
| Deployments por run | 9–11 | **1** | `doctl apps list-deployments` |
| Branches fora do main | 115 / 1.093 commits | a definir | `make inflight` |

**Infraestrutura de medição mínima** (não compra ferramenta, não pede acesso novo):
generalizar `scripts/evaluate_continuum_shadow.py` (já existe, lê `doctl apps logs`, calcula
p50/p75/p95, falha fechado) para `(path, mode)` com thresholds versionados + `%{time_starttransfer}`
no smoke pós-deploy + `make perf-window`. **~200 linhas e dois passos de workflow.**

---

## 10. O que não foi possível verificar

- **Estado de PR/branch protection:** `gh` sem autenticação. Os "21 checks obrigatórios" e
  `enforce_admins` são **[NÃO VERIFICADO]**.
- **Contagem de linhas de `stockman_quant`/`orderman_order` no alpha:** sem credencial de banco.
  É a medição que mais fecharia o diagnóstico da onda 1.
- **`doctl databases list` e API de monitoring da DO: 403** com o token desta máquina. P0 do
  `WP-PERFORMANCE` (observabilidade de query) **não é executável por agente** — precisa de
  credencial do dono.
- **`waitlist` ligada no alpha?** Default é `False`, mas o canal `web` pode sobrescrever pelo
  banco. Decide se a 2ª passada de disponibilidade está ativa hoje.
- **Efeito do Django 6.0.8→6.1.1** (19/09) sobre a regressão: **[NÃO VERIFICADO]**.
- **Se `SENTRY_DSN` colado é válido** e se eventos chegam.
- Toda medição ao vivo é de ~16:20 UTC de 29/09, com ~8–12 amostras por URL. **Não é p50/p95 de
  tráfego.** Uma segunda janela de medição é necessária para separar carga de horário de regressão.

---

## 11. Próximo passo imediato

1. `gh auth login` (destrava todo o resto — inclusive a leitura de PRs).
2. Onda 0: B1, B2, B3.
3. Ler `storefront_catalog_observation` no log de produção (custo zero, decide a prioridade da
   onda 1 inteira).
4. Assinar o corte de escopo da Onda 4 (a regra "todas as 11 frentes" precisa cair).
5. Abrir as frentes F1, F5, F8, F9, F10 em paralelo.
