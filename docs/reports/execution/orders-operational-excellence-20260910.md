# Execução de Pedidos — 10/09/2026

Estado: execução técnica em andamento; piloto e rollout não autorizados nem executados.

## Proveniência

Worktree exclusivo: `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-orders-execution-20260910`.
Branch: `codex/orders-operational-excellence-20260910`.
Base: `5a3383c950031da1ff9c6ace0d9ab09b3c4084f7`, origin/main local, sem fetch.
Base auditada: `9787bbcdfe5ccd2cbb4a2097b4d97c146e86179f`, ancestral da base executada.
Diferença: 16 arquivos de atalhos/PDV/Produção e kit; zero alteração em shopman, packages ou orders-nuxt.
Checkout recebido em `b589e22c5` não foi modificado. Arquivos não rastreados preservados.
Transportado somente o plano de Pedidos da branch documental `1e701515e`, sem código alheio.
CLAUDE.md lido; nenhum AGENTS.md localizado na hierarquia ou na árvore isolada.
Os oito documentos da seção 2 foram lidos, com hashes idênticos aos registrados no plano.
Produção e Marketing permaneceram entradas externas, sem cópia. ADR-012/014/016/018 e contratos
order-operational/remote-mutation confrontados: `confirmed` histórico não substitui `accepted`;
Channel display existente não ganha Listing nem preço próprio. Nenhum Admin alterado.

## WP00 — baseline

Evidência anterior: diagnósticos extraídos literalmente do bloco executável do plano, fora do produto.
SQLite: 12/12 reproduções passaram em 5,46s. D01/D02/D04/D05/D06/D07/D08/D19/D20 permanecem
reproduzidos; D03 permanece saudável (409, estado completed preservado). Assertions de defeito não
são aprovação de produto. D09–D18 de inspeção: comparação confirma código idêntico ao auditado;
releitura confirma watcher destrutivo, disabled divergente, guardas, lote sequencial, fechamento de
editor, erro/vazio, motivos engolidos, relógio local, erro sem refresh e fases incompletas.
H01–H09 continuam hipóteses/decisões, não incidentes provados nem autorização para políticas novas.

Implementação deste pacote: worktree, instalação limpa npm pelo lock e laboratório isolado.
Python 3.12.5 reutilizado em modo somente leitura do venv original, sys.path prioriza todos os packages
do worktree; sem instalação Python limpa alegada. Settings config.settings_test, DATABASE_URL/REDIS_URL
vazios para SQLite, sem .env copiado; adapters de pagamento mock e credenciais de fornecedores vazias.
PostgreSQL próprio em 127.0.0.1:55439, usuário/banco orders_lab, cluster .orders-lab/pgdata,
sem acesso ao banco operacional. Não há destinatário real, chamada de fornecedor nem periférico.

Testes efetivamente executados:
- 32 módulos das duas listas do plano: 585 passed, 1 skipped, 18 subtests passed, 38,37s.
- PostgreSQL: 12 diagnósticos + test_waitlist_waits_for_payment.py: 18 passed, 6,47s.
  Inclui o ensaio concorrente que SQLite pulou; não cobre toda matriz concorrente da seção 8.
- npm ci Gestor e kit com Node 22: passaram (887/660 pacotes). Warning glob deprecated preservado.
- Gestor Vitest: 12 arquivos, 221 passed, 2,35s; warnings Vue de harness presentes.
- Kit Vitest: 22 arquivos, 220 passed, 4,24s; sem a falha de carga antiga; warnings Vue presentes.

Medição pareada preparada: 20 amostras, macOS 15.4.1 arm64, SQLite, pedidos ready/pickup/cash simples.
Para 1/10/100/500 pedidos: 4/13/103/503 queries; 1/10/100/500 Hold nas duas projeções.
Duas zonas em 500: p50 218,03ms, p95 265,70ms, payload 872.660 bytes JSON sem compressão.
Isto não mede HTTP, rede, payload rico, SSE, dois/dez clientes nem hardware de piloto.
Primeiro ensaio de 500 excedeu buffer de 9000 queries; descartado, coletor limpo entre amostras e
ensaio repetido sem warning. Evidências de backend e distribuição: pasta orders-20260910.

### Contratos técnicos de implementação

Revisão: digest opaco do estado pertinente sob lock. Para nota e assignment, base por campo permite
merge independente; igualdade da base do mesmo campo é exigida. Avanço inclui status/target explícitos
mais fingerprint de entrada. Não usar seq de evento como revisão de notas/preços/config.
Fingerprint: JSON normalizado, versão, operação, alvo, base e inputs; escopo vincula pessoa/operação/alvo.
Estender remote_mutations/IdempotencyKey com commit local integral; rede fora do lock e via Directive.
Retenção global 24h e recibos permanentes preservados. Sete dias novos e persistência de draft após
reload ficam pendentes G05/G08; sessão em memória não autoriza retenção nova.
Lote: limite técnico deve ser medido em fixture de células antes do WP05; sem aceitar publicação
parcial de preço nem ampliar conjunto por coleção smart. Pendência de sync não reaplica preço.

Locks observados: produção trava WorkOrder→Order; eventos serializam agregado; Cashman trava turno
antes do ledger; writers de Order.data incluem notas, assignment, courier, dispatch, fiscal, lifecycle
e vínculos WO. Fiscal com lock preservado. Nenhuma ordem global nova pode inverter essas fronteiras.
Matriz fase/efeito: on_commit→estoque/cliente/payment/confirmation; accepted/paid→estoque/KDS/fulfillment;
preparing→KDS; ready→entrega/avisos; delivered→fechamento; completed→fiscal/loyalty; cancelled→release/refund/avisos.
Evidência/recuperador existente: Hold/Entry/Payman/ticket/Directive/IdempotencyKey e marcadores lifecycle.
Não inferir done do status avançado. Provas de crash adicionais pertencem WP02/WP04.

### Rastreabilidade

| Achados | Contratos | Pacotes | Prova exigida |
|---|---|---|---|
| D08/D10/D11 | C01 | WP01 | decimal, Actions iguais, negação por persona |
| D01/D02/D17 | C02/C03/C07 | WP02/WP06 | replay, fingerprint, merge/conflito, resposta perdida |
| D03/D15/H02/H03 | C03/C04 | WP03 | cancelamento, motivo externo, dois turnos, captura tardia |
| D04/D18/D19/H01 | C05 | WP04 | crash/derivação courier, queued/skipped, unknown |
| D05/D06/D07/D12/H05 | C06 | WP05 | patch integral, lote, ordem/revisão, falha segundo destino |
| D09/D13/H06 | C07 | WP06 | dirty/foco/SKU/resposta fora de ordem |
| D14/D16/D20/H04 | C08 | WP07/WP08 | erro≠vazio, clock, batch/frescor/carga |
| H07/H08/H09 | C01/C08 | WP00/WP08/WP09 | personas, inventário autorizado, owner de inbox |
| G01–G08 | C01–C08 | WP09–WP12 conforme DAG | decisão humana documentada, nunca presumida |

## Gates e migração

G01–G08 pendentes. Sem nova autoridade, política de timer/som, lançamento sintético para resolver
custódia, publicação sensível ou retenção persistente. Preparação técnica continua autorizada.
Piloto WP10 depende WP09 + gates; rollout WP11 e encerramento WP12 não começaram.
WP00 sem migration de domínio. Rollback: remover artefatos próprios e parar cluster próprio;
não apagar ou reconciliar dados reais. Código anterior P0 não deve ser reativado como rollback seguro.

## Placar

WP00: baseline executado; inventário e ensaios adicionais continuam ao longo das fatias.
WP01–WP09: pendentes; nenhum marcado T. WP10–WP12: pendentes de pré-requisitos e gates.
J01–J15: baseline estrutural do plano preservado; nenhuma melhora de campo alegada.
G06 ainda precisa aprovar budgets/personas/aparelhos/amostra. Sem medidas humanas de T/clareza.

## WP01 — fatia D08, quantidade decimal

Anterior: regressão permanente falhou para 0.500, 1.125 e limite 999999999.999;
quantidade inteira também verificou a alteração explícita de contrato. Implementação:
`OrderItemProjection.qty` passa a string decimal exata, sem zeros insignificantes;
resumo do card usa a mesma representação. Contrato TypeScript regenerado pelo comando.
Preço e total permanecem intactos. Nenhuma unidade foi inferida: OrderItem não possui
coluna de unidade e snapshot documentado não a garante. Resolução de unidade continua
pendente no WP01, assim como Actions/autoridade; pacote não concluído.

Testes: backend 73 passed, 13 subtests passed (11,42s), incluindo API/projeções/exportação;
Vitest final 222 passed (1,91s), incluindo renderização da fração, e nuxi typecheck passaram.
Ruff nos três arquivos Python passou. Sem ensaio de campo.
Migração: sem DDL ou backfill; consumidor deve aceitar qty textual, backend e artefato
gerado devem ser entregues juntos. Rollback técnico reverte a fatia, mas reintroduziria
D08: manter rollout suspenso até corrigir, nunca converter fração em inteiro para compatibilidade.
Esforço: zero gestos adicionais para ler a fração; tempo/clareza humanos não medidos.

## WP00 — limite local de lote e cobertura de writers

PostgreSQL isolado, 20 amostras/tamanho, sync e notificação mock, rollback de cada
amostra verificado (1.000 células mantiveram preço original). Lote atual de preço:
10/100/500/1.000 células → p95 4,98/12,01/127,05/155,97ms; cinco queries por amostra.
Limite inicial de implementação proposto: **100 células congeladas**, somando destinos,
não 100 SKUs multiplicados implicitamente por todos os canais. O ensaio ainda não inclui
full_clean/locks/fingerprint/recibo do contrato novo: repetir após WP05; rejeitar integralmente
acima do limite. Não equivale ao budget HTTP de 800ms nem a aprovação de Operações (G06).

`writer-inventory.md` registra funções/linhas com save de order/locked e ocorrências de locks.
É inventário estático parcial, explicitamente sem prova de proteção concorrente. Aliases,
updates diretos e core ainda exigem cobertura. Por isso WP00 não recebe selo T e WP02–WP09
não estão liberados como pacotes concluídos. Fatias D08/D10 são correções locais verificadas,
sem ativação/rollout, e não substituem o aceite integral dos pré-requisitos do DAG.

## WP01 — fatia D10, tabela respeita bloqueio

Antes: Playwright reproduziu card disabled versus tabela enabled para pagamento pendente.
Implementação: tabela respeita `a.disabled` e apresenta `a.reason` como o card; nenhuma
confirmação/autoridade suprimida. Fixture corrigida de `confirmed` histórico para `accepted`.
Primeira edição atingiu também botão de atribuição: E2E detectou tela vazia; corrigido antes
do commit. Resultado final: **4 E2E Chromium passed (19,2s)**, Nuxt build e typecheck passaram.
Backend desses E2E é mock; não prova integração Django, autorização ou efeitos reais.
Build emitiu warnings de sourcemap Tailwind e FORCE_COLOR; não foram ocultados.

Migração: nenhuma. Rollback: reverter dois bindings da tabela, reabrindo D10; preferir
manter a capacidade fora do rollout a restabelecer clique inválido. J01: zero ativações
adicionais em ação elegível; bloqueada deixa de aceitar clique. Tempo humano não medido.
WP01 permanece parcial (unidade, Actions e D11 ainda pendentes).

## WP00 — revalidação adicional de D02

Quatro diagnósticos passaram em PostgreSQL (4,96s); passam ao reproduzir perda, não ao
aceitar o produto. Courier `_save_block` e payment `_stamp_gateway_check` perdem nota
independente quando recebem instância obsoleta. Lifecycle `_mark_phase_complete` relê,
mas o ensaio com duas conexões inseriu nota entre leitura e save e demonstrou perda.

O diagnóstico direto de `_write_state` (waitlist) também reproduz perda com instância
obsoleta, **mas não prova defeito no caminho canônico**: releitura dos callers
`open_window`/`confirm`/`release` mostrou Order sob lock e instância fresca.
Não substituir esse caminho maduro com base no teste artificial do helper. Fiscal
`_record` e `settle_from_gateway` também já mesclam sob lock: preservar e testar regressão.
O inventário AST não basta para concluir que uma função está desprotegida.

Writer adicional localizado: anonimização em account usa QuerySet.update para exceção
legítima ao snapshot selado. Não afrouxar Order.save nem remover esse caminho; tratar
concorrência/PII no contrato, preservando autorização de exclusão e G08 para operações reais.

Gate da meia-correção nos três arquivos de produto alterados: exit 0 (log anexado).
Não equivale ao runtime-gate completo nem valida código ainda não implementado.

## Estado consolidado deste registro

**Execução integral não concluída.** Não há pacote aceito integralmente como T/P/R.

| Pacote | Estado | Trabalho restante |
|---|---|---|
| WP00 | parcial | fechar inventário integral de writers/rotas/consumidores e política/fixture/rollback de cada escrita; completar matriz de evidências |
| WP01 | parcial | D08 decimal e D10 tabela corrigidos; unidade, Actions, D11 e personas completos pendentes |
| WP02 | não implementado | intenção/recibo atômico, revisão/fingerprint, todos os writers, BFF e matriz concorrente |
| WP03 | não implementado | cancelamento/motivos externos/caixa e corridas H02/H03; D03 saudável preservado |
| WP04 | não implementado | recuperação courier/fases duráveis/resultado honesto de comunicação |
| WP05 | não implementado | integridade catálogo/feeds, lote e retomada por destino |
| WP06 | não implementado | drafts/conflitos/identidade/contexto |
| WP07 | não implementado | batch waitlist/relógio/refetch/HTTP e carga |
| WP08 | não implementado | retomada e observabilidade integrada |
| WP09 | não iniciado | gates completos, migração/rollback integrado e preparação completa do piloto |
| WP10 | não iniciado | piloto depende WP09 e gates humanos aplicáveis |
| WP11 | não iniciado | rollout depende piloto e G07 por expansão |
| WP12 | não iniciado | janela de retorno e aprovação G08 de remoção |

Commits locais revisáveis (nenhum push/PR/deploy):
- `02ff6149b`: proveniência e baseline.
- `4bb040d0a`: quantidade decimal e regressões.
- `a8f8e0eac`: disabled/motivo na tabela e E2E.
- `acffa3968`: interleavings PostgreSQL e fontes dos ensaios.

Nenhum gate humano foi aprovado ou presumido. G01 autoridade, G02 custódia/terminal,
G03 política externa, G04 urgência/som, G05 publicação/draft, G06 piloto/budgets,
G07 ambiente/efeitos reais e G08 retenção/remoção permanecem pendentes. Esses gates não
são a causa da incompletude técnica: há trabalho autorizado ainda por executar.

Sem migration de domínio. Rollback por fatia e riscos de reintroduzir D08/D10 descritos
acima; não executar rollback operacional nem reconciliar dados reais. Cluster PostgreSQL
próprio foi parado com pg_ctl; dados sintéticos permanecem somente em `.orders-lab/` ignorado.
Checkout original continua com seus arquivos não rastreados; não recebeu alterações desta execução.

Não executados: runtime-gate integral, E2E contra Django, Redis isolado, ensaios 2/10 estações,
matriz completa de crash/concorrência, medições humanas J01–J15, piloto e rollout. Números de
suítes acima se sobrepõem: não somar como testes únicos. A implementação atual não é candidata
à ativação: P0s D01/D02/D04/D05/D07/D12 continuam sem correção integral.

## Retomada autônoma — WP02, fundação do recibo local

O executor existente agora aceita fingerprint em escopos locais novos. Savepoint reverte
qualquer escrita do executor em recusa; efeito/evento/enqueue/recibo compartilham commit.
Fingerprint divergente recusa replay; lookup não cria/resetta chave nem consulta gateway.
Consumidores antigos conservam seu contrato. BFF encaminha somente Idempotency-Key,
If-Match e X-Correlation-ID; resposta preserva ETag/correlação/retry-after. TTL não alterado.

PostgreSQL: **11 passed (5,99s)**, incluindo duas conexões concorrentes, replay após resposta
perdida, falha no save de recibo, rollback de evento/enqueue e recusas 400/409/500.
Primeiro ensaio passou mas teardown alertou duas conexões abertas: harness corrigido para
connections.close_all no finally; banco efêmero removido e ensaio repetido sem warning.
Kit: **221 passed em 22 arquivos (2,57s)**, incluindo allowlist e não encaminhamento de
identidade arbitrária. Integração dos endpoints/clientes e todos os writers ainda em andamento;
isto não conclui WP02. Migração: envelope JSON apenas em escopos novos, sem DDL. Rollback:
manter leitores dos recibos e suspender capacidades locais antes de reverter executor.

## Retomada — WP01/WP02: Actions e avanço por intenção

C01: card e detalhe recebem Actions de shop para aceitar/recusar/avançar. Aceite consulta
os guards existentes de pagamento/disponibilidade; ausência de pessoa/permissão desabilita
Actions. Recusar permanece independente do bloqueio de aceite. Frontend usa essas Actions
nas três apresentações; revisões opacas independentes para avanço, nota e atribuição.

D01: POST advance exige chave, base e target; escopo vinculado a request.user/operação/ref.
Serviço relê sob lock e compara base/target antes de qualquer escrita. API GET no mesmo
recurso consulta recibo, sem resgate de gateway; o resgate do detalhe permanece intacto.
Cliente conserva chave/payload após erro ambíguo, consulta recibo automaticamente e não
aceita resposta de outra pessoa. Nenhuma persistência após reload foi introduzida.

Provas: cadeia do plano + regressões novas **603 passed, 2 skipped, 18 subtests (42,24s)**.
Skips são PostgreSQL-only; recibo concorrente já ensaiado em PG na fatia anterior. Ensaio
adicional de duas chaves contra uma base em PG: **1 passed (5,93s)**, exatamente um 200 e
um 409, uma transição. Handler posterior mock nesse ensaio, portanto sem alegação de efeito
externo. API/custódia/payment gate: **48 passed, 5 subtests (15,21s)**. Gestor **225 passed
(2,05s)**; E2E Chromium/mock **4 passed (22,7s)**; build e typecheck passaram; Ruff e gate
da meia-correção passaram. Resultados sobrepostos não devem ser somados como testes únicos.

J04 sintético: resposta perdida → uma consulta automática, zero clique extra, mesmo key;
resultado ainda desconhecido → próxima tentativa conserva payload/chave. J03 concorrência
de avanço: segunda intenção recusada, sem segundo movimento. Tempos humanos/clareza não
medidos. Sem alteração de confirmação/autoridade; G01/G02 continuam pendentes para políticas.

Limites restantes: Actions de outras mutações, unidade, writers JSON e edição concorrente,
durabilidade de enqueue lifecycle, integração Django no navegador e matriz completa de crash.
O recibo informa lifecycle pendente; não prova conclusão dos efeitos posteriores. WP01 e
WP02 seguem em andamento, sem T. Migração coordenada servidor/cliente: cliente antigo sem
precondição recebe 400; rollback deve suspender avanço, preservar recibos e manter consulta,
nunca reinstalar o advance inseguro para recuperar compatibilidade.

## Retomada — WP02/WP06: contexto concorrente e rascunho

D02 nota/atribuição agora releem Order sob lock, com revisões independentes. Recibo local
cobre notas/atribuição e vincula a intenção à pessoa esperada além da permissão corrente.
Três interleavings comprovados (courier, stamp de gateway, marcador lifecycle) passam a
mesclar somente seu bloco/campo em JSON fresco. Demais writers continuam sob auditoria;
não atribuir a eles o diagnóstico de perda sem prova.

D09/D17: atualização SSE conserva texto/base; conflito no mesmo campo mostra versão do
servidor e permite escolher explicitamente a base antes de salvar. Erro mantém explicação
no recurso e tenta reconciliar a leitura. Recibo de nota antiga não anuncia texto novo como
salvo; a consulta confirma a gravação anterior e preserva o novo rascunho.

PostgreSQL: **31 passed (14,96s)**, incluindo conexões independentes para notas/atribuição,
base de avanço concorrente e preservação de blocos pelos três writers. Gestor: **227 passed
(3,19s)**; typecheck passou (anterior à última alteração de mensagem de falha de refresh).
J02 sintético mantém texto durante SSE, J03 resolve conflito sem redigitação; sem medição
humana. Migração sem DDL; ações exigem expected_actor_id/base/chave em cliente coordenado.
Rollback conserva leitores/recibos e suspende mutações incompatíveis, sem reativar RMW antigo.
WP02/WP06 seguem em andamento; troca de recurso/pessoa com draft e demais comandos pendentes.

## Retomada — WP04: fato do courier e evidência do aviso

D04: o mesmo E/F volta a avaliar a derivação local após gravar uma única vez o fato
externo. A recusa de troco permanece explícita em todas as tentativas; só o operador
sintético com turno/valor explícito resolve a custódia no ensaio. F terminal é reconciliado
pelo polling existente antes de este encerrar, mesmo sem nova consulta ao fornecedor.
Leitura bloqueada compara a corrida observada com a atual; resposta antiga não altera
a substituta. Confirmar recebimento também relê sob lock. Sem novo campo JSON ou tabela.

D19: fila, processamento, aceite pelo serviço, omissão e ausência de confirmação histórica
são distintos. Recibo accepted é lido mesmo antes de o worker fechar; done sozinho não
comprova envio. Gestor e PDV dizem reenvio solicitado. Nenhuma frase comprova leitura humana.

PostgreSQL courier **32 passed (6,47s)**, incluindo E/F + recusa repetida, resolução canônica,
falha local após F e resposta antiga. São ensaios em PG, não prova de todos os interleavings.
Avisos/API **41 passed (16,52s)**; Gestor **227 passed (2,36s)**; PDV reenvio **3 passed
(4,05s)**. Preparação PDV inicialmente falhou (vitest ausente); npm ci isolado e repetição
resolveram. Ruff passou. Migração sem DDL, sem modificar recibos antigos; leitura histórica
sem prova permanece desconhecida. Rollback da apresentação não deve restaurar sucesso falso;
rollback do courier suspende derivação automática afetada, preservando fato e caixa.

WP04 ainda não concluído: enqueue durável de todas as fases, crash externo/worker e
homologação G03 continuam pendentes. Não houve rede externa de negócio ou efeito real.

## Retomada — WP07: reservas em lote, relógio e refresh

D20: states_for usa uma leitura SQL de Hold com Quant associado, incluindo reservas de
outros pedidos nos mesmos quants; o predicado canônico continua exigindo política congelada,
fermata e saldo agregado íntegro. Cards/Actions compartilham o resultado desta projeção;
comandos continuam revalidando. Não há cache durável ou fonte paralela.

D16: countdown ancora server_now_iso com tempo monotônico; drift do navegador ±5min e
reancoragem após retomada ensaiados. Fallback legado sem server_now continua Date.now;
latência de transporte/hidratação e suspensão real ainda não calibradas. Refreshs explícitos
coalescem burst de 100 eventos em leitura ativa + uma posterior; o fetch inicial conserva
os mecanismos defer do Nuxt. Não houve alteração de som, confirmação ou permissão.

PG **107 passed, 13 subtests (7,77s)**; Gestor **231 passed (3,14s)**; typecheck/Ruff passaram.
Preparação: primeiro comando apontou dois módulos inexistentes (nenhum teste executado);
nomes corrigidos. Primeiro teste de relógio não tinha DOM; happy-dom explícito resolveu.

20 amostras SQLite, macOS15.4.1 arm64: 1/10/100/500 cards agora **4/4/4/4 consultas**, com
**1/1/1/1 ao Hold**, em ambas as projeções (antes 4/13/103/503). Para 100 cards retiradas,
99 consultas Hold removidas conforme budget estrutural. Duas zonas 500: p50 **129,77ms**,
p95 **198,81ms**; baseline 218,03/265,70ms. Ensaios não controlaram carga concorrente do host;
não equivalem a HTTP/produção ou tempo humano. Payload aumentou com Actions/revisions:
**1.616.660 bytes** contra 872.660; custo de transferência e 2/10 clientes ainda pendentes.

Sem migração. Rollback pode reverter otimização mantendo predicados; custa consultas, não
altera reservas. Relógio/refresh são leitura apenas. WP07 não T: faltam payload rico,
estações, frescor E2E e budgets sob carga/controlados. O ganho em campo permanece não medido.

## Retomada — WP05/WP06: patch integral, publicação e editor

D05: keywords inteiras validadas antes do save; Product relido sob lock e patch/tags na
mesma transação. D06: matriz manual usa CollectionItem.sort_order; smart mantém seu resolver.
D07: validador fiscal extraído intacto do receiver para fiscal_catalog, consumido por save
e bulk; recusa do último item reverte o lote daquela superfície. Booleanos de todas essas
portas usam parser estrito existente. API traduz ValidationError em recusa 400.

D13/D14: editor/seleção de catálogo e feed só fecham com sucesso conhecido; lote distingue
count zero de falha (null). Feed expõe erro de leitura/escrita em vez de sugerir inexistência.
Essas proteções não tornam seguro repetir preço após resultado desconhecido: D12 é próxima fatia.

PG catálogo + gate fiscal **102 passed (27,66s)**; Gestor **233 passed (4,55s)**; typecheck e
Ruff passaram. Primeira edição introduziu IndentationError de import local (48 falhas comuns,
28 pass); corrigido. Nova fixture usou rota plural inexistente (1 fail/76 pass), corrigida.
Harness feed teve erro de sintaxe antes de coletar; corrigido antes do resultado final.
J10 sintético conserva seleção no erro sem redigitação; não medido em campo.

Sem DDL/novos campos JSON. Rollback preserva validação integral/fiscal ou suspende mutação;
reverter apenas ordem/editor não altera preços/dados. Limites: fan-out entre superfícies,
intenção/revisão de catálogo/feed, sync parcial, drafts entre SKUs e carga ainda pendentes.
WP05/WP06 continuam em execução, sem T.

## Retomada — WP05/WP02: reprecificação por prévia e intenção

D12: API de lote de preços exige prévia/base/pessoa/chave. A prévia congela células/tier,
valores exatos resultantes e configuração relevante; mudança em preço, coleção ou destino
recusa o lote. Confirmação bloqueia recursos, grava preços absolutos + CatalogSyncState +
enqueue existente + recibo atômicos. Nenhuma chamada ao fornecedor dentro dessa transação.
GET/replay não recalculam percentual. Cliente antigo sem precondição recebe 400. Gestor
mostra antes/depois para confirmação explícita, conserva editor no erro e consulta recibo
após resposta perdida. Schema novo gerado por export_orders_schema, sem mirror manual.

PG catálogo/schema/intenções **94 passed (32,48s)**: duas conexões/chaves na mesma prévia,
replay/lookup, fingerprint divergente, outra pessoa, legacy, segundo enqueue falhando,
falha ao salvar recibo, limite por destino e alteração de membership. Gestor **235 passed
(3,97s)**; typecheck passou. Uma tentativa inicial de unpack do helper foi corrigida para
seu dataclass antes dos testes; testes de preço iniciais 8/8 e principais 5/5 passaram.

Budget PostgreSQL local, 20 amostras sem backend externo e rollback de cada amostra:
10/50/100 células em dois destinos: **19 consultas**; p95 **26,43/40,29/45,15ms**.
100 células permanece limite provisório; números excluem HTTP/worker/provedor e aprovação
humana G06. J08 proposta: abrir preço → revisar → confirmar (3 ativações após seleção;
digitação contada separadamente); ainda falta jornada browser/Django e validação humana.

Sem DDL; recibo usa envelope já documentado. Rollback mantém lookup/dedupe e suspende lote
incompatível, nunca volta a reaplicar pct/delta por tentativa ambígua. Lote de publicação,
feed, célula e outros writers ainda não têm todo o protocolo de intenção/revisão; WP05
continua em execução. Estado de sync atual continua no CatalogSyncState, não no recibo.

## Integração local real — SSE, resposta perdida e confirmação de preço

Primeiro ensaio: avanço com resposta descartada passou; nota concorrente não apareceu
por SSE (1 passed/1 failed). Prova nova: save_kitchen_note não emitia evento, e eventos
de contexto existentes não invalidavam a fila. Correção usa OrderEvent canônico e
invalidação privada pós-commit, só ref/kind; não transmite texto da nota ao canal público.
Atores vêm de request.user. Rollback não publica invalidação.

Após correção: **26 testes Django passaram** (API/SSE); **3 testes Chromium integrados
passaram em 7,7s**, usando Nitro → Django → PostgreSQL e Redis reais, todos isolados.
1. POST de avanço efetivamente comita, navegador perde resposta: 1 POST + 1 GET de
recibo, estado preparando e próxima ação pronta. J04: nenhuma ativação extra.
2. Outro cliente salva nota: SSE atualiza contexto, mantém rascunho; conflito exige
“manter meu texto” e salvar (2 ativações adicionais, zero redigitação).
3. Preço: prévia mostra uma célula e não grava; confirmação explícita grava exatamente
10%. Após seleção: abrir preço, revisar, confirmar (3 ativações, digitação separada).

Harness e reprodução em orders-20260910/integration; logs anexos. Preparação: uvicorn
indisponível, Daphne existente utilizado. HTTP/1 local; HTTP/2 opcional não instalado.
Nenhum efeito externo ou worker separado. Esses ensaios não comprovam piloto/campo.
Sem DDL; rollback dos emissores volta a depender de polling e perde frescor imediato;
registro de eventos existentes pode permanecer, sem migração destrutiva. WP06/07 em
execução: identidade, carga e outros cenários ainda pendentes.

## WP03 — H02 provada e D15 revalidado

H02: duas conexões/turnos com instâncias antigas produziram colisão da chave de pagamento
seguida de TransactionManagementError; outra prova perdeu kitchen_note ao acertar usando
Order antigo. Não foi observada duplicidade financeira nessa corrida específica: a
constraint Payman recusou a segunda inserção, mas o comando não resolveu a concorrência.
Correção: transação externa, lock turno → pedido, releitura antes dos guards/merge;
serializa entre gavetas e mantém a autoridade existente do ledger. Sem política nova de
terminal: current_shift() e a decisão G02 continuam pendentes para o piloto.

PostgreSQL: **59 regressões passaram** (caixa/PDV/reconciliação/troco); **4 ensaios
específicos passaram**, incluindo duas custódias (um aplicado/um recusado), nota preservada,
turno já fechado e falha parcial no ledger revertendo Order/Payman/evento. Fixture inicial
usava Terminal.name inexistente; corrigida para label antes de revalidar a hipótese.

D15 persistia: backend e composables convertiam exceção em []; diálogos inferiam marketplace
pelo tamanho da lista. Agora consulta indisponível retorna 503 distinto do vazio confirmado;
loading/erro/vazio iFood impedem confirmar e mantêm diálogo/seleção, com consulta novamente
em uma ativação. Canal define o seletor. Servidor consulta códigos por referência antes
da transação, recusa ausente/antigo/inventado e revalida identidade externa sob lock; a
leitura não equivale a aprovação externa de cancelamento. Não altera transição comercial.

**77 testes Django** (iFood/API/novos) passaram; após proteção de identidade, **34 testes
Django** passaram. Gestor **237 passed**, typecheck passou. Cinco testes iniciais de UI
falharam: dois codificavam o comportamento antigo de esconder erro; três expuseram default
false de boolean opcional Vue. Contrato marketplace tornou-se explícito e testes corrigidos.
J11 sintético: repetir consulta com 1 ativação, sem fechar/reabrir; J05 código inválido aplica
zero mutações. Providers todos simulados, sem envio/cancelamento real. H03 e recibos de
cancelamento/COD ainda pendentes; WP03 não T. Sem DDL. Rollback mantém serialização/guards
ou suspende ações afetadas; não volta a ocultar falha externa nem remove lançamentos.

## WP06 — H06 comprovada, identificação e saída do editor

Dois ensaios de componente falharam antes: resposta da IA do SKU A aparecia em B;
resposta baseada no texto anterior aparecia após nova digitação. Agora sugestão confere
SKU/campo/base/geração e invalida ao desmontar; o painel informa SKU explicitamente.
Fetch de detalhe, salvar detalhe e prévia de preço também conferem recurso/geração/base;
resposta de um editor anterior não fecha/hidrata o atual. Removida prévia de lote que
havia sido inserida indevidamente também no popover de preço individual durante WP05.

Cache de leitura é separado por pessoa/recurso. Página permanece oculta durante bloqueio;
mesma pessoa retoma instância/draft, outra pessoa recebe nova instância. Detalhe tem chave
da rota e saída com texto não salvo exige descarte explícito. Login por senha passou a
usar refresh da sessão/leitura, como unlock PIN/crachá do kit, sem reload destrutivo.
Não há persistência de drafts após reload nem armazenamento de senha no contexto.

**240 testes Gestor passaram**, typecheck/build passaram. Um primeiro ciclo teve 29 falhas
por falta dos stubs Nuxt definePageMeta/onBeforeRouteLeave no teste da página; corrigido.
**5 jornadas Chromium reais passaram (10,1s)**: três anteriores + fechar A/abrir B com
resposta HTTP real atrasada + bloquear/reidentificar A preservando texto e trocar para B
sem herdar texto. Nenhum POST automático de nota após reidentificar; valor canônico ficou
igual. O primeiro ciclo de 5 jornadas encontrou 429 legítimo ao ultrapassar 5 logins/min;
fixtures agora distribuem usuários sintéticos, sem desativar rate limit. Teste subsequente
comprovou retomada por senha. H06 confirmado no componente e recurso errado prevenido no
painel real. J12: uma reidentificação e R=0 para a mesma pessoa, no escopo da sessão.

Sem migração; rollback de UI pode reintroduzir perda de draft e deve manter proteção de
saída/isolar pessoa. Ainda faltam contexto completo da fila/scroll, drafts de catálogo
protegidos na saída, carga/teclado/touch e retomada de todas as mutações; WP06 não T.

## WP04/WP02 — fases tardias duráveis e devolução com um dono

D18 revalidado: preparing/ready/dispatched/delivered/completed/returned não tinham marcador
nem recuperação. Essas transições agora criam `order.lifecycle_phase` no mesmo commit,
usando Directive + receipt permanente existentes. Claim/backoff/lease continuam no orderman.
Handler relê/bloqueia Order, grava efeitos locais/enqueues/marcador atomicamente. Child
handlers executam fora desse lock. Erro do marcador e enqueue não é silenciado. Fase
incompatível fica failed + alerta existente; não marca done por status avançado. Delivered
pode concluir em completed sem repetir a transição. Sweeper inclui fases tardias e dry-run;
tarefa failed conserva limite/alerta, sem reset automático. Fases iniciais existentes
commit/accepted/paid/cancelled conservam seus recuperadores, ainda sujeitos à matriz restante.

Mapa de efeitos desta fatia:

| Fase | Efeito/dono e evidência | Identidade/retomada |
| --- | --- | --- |
| preparing | KDS: ticket por session_key/line_id; aviso: notification_delivery | Phase receipt; ledger de fire + recibo original de aviso |
| ready | Fulfillment + flag atômicos; aviso; enqueue courier canônico | Order lock + phase receipt; courier ainda depende de H01/G03 |
| dispatched/delivered | Aviso; fechamento canônico após handoff | Recibo original de aviso; estado relido; completed tem tarefa própria |
| completed | Enqueue loyalty/fiscal, nunca prova de crédito/NFC-e externa | Phase receipt; ledger loyalty/adopção fiscal mantidos |
| returned | Fiscal/loyalty/aviso; estoque e estorno do registro exato de ReturnHandler | return_index + recibo de estoque; referência canônica de refund |

Prova nova necessária antes de retentar returned: uma unidade devolvida gerou **dois
Moves RETURN**, por lifecycle e ReturnHandler. Agora registro de devolução tem um dono
para itens/estorno. StockMovements + stock_processed ficam no mesmo commit sob lock.
Falha explícita de estorno preserva recibo de estoque e não marca refund_processed; retry
não recebe de novo. Registro legado incompleto sem versão/itens confiáveis exige inventário
humano, com alerta. Não inferimos que mercadoria/dinheiro físico voltou só pelo status.

Validações: **88 testes fase/lifecycle/refund passaram**, **15 testes focados passaram**,
incluindo dois workers e perda da gravação do resultado depois do commit da fase. Primeira
rodada teve 58 falhas: faltava registrar handler em register_all além do inventário; testes
de coordenação com MagicMock dependiam do antigo swallow do marcador. Registro corrigido;
marcador isolado nesses testes de routing, durabilidade testada com Orders reais.

Processos separados: seed terminou com **exit 17 intencional após commit**; worker novo
processou tarefa. Repetir worker manteve uma tentativa e um ticket KDS. Primeira verificação
revelou truncamento adicional D08 no KDS: `0.500 → 0`. Corrigido caminho Order/bundle/ticket/
projeção com decimal exato, mantendo inteiros históricos. Schema KDS exportado pelo comando
canônico. **63 testes Django KDS**, **44 testes KDS Nuxt**, typecheck passaram; nova prova
separada confirmou ticket único de **0.5**. Sem prova de trabalho físico executado.

Cadeia ampliada: **649 passed, 1 failed, 18 subtests**. Falha era spy antigo da fachada de
notas, que ainda esperava chamada sem actor/revision; ajustado ao contrato já implementado.
KDS npm ci isolado informou 4 vulnerabilidades (2 moderate/2 high) no lockfile existente;
nenhum audit fix automático nem atualização de dependências. Unidade histórica e quadro
com carga rica continuam pendentes; teste local não comprova redução de esforço em campo.

Migração expand: sem DDL; novos payloads documentados antes das escritas. Nenhum backfill
real. Retornos novos usam stock_receipt_version=1; incompletos antigos não são automaticamente
reexecutados. Rollback deve manter leitores/handler enquanto houver tarefas e suspender
writers incompatíveis; não voltar ao duplo recebimento nem apagar receipts/Movimentos.
G08 decide retenção antes de piloto. WP04 continua em execução: unknown remoto, demais
writers, histórico/concorrência e recuperação completa precisam das provas restantes.

Reteste do módulo da fachada após corrigir a expectativa: **6 passed**. Uma primeira
substituição textual usou nome singular do mock e não alterou a linha; o reteste capturou
isso, corrigido antes do resultado acima. A cadeia completa será repetida na validação final.

### WP04 — H01: tentativa courier de resultado desconhecido

Evidência anterior nova: provider sintético aceitou a primeira chamada e perdeu a resposta;
retry abriu segunda solicitação (1 failed, 32 deselected). Agora Directive.payload conserva
started antes da rede, unknown sem repetição, accepted antes de vincular Order. Aceite
conhecido recupera somente vínculo local; perda ao persistir aceite deixa started e exige
verificação. Dois workers distintos serializam a intenção no Order e apenas um chama o
adapter. A tarefa concorrente recusada registra not_applied + blocked_by, não inventa uma
segunda chamada desconhecida. Projeção e redispatch bloqueiam enquanto há recibo irresoluto.
Estimativa grava apenas sobre courier recém-relido sob lock; payload usa Order relido.
Mock agora devolve referência distinta em nova solicitação do mesmo pedido, sem supor
id_externo idempotente. Histórico de corrida já adotada continua reconhecido.

Validação PostgreSQL: **49 passed in 6.82s** (courier_service + machine_webhook), incluindo
falha ao adotar aceite, falha ao salvar recibo, tentativa legada sem recibo e dois workers.
Primeira rodada: 2 failed/31 passed (expectativa antiga de retry e mock reutilizava referência);
segunda: 1 failed/48 passed (callback automático consumia tarefa antes do ensaio concorrente).
O teste agora isola callback e executa explicitamente dois workers/conexões reais. Ruff passou.
Não houve consulta, despacho ou cancelamento externo real. G03 permanece pendente para
verificação homologada por referência: nenhum endpoint ou garantia do fornecedor inventado.

Migração: expand JSON, sem DDL/backfill. Retry legado attempts>1 sem recibo exige verificação.
Rollback não pode reativar worker antigo sobre started/unknown/accepted nem apagar receipts;
conservar handler/leitor e suspender somente dispatcher incompatível. Zero repetição automática
após resposta perdida; esforço humano e p95 da verificação externa ainda não demonstrados.
WP04 continua em execução pelas demais fronteiras/matriz; isto não declara piloto ou rollout.

### WP02/WP03 — H03: captura entre leitura e cancelamento

Revalidação nova (não cópia de diagnóstico): dois testes falharam antes da mudança.
Cancelamento com instância antiga apagava kitchen_note gravada por outro writer; timeout
que recebeu resposta antiga unpaid cancelava após captura Payman. Terceiro teste na API
provou captura entre avaliação da política e chamada de domínio: retornava 200 sem nova
aprovação. Os caminhos maduros de PIX tardio/estorno existentes foram preservados.

Implementação mínima: cancelamento canônico relê Order sob lock e grava contexto/transição
atomicamente. Os três caminhos de vencimento de pagamento passam a referência observada;
guard relê intenção/pagamento com lock Payman antes da transição. A política existente de
suficiência/unknown/cartão autorizado foi preservada. Gestor congela revisão da autoridade
já avaliada (estado, política existente, saldo/intenção); domínio compara sob Order→Payman
e recusa 409 quando mudou, sem suprimir PIN/permissão. Consulta de motivos externos fica
antes dos locks. Sem novas regras de autoridade nem escrita remota dentro desses locks.

Validações: **46 passed in 11.73s PostgreSQL**, incluindo captura em conexão separada enquanto
timeout espera a leitura do gateway; Order accepted, captura 5000q, estorno 0q. SQLite final:
39 passed, 1 skipped (somente concorrência PG), rodada anterior 45 passed com fachada.
Preparação do segundo banco de ensaio falhou inicialmente por TEST ausente no settings;
setdefault corrigido no bootstrap isolado, banco test_orders_lab_h03 separado da suíte ampla.
Ruff passou. Logs before/after anexos. Nenhuma transação financeira externa foi executada.

Migração/rollback: sem DDL/payload novo; keyword interna opcional para compatibilidade de
callers confiáveis. Rollback é revert local, mas reabre as janelas demonstradas; não liberar
piloto com leitores antigos contornando o guard. Guard não equivale ao contrato completo de
intenção dos demais comandos. WP03 segue em execução: timeout de confirmação versus ação
do operador e demais fronteiras da matriz ainda precisam das provas próprias.

### WP06/WP08 — última leitura e identidade na caixa pessoal existente

Prova anterior: GET bem-sucedido seguido de 503 apagava lista/contador; teste falhou.
Agora falha conserva última leitura com indicação de desatualização e botão Atualizar;
falha de mark-read não finge sucesso. 401 pede reidentificação; 403 informa permissão.
Troca de pessoa limpa contexto e invalida resposta atrasada; sem pessoa identificada não
consulta inbox/acessos nem abre SSE. SSE reconecta na mudança de identidade. Sem mudança
no escopo de ack, destinatários, cadência de 60s ou nova superfície (G01/G04 preservados).

O coalescedor já existente foi movido para operator-kit e reexportado pelo Gestor: não há
segunda implementação. Cem triggers durante leitura produzem no máximo uma ativa e uma
pendente. **228 testes do kit passaram**, incluindo perda de resposta de leitura, 503,
identidade A→B, re-gate 401, recusa 403 e rajada. Typecheck Orders passou. O ensaio é de
composable/DOM isolado; não mede frescor em campo nem valida autoridade organizacional.
Migração: sem persistência/DDL; estado em memória por pessoa. Rollback por revert do cliente,
com risco explícito de voltar a representar falha como inbox vazio. WP08 ainda depende dos
outros contratos completos; esta proteção não declara o pacote integralmente concluído.

### WP05 — publicação em todos os canais sem aplicação parcial

Prova nova: validação recusada no segundo destino deixava PAO publicado em web (primeiro
canal). Agora bulk_set resolve destinos de venda, bloqueia Channel→Product→Listing→Item,
valida todos pelos validadores fiscais existentes e grava numa transação. Falha de enqueue
também desfaz todas as alterações. Sincronização usa CatalogSyncState/Directive existentes,
fora da escrita local; não chama provider mantendo locks. Display mantém adaptador próprio.
Envelope provisório de 100 células/faixas limita essa operação local; não é SLA de campo.

**105 testes PostgreSQL passaram** (API catálogo + gate fiscal), incluindo recusa no segundo
canal, falha no segundo enqueue e ausência de chamada de provider na escrita. Rodada SQLite
anterior: 103 passed. Ruff dos arquivos alterados passou. Sem publicação externa real.
Sem DDL/backfill; rollout precisa drenar/monitorar tarefas existentes. Rollback deve conservar
recuperador de sync pendente, nunca reaplicar preço para recuperar projeção. Prévia/intenção
dos demais comandos de catálogo/feed e revisão de todos os writers continuam em WP05.

### WP09 — preparação dos gates, ainda sem conclusão da fase

Cores canônicos: executar pytest no diretório/configuração de CADA pacote, importando
somente pacotes do worktree. Todos os 12 passaram; log por pacote consolidado anexo. A
primeira execução indiscriminada de `pytest packages` com settings da aplicação produziu
231 failed/2418 passed/18 skipped: URLs 404 e configuração de orquestrador incompatível.
Essa rodada inválida não é diagnóstico de regressão nem gate aprovado. Nenhum core foi
modificado para acomodar o runner. Skips das suítes canônicas permanecem registrados.

Ruff completo inicialmente apontou 35 erros, sobretudo imports/estilo dos scripts de ensaio
adicionados. Corrigidos sem alterar resultados/algoritmos (lambda agora vincula body no
loop). Ruff completo passou. Gate silent-swallow encontrou três sites nos arquivos tocados:
escopo SSE, emissão SSE de courier e ImportError no cancelamento KDS. SSE agora registra
warning; ausência do serviço KDS propaga falha para recuperação, não conclui silenciosamente.
Gate passou; reteste lifecycle/courier/eventstream: **118 passed, 1 skipped** (concorrência PG).

Migrations gate: três checks passaram (nenhuma migration faltante, banco SQLite vazio e
migrate --check). Dois skips explícitos: tag go-live-v1 ausente; nenhum snapshot baseline
real autorizado/declarado. PostgreSQL sintético também foi migrado nos ensaios anteriores.
Workflow budgets passou. Constraints cobriu os 100 pacotes de imagem; versões disponíveis
mais recentes foram informadas, sem atualização dos pins. Sem build/deploy de produção.

Orders Nuxt após inbox/coalescedor: **240 testes passaram**, typecheck passou; operator-kit
**228 passaram**. Não somar suites sobrepostas como cenários independentes. Suíte ampla
shop/backstage/storefront ainda em execução e com falhas a triar; WP09 NÃO concluído.

### WP01/WP02 — confirmação com intenção, incluindo seleção de pedidos

Prova anterior: repetição da mesma chave confirmava uma vez mas devolvia 409 sem recibo;
cliente sem chave ainda confirmava. Agora Action confirm anuncia a base e API usa o mesmo
helper de recibo atômico, escopo pessoa/operação/ref e GET puro já usado em contexto/avanço.
Guard compara revisão sob lock antes da confirmação canônica. Recusas de domínio são
not_applied; cliente antigo não contorna a exigência. Nenhuma nova máquina de estados.

Board/detalhe usam transporte de intenção existente. actMany também usa uma intenção por
ref; página conserva selecionadas as falhas, retirando somente resultados conhecidos.
Não há atomicidade fictícia entre pedidos. Confirmação e permissões existentes preservadas.

**32 testes PostgreSQL passaram**, 32 SQLite, **240 testes Orders Nuxt passaram**, typecheck
passou. As primeiras rodadas detectaram testes antigos sem contrato e um caso tentando
obter Action confirm de pedido já accepted; atualizado para testar recusa autoritativa com
intenção explícita. Cinco fixtures frontend também não declaravam Action nem outcome;
agora modelam o contrato real, mantendo o teste próprio que recusa cliente legado.
Migração sem DDL; publicar cliente compatível antes de exigir contrato em ambiente autorizado.
Rollback não pode reabrir confirmação sem intenção; conservar recibos e GET durante G08.
Concorrência/retomada dos demais comandos e jornadas completas seguem no escopo pendente.
