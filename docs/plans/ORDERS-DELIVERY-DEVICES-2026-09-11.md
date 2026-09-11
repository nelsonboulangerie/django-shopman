# Maquininhas individuais na entrega — extensão autorizada

Solicitação de Pablo transmitida pela tarefa PDV `01a08aaa-605d-7b70-a97e-26825fe39a2f`
em11/09. Complementa o plano operacional, sem substituir seus gates, budgets ou DoD.
Não autoriza publicação nem efeitos reais. Fonte integrada a revisar: commit PDV
`e3c1267a57a6e181ec6d1a9be04dea21c1311da5`, relatório
`docs/reports/PDV-PAGAMENTO-ENTREGA-2026-09-11.md` na worktree PDV.

## Escopo e invariantes

Cadastro nativo Admin/Unfold: nome/apelido, identificação única, ativa/inativa.
Gestor identifica aparelhos disponíveis e em trânsito e a entrega correspondente.
Escolha e alocação somente na confirmação do despacho, com exclusividade no servidor.
Duas pessoas disputando o mesmo aparelho: uma alocação, outra recebe conflito,
leitura atualizada e próxima ação no recurso. Falta de aparelho bloqueia somente
entrega dependente. Devolução explícita libera disponibilidade. Um aparelho por
entrega nesta etapa; compartilhar por rota fica fora do escopo.

Pagamento e devolução são fatos independentes. Checkbox conjunto começa desmarcado.
PDV declara necessidade, nunca reserva antecipadamente. Reusar intenção/recibo,
revisão, locks e Actions existentes. `dispatch.equipment=['card_machine']` é tipo
legado, não identidade física; não inventar vínculos históricos por migração.

## DAG e evidências de entrada

1. M00 inventariar modelo/entrada/writers e integrar seletivamente contrato PDV.
   Fonte Gestor52bebddbb; locks de pedido/custódia e recibos já mais maduros que PDV:
   não sobrescrever funções pelo arquivo antigo nem cherry-pick da branch inteira.
2. M01 cadastro estrutural e exclusividade, migration aditiva e testes de banco.
   Nenhum campo novo em Core; JSON sozinho não impõe exclusividade entre pedidos.
3. M02 alocação/devolução nos serviços canônicos, proteção das entradas Gestor,
   KDS/expedição e fulfillment/courier; legado retornável sem identidade inventada.
4. M03 projeção em lote e seleção no despacho, disponibilidade e contexto do conflito;
   evitar consulta por card e manter budgets anteriores.
5. M04 ensaios PostgreSQL concorrentes, replay/resposta perdida, devolução versus
   acerto, inativo, legados e entradas alternativas; Admin/browser/typecheck e
   budgets afetados. Registrar logs negativos e limites, migration/rollback.

M00→M01→M02→M03→M04, integrados a WP01/02/03/06/07/09 do plano principal.
Estado inicial: M00 em andamento; demais não iniciados. Nenhuma conclusão alegada.

## Integração e rollback

Contrato PDV preserva `settle_delivery_cash`/`can_settle_delivery_cash` para cartão,
dinheiro e mistos; apenas cash afeta gaveta, PIX Efí continua antecipado. Integração
manual deve preservar locks/revisões/receipts mais novos do Gestor. Não publicar
antes de teste integrado contra a versão acordada com PDV.

Migração aditiva não reconcilia estoque físico real. Cadastro/contagem reais são
G02/G06/G07 aplicáveis; não semear aparelhos presumidos. Rollback deve suspender
despachos dependentes antes de voltar para código sem exclusividade, preservar
alocações/histórico e permitir devolução segura; não apagar tabela em trânsito.
Decisões sobre retenção de drafts continuam separadas desta extensão.
