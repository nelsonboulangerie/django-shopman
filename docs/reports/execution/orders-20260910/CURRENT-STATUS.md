# Estado consolidado da execução

Referência: plano integral de 10/09/2026; diário append-only em
`../orders-operational-excellence-20260910.md`. As tabelas antigas do diário são
fotografias históricas. Esta consolidação cobre o código até **062a7b5ec**, incluindo proteção de descarte
**8318b9b03**, ícones CSS **062a7b5ec**, alvos de interação, Actions de corrida
e inventário **84e609641**. Não declara T, P ou R concluídos.

## Capacidade: verificação da DigitalOcean e CI — 11/09

Spec ativo consultado read-only: backend1CPU/1GB, Gestor512MB, PG16/Valkey8.
CI isolado na topologia de1leitor reprovou p95backend2500ms/10clientes e browser2229ms.
Cinco leitores também reprovaram1322/1622ms e browser2573/3044ms no runner4CPU.
Preparação e jornadas passaram; vereditos de budget falharam. Sem liberação de
capacidade nem indicação comprovada de aumento permanente. Não atribuir tudo ao
swap do Mac. Três fontes/artefatos/perfis estão em [do_capacity/README.md](do_capacity/README.md).

Pablo aceitou rascunhos em memória com proteção de saída. A proposta de novo
laboratório pago foi retirada por orientação explícita dele; não há decisão de
infraestrutura pendente nem recurso novo criado. PC da loja, rede existente e
DigitalOcean são o contexto informado, sem necessidade de rediscutir hospedagem.

Correção de escopo: G06 condiciona o início do piloto; §10 item 4 permite deploy
técnico antes da ativação de capacidades. As reprovações acima permanecem como
limite do ensaio de capacidade, sem bloquear automaticamente toda publicação.
A tarefa PDV coordena a publicação técnica já autorizada: integrar main atual,
revisar migração/compatibilidade, obter CI da fonte final e verificar rollout/smoke
sem efeitos reais. Isso não declara T, P ou R globalmente concluídos.

## Atualização vigente — extensão de maquininhas individuais47e9c657a

Esta atualização prevalece sobre budgets históricos abaixo. Cadastro nativo,
alocação exclusiva no despacho, devolução independente e contrato PDV integrados.
M00–M03 implementados; M04 funcionalmente verificado:90 PostgreSQL sem skips,
corrida forçada1,31 jornadas browser,303 unidade Orders,264 gate Admin, typecheck/build.
Suíte ampla6f0f38145:23 falhas/9452 passes/79 skips; os23 nós passaram após correções
emc1063c850. Não atribuir suíte inteira ao HEAD atual nem somar famílias sobrepostas.

**Capacidade atual reprovada:**500 pedidos+10 aparelhos,5 leitores/10 clientes,
p95backend954/2036/1058ms; browser1857/1695/1620ms em três rodadas. Limites500/1500
não mudaram. T permanece aberto por capacidade e demais aceites; P não iniciado;
R não autorizado. Fonte antiga922 também reprovou agora2290ms no mesmo host; seu passe histórico
não libera a nova versão nem esta comparação prova regressão causal. Logs,
proveniência, decisões, esforço, migration0061/rollback e scripts reproduzíveis em
[delivery_devices/README.md](delivery_devices/README.md). Persistir drafts pós-reload
é opcional em C07 e não está implementado; não é bloqueio obrigatório de T.

## Resultado histórico — fonte922fb522c

**Rodada histórica; desempenho atual está na extensão acima.** Evidências completas,
falhas preservadas, testes e rollback em [performance_completion/README.md](performance_completion/README.md).
Commits429e0a2b2 e922fb522c reduziram trabalho repetido de projeção e hidratação.
500 pedidos: browser p951329 ms; backend p95451,290 ms em10 clientes com **cinco
processos**,60 amostras. Quatro ainda falham565,553 ms. Topologia real e rede não
homologadas; nenhum budget foi alterado. Backend amplo atual9446 pass/77 skips;
runtime PostgreSQL341 pass sem skips;29 jornadas integradas passaram.
Restore atual162 tabelas/151 sequências iguais inicialmente; após probes apenas
sequência de alerta10→11, linhas intactas. Worker antigo permanece inseguro.

Retenção pós-reload é opcional em C07: não implementada, contexto em memória e
confirmação de descarte mantidos. Não constitui bloqueio técnico obrigatório.
T continua aberto pelos aceites listados; P preparado, R não executado.

## Atualização do brief / rebase — 11/09

Os 96 commits foram reaplicados sobre main **0acb727ff** (incluindo PRs599/601).
Backup anterior: `codex/orders-pre-brief-20260911` em **daf58b9c2**. Rebase
**aa412f87c**; compatibilidade final **8669dce40**. A referência062a7b5ec acima
continua identificando a rodada histórica, não a fonte pós-rebase.

Rodada atual: **303 testes Orders**, **255 kit**, **58 +85 execuções PostgreSQL**,
**29 jornadas integradas**, typecheck/build e Ruff dos arquivos Python resolvidos.
Há sobreposição entre as famílias PostgreSQL; não são143 testes únicos.
Logs positivos, falha de seleção de arquivo e regressão corrigida estão em
`brief_rebase/README.md`. A suíte ampla histórica não foi reexecutada neste SHA.
O servidor das jornadas foi carregado antes do ajuste8669 (código estável do erro
+imports); essa diferença foi coberta pela rodada PostgreSQL, não por nova jornada.

A triagem do novo brief está em `../../ORDERS-CONTROLS-TRIAGE-2026-09-11.md`.
Altura44/fundo/foco já aprovados por Pablo no PR599, sem novo gate. Opacidades
continuam pendentes. A/B/C ainda não implementados: o brief exige fechar a branch
operacional antes dos três PRs separados. Não há aprovação implícita desse fechamento.
Esta afirmação de reprovação pertence à rodada do brief; foi superada pela medição acima.

As novas migrações do main foram aplicadas somente em `orders_lab` sintético;
Pedidos não introduziu DDL próprio. O rollback para a antiga base
não pode ser tratado como downgrade de banco: o baseline agora inclui os schemas
upstream. Não houve produção nem efeitos reais. T/P/R mantêm os estados abaixo.

## Pacotes e critérios restantes

| Pacote | Implementação/evidência disponível | Aceite ainda aberto |
| --- | --- | --- |
| WP00 | Worktree/branch isolados, proveniência das oito referências, comparação das bases, diagnóstico reproduzido, writers e locks inventariados | 39 rotas/hashes e47 usos diretos mapeados em contract_inventory; aliases/caminhos indiretos não são prova por AST; H08 depende de inventário real autorizado |
| WP01 | Actions por pessoa/revisão, guardas reutilizadas, quantidade decimal, bloqueio consistente e recovery actions | Unidade histórica ausente não é inferida do produto atual; política nova G01 e inventário H08 |
| WP02 | Efeito/recibo local atômicos, fingerprint, consulta com mesma chave, merge por campo, concorrência/crash e cliente antigo recusado | Retenção nova G08; versão antiga de worker não é rollback seguro |
| WP03 | Cancelamento fresco e motivos, barreiras Payman→transição, custódia/turno observado, acerto único, estorno/retorno preservados | Custódia operacional G02; procedimentos externos G03 |
| WP04 | Fases duráveis, retorno com um dono, courier e avisos started/unknown/accepted, crash entre processos e alerta | Consulta/retry de fornecedor homologados G03; não repetir unknown por idade |
| WP05 | Patch/lote integral, prévia exata, recibos, ordem canônica por drag/teclado, feed sem preço próprio, sync separado | Publicação sensível/tiers reais e evidência fiscal/nutricional G05; volume de campo H08 |
| WP06 | Draft por pessoa/recurso, merge/conflito, SKU atrasado, sessão e navegação, nota confirmada com GET falho, alvos compartilhados | 29 jornadas integradas e alvos frequentes44/48; AT físico e compreensão humana sem ensaio; persistência pós-reload opcional não adotada |
| WP07 | Hold/Payman/fiscal em lote, leitura útil/erro, relógio, coalescimento, HTTP rico e SSE real medidos | Rodada nova com aparelhos falha500/1500ms; capacidade/ambiente G06 e cobertura completa de carga/fallback abertos |
| WP08 | Eventos correlacionados, estados de efeitos, alertas existentes, runbook e placar readonly canônico | Contagem limitada por endpoint/trace; coleta supervisionada draft/stale preparada, sem medidas humanas; nem todo efeito sem Directive é coberto pelo sweeper |
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
| D09/D13/D17/H06 | Draft/SKU/pessoa protegidos; resultado confirmado sobrevive à falha de leitura | 29 integrações; `confirmed_note/`, `reason_discard/`, `close_targets/` |
| D10/D11 | Action e motivo controlam ativação; API reavalia permissão e fato sob lock | Testes de personas/Actions, `recovery_actions/` e `courier_actions/` |
| D14/D15/D16 | Erro não vira vazio; motivo externo tipado; hora do servidor e leitura útil | Integrações de outage/SSE e testes de clock/reasons |
| D20/H04 | Batch elimina Hold por card; otimização medida sem mudar JSON rico; budgets revalidados em cinco processos; quatro falham | `http_read_lab/`, `read_work/`, `command_budget/`, `sse_budget/` |
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
| J12 | Troca/reabertura podia reaplicar resposta na pessoa/SKU errados | Mesma pessoa conserva contexto em memória; outra pessoa não herda; reload com texto pede decisão; persistência segue gate |
| J13/J14 | Fase parcial/retry externo podia repetir efeito ou afirmar envio | Estado conhecido/unknown e recibo no recurso, um aceite após crash; homologação pendente |
| J15 | Lote podia limpar contexto e repetir itens aplicados | Resultado por ref e intenção; teste de publicação/recovery sem ampliar seleção |

R=0 está comprovado nos cenários de interrupção efetivamente ensaiados, não em
todo aparelho/retensão possível. Não há número legítimo para redução humana ≥30%
ou p50/p95 de T. Login, segunda assinatura e confirmação física não foram removidos
e constam separados e no total da folha preparada para o piloto.

## Testes e desempenho históricos (rodada atual acima)

- Backend amplo, fonte fixa1d84dcc5b: **8.718 passed,68 skipped,3 warnings,
  38 subtests,493,08s**, SQLite/xdist2. Skips nominais no log; não equivalem a testes
  PostgreSQL executados. Cores e famílias PostgreSQL têm rodadas próprias no diário.
- PostgreSQL sensível nesta rodada: **48 passed/15,85s**. Anteriores:157 de
  notificação/efeitos,218 da família de notificação e demais contratos documentados.
- Gestor atual: **303 Vitest/6,44s**, **228 kit/3,89s**, typecheck/build; **29 integrações/1,2min**.
  Antes reproduzidos: coluna0px, descarte de motivo e botão Fechar16px; corrigidos
  com logs negativos preservados. Cancelamento/nota/reload da nova jornada não
  emitem comandos e conferem estado canônico inalterado.
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

Incrementos recentes: fb2e80fc9 alvos auxiliares;8318b9b03 descarte explícito;
84e609641 mapa de contratos;048b8e85a placar por endpoint;f531fd9f0 fechamento
44px e links. As dez superfícies/12 cores foram rodadas antes desses incrementos
de UI/artefatos; Orders foi revalidado após as mudanças. Nenhum teste de outro
SHA foi renomeado como teste da versão atual.

Última otimização mantida: **062a7b5ec** usa o modo CSS nativo dos mesmos
ícones locais na layer base, preservando hidden/size.500 pedidos: HTML4,19→3,04MB,
p953016→1951ms nesta comparação; **ainda acima1500ms**. Variante sem layer
rejeitada visualmente e documentada. Medição/limites em icon_render/. Não houve
mudança do backend nesta fatia: o limite500ms/10 clientes continua reprovado.

## Decisão necessária e trabalho suspenso

G06 precisa identificar aparelho/rede/topologia/personas representativos para
o ensaio de aceitação. O laboratório declarado é Apple M2/8GiB, loopback e
processos próprios; não é host exclusivo nem ambiente homologado. Escolher
outro ambiente exige nova medição; a rodada atual passa1329ms/451,290ms nas condições declaradas, mas não comprova
a capacidade de outro ambiente. Não se propõe relaxar budget silenciosamente.

G01–G05 definem owners, custódia, consulta externa, urgência e publicação sensível;
G07 autoriza ambiente/coorte/janela; G08 decide retenção/remoção. A decisão concreta,
evidência e impacto por gate estão em PILOT-PROTOCOL. Não há assinatura inferida.
WP09/T continua aberto, WP10/P somente preparado e WP11–12/R não executados.
AT físico, compreensão/handoff humano, contadores de campo e qualquer melhoria
humana30% continuam sem prova. O relatório não converte essas pendências em
exclusões de capacidade ou em conclusão técnica.
