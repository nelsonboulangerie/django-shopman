# Reavaliação Agente D — WPs de Auditoria dos Apps do Backstage

**Data:** 2026-08-30 · **Autor:** Agente D (revisão da auditoria do Agente G, 2026-08-29)
**Originais intactos:** `docs/plans/backstage-app-audits-2026-08-29/WP-01..09` — **não foram tocados.**
**Versões revisadas:** este diretório (`agente_d/`) — `WP-01-agente-d-*.md` … `WP-09-agente-d-*.md`.

---

## 1. Veredito geral

O Agente G entregou **a melhor auditoria de superfície que este repositório já recebeu** — e isso precisa ser dito primeiro. Nove WPs com fronteira natural declarada, evidências ancoradas em `arquivo:linha`, aceites por achado, testes por achado, "Fora de Escopo" explícito e prompt executor padronizado. A verificação independente (9 agentes de leitura de código, 70 evidências conferidas) encontrou **≈ 95% das evidências reais e corretamente descritas**, incluindo os achados mais graves do sistema hoje:

- `bool("false")` marca item do KDS como checked (WP-04) — bug real de uma linha, em produção.
- `confirm_receipt` confia no payload do browser para gravar estoque e aprender de-para fiscal (WP-06) — P0 real.
- Refund no Admin executável por **qualquer staff com view** (WP-09) — pior do que o WP pinta.
- Cancelamento de pedido que devolve **200 "ok" sem efeito** para status não-canceláveis (WP-03) — achado perdido pelo WP, mais grave que tudo que ele listou.
- SSE do KDS vazando `session_key` + `order_ref` para qualquer `operate_kds` (WP-04) — achado perdido.
- Dois resolvers de terminal default **divergentes** no POS, podendo operar dinheiro no caixa errado sem erro (WP-02) — achado perdido.

**O que a revisão muda não é o diagnóstico — é a prescrição.** O Agente G acertou o raio-X e errou em cinco dimensões: (1) enquadrou decisões de design documentadas como bug; (2) escreveu aceites que contradizem o código ou o próprio produto; (3) criou permissões novas sem tocar no `setup_groups` (dono único do RBAC); (4) não declarou dependências entre WPs nem donos de fronteira para modelos/permissões novos; (5) não diferenciou risco × esforço (um P1 de uma linha convive com uma "melhoria UX" de semanas).

As versões `agente_d` corrigem exatamente isso: achados recalibrados, aceites verificáveis, dependências explícitas, `setup_groups` em todo WP que cria permissão, e priorização por risco×esforço.

## 2. O que está corretamente colocado (méritos, confirmados na verificação)

| # | Mérito | Confirmação |
|---|---|---|
| 1 | **Template único e executável** (Status/Superfície/Objetivo/Fronteira/Evidências/Achados/UX/Testes/Fora de Escopo/Prompt) nos 9 WPs | Padrão consistente; "Fora de Escopo" presente em todos |
| 2 | **Evidências ancoradas em arquivo:linha** | 70 evidências verificadas; ≈95% reais (tabela §5) |
| 3 | **As 4 invariantes do README** (identidade operacional, servidor decide capacidade, sem efeito irreversível sem contrato, UX de chão de loja) | Princípios corretos e bem aplicados nos achados |
| 4 | **Achados P0 de segurança/integridade reais** | WP-06 (recebimento), WP-09 (refund) — confirmados e até subestimados |
| 5 | **Ordem recomendada** (P0 → contrato compartilhado → estação → P1 permissões → UX) | Sensata; a revisão só adiciona dependências explícitas (§6) |
| 6 | **Fronteira natural declarada em cada WP** | Em geral respeitada; as exceções estão listadas em §3.5 |
| 7 | **Permissões finas como tema transversal** | É o problema mais real do backstage hoje (permissão única em orders/marketing/purchase) |

## 3. Críticas transversais (o que merece ajuste)

### 3.1 — `setup_groups` nunca é mencionado (lacuna mais grave)

Seis dos nove WPs criam permissões novas (03, 04, 05, 06, 08, 09). O repositório tem **um dono único de grupos RBAC** — `shopman/shop/management/commands/setup_groups.py` — com teste de paridade (`tests/test_group_permission_parity.py`) que **falha se uma permissão que gateia superfície não é concedida a ninguém**, e com semântica `set` (dono também tira). Nenhum WP do Agente G lê esse arquivo. Consequências:

- Permissão nova não concedida a grupo → app inalcançável e CI vermelha (o teste de paridade pega).
- Permissão nova concedida sem pensar no "Caixa"/"Gerente"/"Cozinha" → operador perde ou ganha capacidade por acidente.
- Separar `settle_delivery_cash` de `manage_orders` (WP-03) tem blast radius nas personas que **já** detêm as duas (grupo Caixa recebe `manage_orders` + `operate_pos`).

**Correção agente_d:** todo WP que cria permissão carrega uma seção "RBAC / `setup_groups`" com a matriz de grupos afetados.

### 3.2 — Decisões de design documentadas tratadas como bug

O Agente G várias vezes pintou como falha o que o código **decidiu de propósito e documentou**:

| WP | Caso | Decisão documentada | Leitura correta |
|---|---|---|---|
| 04 | SSE autoriza por tipo de canal, não por ref | ADR-016: canal é push de um fetch canônico; o fetch faz o gate fino (`eventstream.py:100-101`) | O achado real é o **payload** vazar `session_key`/`order_ref` (`_sse_emitters.py:396`) — o WP nem listou |
| 02 | Terminal default | `Terminal.default()` existe de propósito: "loja com um só balcão não deve precisar cadastrar terminal" (`terminal.py:44-55`) | O problema é **dois resolvers divergirem** com 2+ terminais, não o default em si |
| 02 | `open_cash_shift` clampa negativo em zero | O módulo documenta "devolver 0 silencioso transformaria um typo numa diferença gigante sem aviso" (`services/pos.py:24-29`) | O WP acertou o sintoma; a correção é rejeitar (400), não só "auditar" |
| 07 | Data inválida cai no default | `bi.py:52`: "janela inválida cai no default — a projection normaliza" | 400 seco reverte decisão; o meio-termo é `normalized_window_reason` no contrato |
| 08 | Approve respeita `publish_at` | `campaign.py:810-820` é coerente com a docstring | O bug é a **UI** não mandar `publish_now` (zero ocorrências da flag no frontend) |
| 05 | `check_finish_materials` fail-open | Modo `MODE=strict` fail-closed é intencional e testado; graceful sem backend é design (`production.py:672-678`) | O fail-open real é `_check_linked_order_coverage`, incondicional |

### 3.3 — Aceites contraditórios ou inverificáveis

| WP | Aceite do Agente G | Problema |
|---|---|---|
| 08 | "O número planejado nas ondas bate com a audiência confirmada" | O código **re-resolve a audiência na hora do envio de propósito** (favoritos/alertas mudam). "Bater" exige congelar (freeze) — decisão de produto não tomada |
| 08 | "Usuário que edita não necessariamente dispara" | Colide com approve-with-edits: o card sempre envia edições junto da aprovação |
| 06 | "Sem `approve_purchase` não envia compra acima da política" | `approve_purchase` **não existe** e "política" também não — aceite referencia infra que o próprio WP não cria |
| 03 | "UI não oferece cancelamento proibido" | Contradiz decisão explícita no código: "depois do aceite, Cancelar segue sempre disponível" (`[ref].vue:217-218`) |
| 04 | "Estação A não assina SSE B" | Colide com expedição global (board expedition é global por design) |
| 09 | "Ampliar gate para `packages/*/admin.py`" + "`make admin` final obrigatório" | Ampliar o gate hoje **quebra** `make admin` (dezenas de violações em doorman/orderman/guestman) — o WP não dimensiona a migração |
| 01 | "Tile renderiza `forbidden`/`missing_url`" | Contradiz o contrato "tiles já vêm FILTRADOS: se está na lista, o operador pode abrir" (`hub.ts:2-3`) e vaza nomes de superfície |
| 07 | "Cenário salvo mostra a janela exata usada" | A API lê a janela de `request.GET` num POST (`bi.py:376-377`) — a proposta "envia `useBiWindow().range`" não funciona sem mudar a API |

### 3.4 — Dependências entre WPs não declaradas

- **WP-06 P0-1 (ReceiptDraft)** é pré-requisito do aceite de conversão ("divergente sem justificativa não confirma") — o servidor hoje não persiste a sugestão da NF, então o aceite é inverificável sem o draft. Não declarado.
- **WP-04 P1 (estação vinculada)** é pré-requisito da UX "estação lacrada" — sem vínculo operador→estação não existe "estação correta" para mostrar. Não declarado.
- **WP-09 "ampliar gate"** depende de reescrever ou emitir waiver para 7+ admins planos — o WP trata como detalhe.
- **WP-01 "Hub no check de domínio"** exige criar `SHOPMAN_HUB_BASE_URL` — **não existe** setting do host da Central hoje.
- **WP-05 expected_rev** atravessa backstage → orquestrador (`shop/services/production.py`) → craftsman core → contrato TS (`rev` não existe no card; regerar via `export_production_schema`). O WP diz "não mova cadastro canonico" mas não diz que a mutation é multi-dono.

### 3.5 — Fronteiras de dono não nomeadas

- **WP-09**: refund = payman/doorman (permissão nova em modelo de core); PII/masking = guestman; TrustedDevice = doorman; import/export = offerman. O WP é dono do *gate canônico*, mas as permissões/modelos que propõe são de outros donos — precisa declarar.
- **WP-04**: "vincular KDSInstance a Terminal" acopla o domínio caixa (cashman); a solução certa é `station_ref`/allowlist dentro do backstage.
- **WP-06**: `ReceiptDraft`/`PurchaseReceipt`/`SupplierCostObservation` não têm dono declarado (buyman? backstage?); o WP diz "consumir Buyman" mas propõe modelos no core.
- **WP-01**: "Leve-me ao gargalo" exige ler orderman/cashman/buyman/craftsman — cada app deve expor seu próprio summary, o Hub não agrega.
- **WP-02**: contrato `manager_approval` unificado mora no orquestrador (shop), dono único declarado — o WP deve nomear.

### 3.6 — Prioridade ≠ risco × esforço

- `bool("false")` (WP-04) é P1 mas é **fix de 1 linha com teste** — deveria ser P0 de impacto e trivial.
- "Leve-me ao gargalo" (WP-01) é melhoria cara e arriscada tratada como UX simples — deveria ser backlog ou resumo por app.
- "Manifest de actions" (WP-02/03) é infra **pré-requisito** para vários aceites — tratado como P2.
- WP-05 propõe ~11 permissões novas quando as perms por coluna (`shop.view/edit_production_*`) já existem e resolvem 90% — risco de permission sprawl sem ganho.

### 3.7 — Subestimação de gravidade (2 achados piores que descritos)

- **WP-09 refund**: "sem permissão dedicada clara" → na verdade **view-only executa refund** (Django roda actions no changelist sem checar `has_change_permission`; sem `allowed_permissions`). Import/export idem: `django-import-export` default é `has_import_permission=True`.
- **WP-03 cancelamento**: "backend falha depois" → na verdade **falso-sucesso**: `cancellation.cancel` retorna `False` sem levantar, `cancel_order` descarta o retorno e a view responde `200 {"ok": True}`.

### 3.8 — O que o Agente G perdeu (achados novos incorporados aos WPs agente_d)

| WP | Achado novo (verificado) |
|---|---|
| 01 | Spec e2e `hub.spec.ts` também stale (href `/admin/shop/shop/` + `target=_blank` inconsistente); zero cobertura de teste para o grant customizado de Produção |
| 02 | **Dois resolvers de terminal default divergentes**; desconto persiste `approved_by` do username cru do payload (validar A, persistir B); review vs close divergem (warning vs erro) |
| 03 | **Cancelamento falso-sucesso 200 ok**; resíduo `confirmed` no STATUS_TONE (zero-residuals); iFood vira free-text quando reasons falha; `save_kitchen_note` sem auditoria |
| 04 | **SSE kds vaza `session_key` + `order_ref`**; ref inexistente → 500 (não 404); board expedition global |
| 05 | **Mutations sem perms finas de edição** (`view_planned` consegue plan/start/finish); `ProductionKDSView` com `can_finish` sempre True; race no board (500) |
| 06 | **Escrita silenciosa em dado mestre** (cost_q/conversion sobrescritos, pode zerar conversão; `prefer_if_missing` auto-promove); **número exibido ≠ número despachado** na reposição; scan cria fornecedor implicitamente |
| 07 | **Egress de financeiro para provedor de IA** (`scenarios.py:94-128`); aba Caixa sem gate client-side; save de cenário audit-only não bloqueado |
| 08 | **Test-send sem restrição de destino** (qualquer número); approve não re-valida audiência; `publish_at` no passado vira publish-now silencioso; CampaignForm descarta 8+ chaves de audiência |
| 09 | **Segredos de gateway expostos a view-only** (`client_secret`/qrcode/txid); `reset_pin` sem LogEntry; TrustedDevice deletável |

## 4. Como usar os WPs agente_d

Cada `WP-0X-agente-d-*.md` é **autocontido e executável** (mesmo template do Agente G), precedido de uma seção **"Diferenças vs. WP original"** que lista: achados mantidos (validados), recalibrados (com o porquê), removidos (com o porquê), e novos. Os originais seguem intactos na pasta-pai.

Convenções aplicadas em todos:

- **`setup_groups`**: seção obrigatória quando o WP cria permissão — matriz de grupos e aviso do teste de paridade.
- **Dependências**: seção "Pré-requisitos" listando WPs/blocos que precisam vir antes.
- **Aceites**: reescritos para serem verificáveis contra o código atual (nada de referenciar infra inexistente).
- **Fronteira de dono**: modelos/permissões novos declaram o dono e o que o WP pede a ele.

## 5. Tabela de verificação das evidências (Agente G)

| WP | Evidências | Confirmadas | Parciais | Incorretas | Não localizadas |
|---|---|---|---|---|---|
| 01 Hub | 7 | 7 | — | — | — |
| 02 POS | 7 | 5 | 2 | — | — |
| 03 Gestor | 8 | 8 | — | — | — |
| 04 KDS | 7 | 7 | — | — | — |
| 05 Produção | 9 | 8 | 1 | — | — |
| 06 Compras | 7 | 7 | — | — | — |
| 07 BI | 9 | 9 | — | — | — |
| 08 Marketing | 8 | 7 | 1 | — | — |
| 09 Admin | 8 | 8 | — | — | — |
| **Total** | **70** | **66** | **4** | **0** | **0** |

Parciais: WP-02 E3 (default de turno é decisão documentada) e E6 (fire já idempotente via ledger KDS); WP-05 E8 (force é lenient mas cliente envia boolean real); WP-08 E5 (ondas divergem mas não perdem mensagem no caminho comum).

## 6. Ordem de execução revisada (com dependências)

1. **P0 isolados, independentes:** WP-04 `bool("false")` (1 linha) · WP-03 cancelamento falso-sucesso · WP-09 refund view-only + import/export aberto · WP-06 ReceiptDraft+idempotência · WP-02 resolver único de terminal.
2. **Contrato compartilhado (pré-requisito):** manifest de actions/payloads (WP-02+WP-03+WP-05) definido **uma vez** — ver `WP-02-agente-d-pos.md` §"Contrato de actions" — antes dos aceites que dependem dele.
3. **Estação e identidade:** WP-04 estação vinculada (depende do 2 para payload mínimo) · WP-02 terminal por estação · WP-01 tile Produção por permissão real (inclui criar config do host do Hub).
4. **Permissões finas com `setup_groups`:** WP-03, WP-05, WP-06, WP-08, WP-09 — cada um com matriz de grupos e teste de paridade.
5. **UX de excelência:** semáforos, preflights, outbox, dry-run, undo — último, porque dependem dos contratos.

## 7. Método desta revisão

- 9 agentes independentes de verificação de código (um por WP) leram cada evidência citada, a função inteira (não só a linha) e classificaram: confirmada / parcial / incorreta / não localizada, além de reportar achados perdidos, invasões de fronteira e aceites problemáticos.
- Verificações adicionais do Agente D: `setup_groups`, `permissions.py`, `hub.py`, `operator-kit/httpError.ts`, `eventstream.py`, `operations.py` (POS/Orders/Production), `purchase.py`, `bi_customers.py`, `bi_explore.py`, `checks.py`, `Terminal` (cashman).
- Nenhuma evidência do Agente G foi desmentida; quatro foram qualificadas com nuance material.
