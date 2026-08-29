# WP-07-agente-d — BI

**Status:** pronto para implementação · **Autor:** Agente D (revisão do WP-07 do Agente G)
**Superfície:** 'surfaces/bi-nuxt' + endpoints 'api/v1/backstage/bi/*'
**Objetivo:** fazer o BI responder perguntas de gestão sem falsa confiança, vazamento de PII/financeiro (inclusive para o provedor de IA) ou ação fora do domínio dono.

## Diferenças vs. WP original (Agente G)

**Mantidos (validados):** explorador pode oferecer exemplo sem métrica permitida (exemplo estático de quebra de caixa visível a qualquer um — clicar vira 403; contradiz a docstring "a tela não oferece o que a API vai recusar", 'bi.py:135-136'); Clientes mistura janela e global (4 de 5 KPIs globais — 'bi_customers.py:48,75,90,93'); cenários IA não enviam janela; alertas BI podem vazar valores financeiros; datas inválidas viram default silencioso; sem regra de célula mínima.

**Recalibrados / agravados:**
- **P1 exemplos/saved views** — mantido + agravado: o **save** de cenário com métrica audit-only **não é bloqueado** ('_validated_view_config' valida só gramática — 'bi.py:254-272'); quem perdeu 'audit_shift' continua vendo as próprias views salvas com 'cash_difference'. O filtro precisa rodar no list/apply contra permissão **corrente**.
- **P1 alertas** — nuance material: 'cash_variance_by_drawer' **já está mitigado** (mensagem pública sem nome/valor — 'bi/alerts.py:115-130'; detalhe no 'BIAlertEvent' gateado). O vazamento real é 'daily_revenue_vs_baseline': '_brl(measured)'/'_brl(baseline)' na mensagem ('bi/alerts.py:216-218') → 'OperatorAlert' → '/api/v1/backstage/alerts/' gateado por **qualquer** capacidade de operador ('permissions.py:120-129', conjunto maior que 'view_bi') — operador de PDV/KDS sem 'view_bi' recebe faturamento em R$.
- **P2 datas inválidas → 400** — reverte decisão documentada DUAS vezes ("janela inválida cai no default", 'bi.py:52' e 'bi_production.py:178-186'). Reformulado: manter normalização, mas expor 'normalized_window_reason' no contrato; 400 seco só para campos de horizon/target que fazem sentido falhar.
- **P2 célula mínima (n<k)** — mantido com custo declarado: as projeções **não expõem contagem de pedidos por bucket** ('_payment_rows'/'_sales_rows' sem n) — exige contar 'n' por bucket em cada família sensível. Risco de estourar o escopo; escopar a famílias financeiras.
- **P1 cenários IA** — a proposta "envia 'useBiWindow().range'" **não funciona**: a API lê a janela de 'request.GET' num POST ('bi.py:376-377') — body seria ignorado. Precisa mudar a API (janela explícita no body) + persistir a janela **efetiva** (hoje grava a bruta — 'scenarios.py:236-237' vs efetiva em 'inputs.window' :101) + exibir na UI (hoje nem mostra).

**Novos (achados da verificação):**
- **Egress de agregados financeiros para o provedor de IA**: '_sales_inputs' envia faturamento por dia/canal/top produtos (com nomes de SKU) para 'copy_assist' → 'AI_ASSIST_API_KEY' ('scenarios.py:94-128') — o objetivo do WP cita PII/financeiro e nenhum achado trata disso.
- **Aba "Caixa" sem gate client-side** ('BiTopBar.vue:30'): visível a qualquer 'view_bi'; não-auditor leva 403 genérico; a API não expõe flag de capacidade de auditoria em payload nenhum — a UI não tem como esconder.
- 'average_ticket_q' de Clientes = média não-ponderada de médias com divisão inteira ('bi_customers.py:93') — menor.
- Descarte verificado: SSE '/events/<kind>/' **não** é achado (canais gateados com as mesmas permissões das views; payload = sinal mínimo).

## Fronteira Natural

BI é camada de leitura gerencial sobre fatos de outros domínios. Não abre caixa, não corrige contagem, não edita pedido, não comanda produção, não cria compra, não muda estoque e não dispara campanha. **Se "Clientes" implicar segmentos RFM por janela, o dado pertence ao guestman** ('CustomerInsight' é agregado dele; o BI "só lê, nunca recalcula" — 'bi_customers.py:1-6'). **Alertas**: o detalhe sensível vive fora do bus compartilhado ('OperatorAlert', consumido por orders-nuxt/production-nuxt) — coordenação de superfície, não outro app.

## Evidências (verificadas)

- Gate comum 'view_bi': 'shopman/backstage/api/bi.py:38-42'.
- Caixa exige 'cashman.audit_shift' adicional: 'bi.py:94-99' (tupla = AND).
- API poda métricas audit-only: 'bi.py:157-161'; pedido direto = 403: ':142-146'.
- 'AUDIT_ONLY_FAMILIES = {"cash"}': 'projections/bi_explore.py:224'.
- Exemplo estático de quebra de caixa: 'surfaces/bi-nuxt/app/presentation/bi.ts:246'; 'availableExamples' filtra dimensão, não métrica: ':184-196'.
- Clientes: globais vs janela: 'projections/bi_customers.py:48,75,90,93'.
- Cenários: POST só 'focus' ('useBiScenarios.ts:17-20'); API lê 'request.GET' ('bi.py:376-377'); grava janela bruta ('scenarios.py:236-237').
- Alerta financeiro com '_brl': 'bi/alerts.py:216-218'; gate amplo: 'permissions.py:120-129'.
- Save sem checar auditoria: 'bi.py:254-272'.

## Achados Priorizados

### P1 — Explorador pode oferecer exemplo sem métrica permitida (e salvar sem checar)

Proposta:
- 'availableExamples' valida métrica contra 'report.metrics' (já podado no servidor).
- **Bloquear no save**: '_validated_view_config' rejeita métrica audit-only para não-auditor.
- Saved views com métricas proibidas: filtradas no list e no apply, contra permissão **corrente** (quem perdeu 'audit_shift' não continua vendo as próprias views).
- API expõe flag 'can_audit_cash' (para a UI poder esconder a aba Caixa — achado novo).

Aceite:
- Usuário sem 'cashman.audit_shift' não vê exemplo, não salva e não aplica view com 'cash_difference'.
- Quem perdeu 'audit_shift' perde também o acesso às views salvas com métrica audit-only (teste).
- A aba Caixa some para não-auditor (sem 403 genérico).

### P1 — Clientes mistura período com métricas globais

Proposta:
- Campos ganham 'scope: "global" | "window"' no contrato do relatório.
- UI separa "base atual" (global) de "no período" (window).
- **Não** recalcular RFM por janela (dono: guestman) — apenas rotular.

Aceite:
- Alterar janela não faz número global parecer recorte (teste de contrato).
- Nenhum agregado novo de guestman é criado neste WP.

### P1 — Cenários IA podem não representar janela visível

Proposta:
- API passa a aceitar janela explícita no **body** do POST (corrigir o contrato GET-em-POST).
- 'useBiScenarios.generate()' envia 'useBiWindow().range'.
- Persistir a janela **efetiva** (pós-normalização, via 'inputs.window'), não a bruta.
- UI exibe 'window_from/to' do cenário salvo.

Aceite:
- Cenário salvo mostra a janela exata usada para o cálculo (teste round-trip).
- POST sem janela continua caindo no default documentado (28d).

### P1 — Alertas BI podem vazar valores financeiros

Proposta:
- Separar payload público (sem 'R$', cliente ou operador) de detalhe sensível.
- 'daily_revenue_vs_baseline' troca '_brl(...)' por mensagem sem valor; detalhe no 'BIAlertEvent' gateado (padrão já usado por 'cash_variance_by_drawer').
- Guardrail de teste: alerta amplo de BI com valores financeiros falha a suíte.

Aceite:
- Guardrail falha se alerta amplo contém 'R$' (teste — hoje 'revenue_vs_baseline' falharia).
- Operador sem 'view_bi' não recebe faturamento em R$ pelo canal de alertas.

### P1 — Egress financeiro para o provedor de IA (achado novo)

Proposta:
- 'scenarios.py:94-128': revisar o que vai para 'copy_assist'; remover nomes de SKU/faturamento por canal quando não forem necessários ao prompt; documentar a finalidade no contrato do endpoint.
- Se o provedor exige os agregados, anonimizar e reduzir granularidade (dia→semana, sem nomes).

Aceite:
- Teste asserta o payload do 'copy_assist' sem PII/nomes de SKU (ou com justificativa documentada).
- Decisão de retenção registrada neste WP.

### P2 — Datas inválidas e célula mínima

Proposta:
- 'normalized_window_reason' no contrato quando clampa/inverte (mantém a decisão de normalizar).
- Célula mínima: famílias financeiras com 'n < k' → bucket 'suppressed' (exige contar 'n' por bucket — custo declarado).

Aceite:
- 'date_from=bad' não quebra, mas o relatório informa a janela efetiva e o motivo.
- Explorador não mostra bucket financeiro identificável por uma venda.

## Melhorias UX

1. **Selo de confiança por painel:** fonte, cobertura, buracos, janela efetiva, medido/estimado.
2. **Drilldown ao dono:** vendas → pedidos agregados; produção → relatório; caixa → auditoria; estoque → indisponibilidade.
3. **Snapshot/export com metodologia:** janela, fontes, filtros, usuário, horário, suprimidos, conflitos.
4. **Por que mudou?:** decompor delta por fonte, canal, SKU e conflito.
5. **Modo reunião:** snapshot sem PII para compartilhar com equipe.

## RBAC / setup_groups

Nenhuma permissão nova: 'view_bi' e 'cashman.audit_shift' já existem e são concedidas. O flag 'can_audit_cash' é derivado, não permissão nova.

## Pré-requisitos

- Nenhum. Independente dos demais WPs.

## Testes

- Exemplos filtrados por métrica permitida; save audit-only bloqueado; filtro contra permissão corrente.
- Aba Caixa some para não-auditor (flag 'can_audit_cash').
- Cenário IA envia/persiste janela efetiva; round-trip exibe.
- Alertas amplos sem 'R$', operador ou cliente.
- Egress IA sem PII/nomes de SKU.
- Buckets sensíveis com 'n < k' suprimidos.
- 'normalized_window_reason' presente quando normaliza.
- Paridade barrel TS exporta tipos gerados usados.

## Fora De Escopo

Executar plano da IA, abrir/fechar caixa, editar pedido, comandar produção, criar compra, mudar estoque, disparar campanha, editar cliente, aprovar crédito, e **recalcular RFM por janela** (dono: guestman).

## Prompt Para Agente Executor

~~~text
Execute WP-07-agente-d (BI).

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_d/WP-07-agente-d-bi.md
- surfaces/bi-nuxt/app/presentation/bi.ts
- surfaces/bi-nuxt/app/composables/useBiScenarios.ts, useBiWindow.ts
- surfaces/bi-nuxt/app/components/BiTopBar.vue, pages/scenarios.vue
- shopman/backstage/api/bi.py
- shopman/backstage/projections/bi_explore.py, bi_customers.py
- shopman/backstage/bi/alerts.py
- shopman/backstage/bi/scenarios.py (egress IA)

Fases:
1. Filtrar exemplos/saved views por metrica permitida + bloquear save + flag can_audit_cash (aba Caixa).
2. Escopos global vs janela em Clientes (rotulo, sem recalcular RFM).
3. Contrato de janela do POST de cenarios IA (body) + persistir janela efetiva + exibir.
4. Redigir payload publico de alertas; guardrail de R$; revisar egress para copy_assist.
5. normalized_window_reason + supressao de celula minima (famiilias financeiras).

Nao implemente acoes operacionais dentro do BI e nao recalcule dados de guestman.
~~~

