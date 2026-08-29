# WP-07 - BI

**Status:** pronto para implementacao  
**Superficie:** `surfaces/bi-nuxt` + endpoints `api/v1/backstage/bi/*`  
**Objetivo:** fazer o BI responder perguntas de gestao sem falsa confianca, vazamento de PII/financeiro ou acao fora do dominio dono.

## Fronteira Natural

BI e camada de leitura gerencial sobre fatos de outros dominios. Pode explicar tendencia, confianca, buracos de medicao, perguntas salvas e propostas. Nao abre caixa, nao corrige contagem, nao edita pedido, nao comanda producao, nao cria compra, nao muda estoque e nao dispara campanha.

## Evidencias Principais

- Gate comum `view_bi`: `shopman/backstage/api/bi.py:38`.
- Caixa exige permissao adicional: `shopman/backstage/api/bi.py:94`, `:99`.
- API filtra metricas audit-only: `shopman/backstage/api/bi.py:157`.
- Metrica `cash_difference` e audit-only: `shopman/backstage/projections/bi_explore.py:222`.
- UI tem exemplo estatico de quebra de caixa: `surfaces/bi-nuxt/app/presentation/bi.ts:246`.
- Exemplos filtram dimensao, nao metrica: `surfaces/bi-nuxt/app/presentation/bi.ts:184`.
- Clientes mistura janela e global: `shopman/backstage/projections/bi_customers.py:48`, `:75`, `:90`.
- Cenariamente IA nao envia janela: `surfaces/bi-nuxt/app/composables/useBiScenarios.ts:17`.

## Achados Priorizados

### P1 - Explorador pode oferecer exemplo sem metrica permitida

A API esconde `cash_difference` para quem nao tem auditoria; a UI ainda pode sugerir exemplo.

Proposta:

- `availableExamples` valida metrica contra `report.metrics`.
- Saved views com metricas proibidas devem ser filtradas, rebaixadas ou bloqueadas com motivo.

Aceite:

- Usuario sem `cashman.audit_shift` nao ve exemplo nem saved view acionavel de quebra de caixa.

### P1 - Clientes mistura periodo com metricas globais

Tela mostra `CustomerInsight` e `Customer.count()` globais junto de `new_by_week` por periodo.

Proposta:

- Campos recebem `scope: "global" | "window"`.
- UI separa “base atual” de “no periodo”.

Aceite:

- Alterar janela nao faz numero global parecer recorte.

### P1 - Cenarios IA podem nao representar janela visivel

POST aceita data, mas composable nao envia. Backend grava janela antes de normalizar.

Proposta:

- `useBiScenarios.generate()` envia `useBiWindow().range`.
- Persistir janela efetiva retornada por `gather_inputs`.

Aceite:

- Cenario salvo mostra a janela exata usada para calculo.

### P1 - Alertas BI podem vazar valores financeiros

Bus de alertas e amplo; algumas mensagens podem conter faturamento/baseline para operadores sem `view_bi`.

Proposta:

- Separar payload publico de detalhe sensivel.
- Alertas publicos de BI financeiro sem `R$`, cliente ou operador.
- Link para detalhe exige BI/permissao adequada.

Aceite:

- Guardrail falha se alerta amplo de BI contem valores financeiros.

### P2 - Datas invalidas viram default silencioso

Parse invalido retorna `None`, normalizacao clampa/inverte sem motivo no contrato.

Proposta:

- 400 para data invalida.
- `normalized_window_reason` quando clampa/inverte por regra.

Aceite:

- `date_from=bad` retorna 400 em endpoints BI.

### P2 - Sem regra de celula minima

Dimensoes financeiras por hora/canal/metodo podem identificar venda unica.

Proposta:

- Classificar familias sensiveis.
- Ocultar buckets com `n < k`, retornando `suppressed`.

Aceite:

- Explorador nao mostra bucket financeiro identificavel por uma venda.

## Melhorias UX

1. **Selo de confianca por painel:** fonte, cobertura, buracos, janela efetiva, medido/estimado.
2. **Drilldown ao dono:** vendas -> pedidos agregados; producao -> relatorio; caixa -> auditoria; estoque -> indisponibilidade.
3. **Snapshot/export com metodologia:** janela, fontes, filtros, usuario, horario, suprimidos, conflitos.
4. **Por que mudou?:** decompor delta por fonte, canal, SKU e conflito.
5. **Modo reuniao:** snapshot sem PII para compartilhar com equipe.

## Testes

- Exemplos filtrados por metrica permitida.
- Saved view com `cash_difference` bloqueada para nao auditor.
- Datas invalidas retornam 400.
- Cenario IA envia/persiste janela efetiva.
- Alertas amplos sem `R$`, operador ou cliente.
- Buckets sensiveis com `n < k` suprimidos.
- Paridade barrel TS exporta tipos gerados usados.

## Fora De Escopo

Executar plano da IA, abrir/fechar caixa, editar pedido, comandar producao, criar compra, mudar estoque, disparar campanha, editar cliente ou aprovar credito.

## Prompt Para Agente Executor

```text
Execute WP-07 BI.

Leia:
- docs/plans/backstage-app-audits-2026-08-29/WP-07-bi.md
- surfaces/bi-nuxt/app/presentation/bi.ts
- surfaces/bi-nuxt/app/composables/useBiScenarios.ts
- shopman/backstage/api/bi.py
- shopman/backstage/projections/bi_explore.py
- shopman/backstage/projections/bi_customers.py
- shopman/backstage/bi/alerts.py

Fases:
1. Filtrar exemplos/saved views por metrica permitida.
2. Separar escopos global vs janela em Clientes.
3. Persistir janela efetiva em cenarios IA.
4. Redigir payload publico/sensivel de alertas.
5. Adicionar selo de confianca e supressao de celula minima.

Nao implemente acoes operacionais dentro do BI.
```

