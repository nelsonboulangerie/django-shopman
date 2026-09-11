# Estado consolidado da execução

Referência: plano integral de 10/09/2026; diário append-only em
`../orders-operational-excellence-20260910.md`. As tabelas antigas do diário são
fotografias históricas. Esta consolidação cobre o código até **006264e45**, incluindo
a correção de largura do catálogo **340eefeac** e logging Manychat **4f4ad6fef**. Não declara T, P ou R concluídos.

## Pacotes e critérios restantes

| Pacote | Implementação/evidência disponível | Aceite ainda aberto |
| --- | --- | --- |
| WP00 | Worktree/branch isolados, proveniência das oito referências, comparação das bases, diagnóstico reproduzido, writers e locks inventariados | Consolidação integral da matriz por consumidor; H08 depende de inventário real autorizado |
| WP01 | Actions por pessoa/revisão, guardas reutilizadas, quantidade decimal, bloqueio consistente e recovery actions | Unidade histórica ausente não é inferida do produto atual; política nova G01 e inventário H08 |
| WP02 | Efeito/recibo local atômicos, fingerprint, consulta com mesma chave, merge por campo, concorrência/crash e cliente antigo recusado | Retenção nova G08; versão antiga de worker não é rollback seguro |
| WP03 | Cancelamento fresco e motivos, barreiras Payman→transição, custódia/turno observado, acerto único, estorno/retorno preservados | Custódia operacional G02; procedimentos externos G03 |
| WP04 | Fases duráveis, retorno com um dono, courier e avisos started/unknown/accepted, crash entre processos e alerta | Consulta/retry de fornecedor homologados G03; não repetir unknown por idade |
| WP05 | Patch/lote integral, prévia exata, recibos, ordem canônica por drag/teclado, feed sem preço próprio, sync separado | Publicação sensível/tiers reais e evidência fiscal/nutricional G05; volume de campo H08 |
| WP06 | Draft por pessoa/recurso, merge/conflito, SKU atrasado, sessão e navegação, nota confirmada com GET falho, alvos compartilhados | Inventário completo de alvos/AT e compreensão humana; pós-reload/retensão G05/G08 |
| WP07 | Hold/Payman/fiscal em lote, leitura útil/erro, relógio, coalescimento, HTTP rico e SSE real medidos | **500 pedidos/10 clientes e tela de 500 ainda excedem budgets**; rede/aparelho G06 e cobertura completa de carga/fallback |
| WP08 | Eventos correlacionados, estados de efeitos, alertas existentes, runbook e placar readonly canônico | Placar ainda não mede todos os drafts/stale/efeitos sem Directive; handoff e compreensão com pessoas no piloto |
| WP09 | Suíte ampla fixa, PostgreSQL, browser integrado, restore populado com livros/chaves, incompatibilidade antiga comprovada | Depende dos aceites técnicos abertos WP00–08; gates de liberação ainda não assinados |
| WP10 | Protocolo e folha de observação preparados | Piloto **não iniciado**: WP09 e G01–G08 aplicáveis, cinco turnos e pessoas reais |
| WP11 | Sequência por capacidade/coorte e parada documentadas | Rollout **não autorizado nem executado** |
| WP12 | Retorno, retenção e remoção documentados | Sete dias/dois fechamentos e G08 de remoção **não executados** |

Não se excluiu formalmente uma capacidade para tornar a DoD verde. Uma limitação
listada não equivale a exclusão aprovada. Nenhum gate foi resolvido por silêncio.

## D/H revalidados e destino da evidência

| Achados | Resultado técnico observado | Evidência principal |
| --- | --- | --- |
| D01/D02 | Replay não avança novamente; campos independentes coexistem; conflito conserva intenção/draft | Contratos remote_mutations, testes PostgreSQL e integração `operational.spec.ts` |
| D03 | Correção madura preservada: cancelamento impossível continua recusado | Testes de cancelamento fresco e H03; não recriada regra |
| D04/D18/D19/H01 | Derivação courier e fases recuperam trabalho faltante; unknown impede repetição cega | `notification_unknown/`, `restore_lab/`, testes courier/lifecycle/return |
| D05/D06/D07/D12/H05 | Validação integral, gate fiscal compartilhado, preço e ordem exatos, revisão entre escritores | Testes catálogo/lote/config; integração preço/célula/curadoria/publicação |
| D08 | Frações preservadas; unidade sem fonte histórica permanece desconhecida | Schema gerado e testes de precisão; H08 pendente |
| D09/D13/D17/H06 | Draft/SKU/pessoa protegidos; resultado confirmado sobrevive à falha de leitura | 26 integrações; `confirmed_note/`, `detail_targets/` |
| D10/D11 | Action e motivo controlam ativação; API reavalia permissão e fato sob lock | Testes de personas/Actions e `recovery_actions/` |
| D14/D15/D16 | Erro não vira vazio; motivo externo tipado; hora do servidor e leitura útil | Integrações de outage/SSE e testes de clock/reasons |
| D20/H04 | Batch elimina Hold por card; otimização medida sem mudar JSON rico; gargalos grandes persistem | `http_read_lab/`, `read_work/`, `command_budget/`, `sse_budget/` |
| H02/H03 | Corridas reproduzidas/protegidas por locks e barreiras, livros conferidos | `h03-final-matrix.txt`, testes de custódia/Payman/cancelamento |
| H07/H09 | Política/audiência preservadas, inbox conserva última leitura | Não houve extensão de ação pessoal; decisão G01 permanece |
| H08 | Nenhuma inferência sobre volume/dados históricos reais | Inventário autorizado ainda necessário; fixtures não o substituem |

## Esforço: comparação disponível e limites

Antes é baseline **estrutural** do plano e reproduções controladas, sem distribuição
humana medida. Depois são trajetórias automatizadas/contratos; T humano, hesitação,
abandono e entendimento continuam sem amostra de campo.

| Jornadas | Antes observado | Depois demonstrado no laboratório |
| --- | --- | --- |
| J01 | Ação elegível com um gesto; divergência tabela/card quando bloqueada | Um gesto preservado; Action bloqueada não emite comando |
| J02/J03 | SSE/concorrência substituíam nota ou campo independente | Texto preservado, decisão explícita no mesmo campo, sem redigitar draft |
| J04 | Repetir avanço após resposta perdida mudava outra etapa | Uma aplicação e consulta automática da mesma intenção, zero clique de recuperação |
| J05 | Regra madura já recusava cancelamento impossível | Regra protegida; revalidação no momento da transição |
| J06/J07 | Fato courier podia ficar sem derivação; risco de custódia obsoleta | Pendência explícita, turno/revisão observado, acerto único; confirmações físicas mantidas |
| J08/J09 | Retry podia alterar preço outra vez; ordem gravada voltava diferente | Prévia/recibo exatos, ordem canônica por pointer/teclado, sync independente |
| J10/J11 | Erro/vazio e falha de motivo perdiam orientação/contexto | GET falho conserva leitura/draft, retorno tipado, receipt sem nova mutação |
| J12 | Troca/reabertura podia reaplicar resposta na pessoa/SKU errados | Mesma pessoa conserva contexto em memória; outra pessoa não herda; reload segue gate |
| J13/J14 | Fase parcial/retry externo podia repetir efeito ou afirmar envio | Estado conhecido/unknown e recibo no recurso, um aceite após crash; homologação pendente |
| J15 | Lote podia limpar contexto e repetir itens aplicados | Resultado por ref e intenção; teste de publicação/recovery sem ampliar seleção |

R=0 está comprovado nos cenários de interrupção efetivamente ensaiados, não em
todo aparelho/retensão possível. Não há número legítimo para redução humana ≥30%
ou p50/p95 de T. Login, segunda assinatura e confirmação física não foram removidos
e constam separados e no total da folha preparada para o piloto.

## Testes e desempenho relevantes

- Backend amplo, fonte fixa1d84dcc5b: **8.718 passed,68 skipped,3 warnings,
  38 subtests,493,08s**, SQLite/xdist2. Skips nominais no log; não equivalem a testes
  PostgreSQL executados. Cores e famílias PostgreSQL têm rodadas próprias no diário.
- PostgreSQL sensível nesta rodada: **48 passed/15,85s**. Anteriores:157 de
  notificação/efeitos,218 da família de notificação e demais contratos documentados.
- Gestor atual: **295 Vitest**, typecheck/build; **26 integrações/47,3s**.
  Uma rodada anterior falhou por coluna de produto com0px; corrigida e preservada.
- 500 pedidos ricos, após otimização: backend p95 **229,7/377,4/1.599,1ms** para
  1/2/10 clientes; BFF **266,1/433,5/1.903,5ms**. Browser500 p95 **2.473ms**.
  São medições do incremento de otimização registrado, não nova rodada no último SHA.
- Comando de nota: feedback com2frames p9532,3ms; normal112,6ms; resposta perdida
  recuperada110,6ms;20 amostras por modo,40 eventos/40 intenções e zero reenvio.
- SSE:20 atualizações, POST→visível+2frames p95108,03ms, limite superior do
  commit→visível. Stream quente, uma pessoa/pedido, localhost; não rede piloto.
- Placar sintético readonly de11/09: Payman/caixa12.000 centavos, diferença0;
  warning de fechamento ausente e tarefas/recibos pendentes preservados.

Rodadas negativas, preparação falha, npm warnings e limitações permanecem nos logs.
A instalação Python reutilizou o venv original somente para leitura, com imports
priorizando o worktree; não se alegou instalação Python limpa.

## Migração, rollback e decisão

Sem DDL novo de domínio. Backend seguro e leitores compatíveis devem anteceder
capacidade; browser antigo recebe400 intention_required e orientação de atualização.
Worker antigo **é inseguro para unknown**, demonstrado com fake: drenar/substituir
antes da liberação. Rollback conserva versão segura de mutação ou suspende apenas a
capacidade; nunca reativa o defeito antigo por conveniência.

Restore populado comprovou140 tabelas/129 sequências iguais e livros/chaves
preservados, inclusive in_progress/unknown; dois movimentos de estoque na rodada
completa. Backup sintético pequeno não comprova RTO/RPO operacional. Não se executou
deploy, reconciliação real, contato externo, despacho, emissão ou movimento real.

Decisões concretas e impactos estão em `PILOT-PROTOCOL.md`; G01–G08 pendentes.
O checkout original permanece em b589e22c5 com arquivos alheios preservados. Não
houve push, PR, merge, remoção de histórico ou limpeza de dados de terceiros.

Gates adicionais das dez superfícies e12 cores: `final_gates/README.md`.
Quatro processos ainda excedem500ms em10 clientes: `process_read_lab/README.md`.
