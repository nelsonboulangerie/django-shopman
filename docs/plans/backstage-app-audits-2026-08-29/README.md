# Auditoria Backstage Apps 2026-08-29

**Status:** planejamento pronto para execução  
**Metodo:** agentes independentes por fronteira natural de app, com consolidacao final  
**Escopo:** apps de operador/backstage, contratos API/projection/UI, seguranca e UX operacional  

## Resultado

Foram disparados agentes independentes para cada recorte funcional. Cada agente trabalhou sem editar codigo, com hyperfoco no proprio app e fronteiras explicitas com os demais.

| WP | App | Foco principal | Prioridade |
| --- | --- | --- | --- |
| [WP-01](WP-01-hub.md) | Hub / Central | tiles, sessao, deep links, dominio operacional | P1 |
| [WP-02](WP-02-pos-caixa.md) | POS / Caixa | terminal, dinheiro, pagamento, idempotencia | P1 |
| [WP-03](WP-03-gestor-pedidos.md) | Gestor de Pedidos | acoes, courier, fiscal, fila de excecoes | P1 |
| [WP-04](WP-04-kds.md) | KDS | estacao, item identity, SSE, toque errado | P1 |
| [WP-05](WP-05-producao.md) | Producao | WO, QC, pesagem, force/void, concorrencia | P1 |
| [WP-06](WP-06-compras.md) | Compras | NF, recebimento, custo, conversao, ruptura | P0 |
| [WP-07](WP-07-bi.md) | BI | confianca dos numeros, PII, saved views | P1 |
| [WP-08](WP-08-marketing.md) | Marketing | blast radius, preview, publish_now, PII | P1 |
| [WP-09](WP-09-admin-canonico.md) | Admin canonico | Unfold, actions perigosas, PII, refund | P0 |

## Agentes

| Agente | Recorte | Resultado |
| --- | --- | --- |
| Volta | Hub | concluido |
| Nietzsche | POS/Caixa | concluido |
| Halley | Gestor de Pedidos | concluido |
| Euler | KDS | concluido |
| Poincare | Producao | concluido |
| Descartes | Compras | concluido |
| Aristotle | BI | concluido |
| Turing | Marketing | concluido |
| Gibbs | Admin canonico | concluido |

## Regras Comuns

Estes WPs partem de quatro invariantes de produto:

1. **Uma identidade operacional:** a pessoa identificada por PIN, cracha ou senha deve ser o `request.user`; dispositivo confiavel nao concede permissao.
2. **Servidor decide capacidade:** botoes, permissoes, acoes perigosas e bloqueios devem vir de projection/API, nao de heuristica local da UI.
3. **Sem efeito irreversivel sem contrato:** dinheiro, estoque, fiscal, campanha, refund, recebimento e producao precisam de idempotencia ou conflito claro.
4. **UX de chao de loja:** operador com pressa precisa ver proxima acao, risco, bloqueio e undo/recuperacao sem interpretar erro tecnico.

## Regua Externa Usada

Estas referencias foram usadas como calibragem, nao como substituto da leitura do repo:

- OWASP ASVS 5.0.0: https://owasp.org/www-project-application-security-verification-standard/
- OWASP API Security Top 10: https://owasp.org/API-Security/
- OWASP Top 10 2025: https://github.com/OWASP/Top10/blob/master/2025/docs/en/index.md
- WCAG 2.2 Recommendation: https://www.w3.org/TR/WCAG22/
- NN/g, Error Prevention / Slips: https://www.nngroup.com/articles/slips/

## Ordem Recomendada

1. **P0 de seguranca/integridade:** Compras `ReceiptDraft` e idempotencia; Admin refund/step-up.
2. **Contrato operacional compartilhado:** manifests de actions/hrefs/payloads para POS, Pedidos, Producao e KDS.
3. **Estacao e identidade:** terminal POS, KDS lacrado por estacao, Hub permission-aware.
4. **P1 de permissoes finas:** Marketing, Producao, Pedidos, Compras, Admin actions.
5. **UX de excelencia:** semaforos, preflights, outbox, dry-run, trust badges, undo.

## Definicao De Pronto Para Cada WP

- Achados P0/P1 cobertos por teste de backend e, quando houver UI, teste frontend.
- Sem mutacao nova sem idempotencia, `expected_rev`, token de preview ou erro 409 deliberado.
- Permissoes perigosas separadas de permissoes de leitura/operacao comum.
- Apps Nuxt com estado honesto para lock, offline, stale e erro de permissao.
- Admin/backstage custom segue `make admin` e Unfold Canonical Gate.
- Fronteira `O que nao pertence` preservada.

