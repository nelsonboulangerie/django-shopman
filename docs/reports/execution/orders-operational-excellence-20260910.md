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

### WP09 — triagem da suíte ampla PostgreSQL

Rodada ampla iniciada após e258b01d6: **8494 passed, 61 failed, 16 errors, 35 skipped,
26 deselected, 38 subtests, 3 warnings**, 1223.52s. Módulos já carregados nessa rodada não
validam automaticamente as mudanças posteriores; estas têm retestes próprios.

Falhas atribuíveis à evolução do contrato: testes MagicMock de configuração chamavam o
marcador persistente e dependiam do antigo swallow; agora isolam somente o marcador nos
testes de roteamento, preservando provas reais de durabilidade. Teste C14 esperava estoque/
estorno a partir de status returned sem registro de itens; agora exige tarefa failed+alerta,
sem inventar recebimento. Os ensaios de ReturnHandler continuam comprovando o caminho com
registro autorizado e recibo único. Três catches novos já alertavam/relevantavam fora da
janela de quatro linhas do gate de higiene; adicionado log explícito imediato, sem elevar
baseline. **121 passed, 2 skipped** no reteste lifecycle/config/conformance/courier/returns.

Outros grupos mostram SQL PostgreSQL de base (FOR UPDATE com DISTINCT/outer join), tamanho
de posição de forno e ordem de chaves JSON em teste. Atribuição definitiva ainda em ensaio:
base 5a3383c9 extraída por git archive em diretório de laboratório, sem alterar checkout de
terceiros; repetição dos 14 módulos problemáticos em andamento. Não são descartados como
“preexistentes” sem essa prova, nem a rodada ampla é marcada verde.

### WP05/WP06 — leitura confirmada do feed

Teste novo confirmou que o GET de refresh com 503 apagava board, embora o banner prometesse
“última leitura disponível”. O composable agora conserva somente a última resposta válida
na instância de página pertencente à pessoa; erro continua visível e não vira convite de
criar feed. Sem cache persistente, sem mudança de origem Channel/config.display.
Resultado técnico: suíte Orders com **241 testes passou**. Migração inexistente; revert
retorna à perda de contexto. Intenção/revisão das mutações de feed ainda precisa fechar J10.

### WP09 — atribuição final das falhas de suíte (21:26)

PostgreSQL amplo: 8.494 passed, 61 failed, 16 errors, 35 skipped, 26 deselected. A reprodução dos 14 módulos na base imutável `5a3383c9` confirmou exatamente 45 failed + 16 errors iguais; 263 passed. Falhas preexistentes: locks com outer join em marketing, DISTINCT no merge Guestman, fixture Oven excedendo varchar e ordem de chaves JSONB. As 16 falhas exclusivas da implementação foram corrigidas em `6a8daa373` e revalidadas (121 passed, 2 skips); isto não transforma a execução ampla original em verde.

SQLite amplo no HEAD `6a8daa373`: 8.551 passed, 8 failed, 56 skipped, 28 subtests, 585,14 s. A triagem dos cinco módulos passou integralmente: **178 passed, 10 subtests**. Cinco testes de cancelamento usavam objetos simulados sem banco, incompatíveis com a leitura sob lock; agora verificam persistência real e ator/motivo. Dois subtestes falhavam na serialização xdist de Path/Enum; somente os parâmetros de diagnóstico viraram strings. A cópia auditada local confundia o scanner do gate: foi movida para `/Users/pablovalentini/Dev/Claude/.codex-worktrees/orders-audit-base-5a3383c9`, fora da árvore de código, sem relaxar o gate. Logs originais preservados no laboratório. Migração: nenhuma. Rollback: revert dos ajustes de teste; não remover locks do cancelamento.

Feed: a versão final do watcher foi reexecutada, **241 testes Orders aprovados** (`feed-final-unit.txt`).

### WP07 — fila rica: leituras Payman e ChannelConfig em lote

Evidência anterior reproduzida: 10 pedidos, 3 itens fracionados e 6 eventos cada, pagamento capturado, Hold planejado e contexto de entrega geravam **50 consultas Payman**. Depois de corrigir somente Payman, 500 pedidos ainda faziam 457 consultas; a segunda testemunha isolou **9 leituras Channel para 10 pedidos**. Não era uma hipótese baseada só no plano.

Implementação: `PaymentService.read_many` agrega os mesmos tipos de transação canônicos em uma instrução SQL. A projeção fornece observações explícitas aos mesmos guards; não grava cache no Order, não usa estado global e não envia observações ao comando. ChannelConfig é resolvido uma vez por canal na requisição, pela cascata existente. Falha de leitura financeira continua `unknown`, sem confiar no status embutido. O tratamento vigente de chargeback não foi modificado neste pacote de desempenho; sua adequação operacional ainda exige a matriz H03.

Testes: **78 passed + 13 subtests** no PostgreSQL (fila/Actions/gates), **4 passed** de isolamento SQLite, Payman canônico **189 passed, 2 skipped, 2 subtests**. Provas: 100 intents com múltiplas transações concordam com as somas individuais; estorno posterior ao snapshot bloqueia a próxima ação; alteração do canal posterior à leitura é relida na confirmação; intent ausente/falha permanece desconhecido.

Ensaio sintético `rich_queue_assay.py`, PostgreSQL local, 20 amostras por cenário, projeção + JSON (não HTTP), cache do processo aquecido:

| Pedidos | Consultas | p50 ms | p95 ms |
| --- | ---: | ---: | ---: |
| 1 | 7 | 4,17 | 4,69 |
| 10 | 8 | 7,57 | 7,92 |
| 100 | 8 | 38,63 | 44,76 |
| 500, um leitor | 8 | 171,24 | 238,82 |
| 500, dois leitores concorrentes | 8 | 402,41 | 454,18 |
| 500, dez leitores concorrentes | 8 | 1.826,04 | 3.071,05 |

Em 500 pedidos, após apenas o lote Payman o p95 era 453,87/718,30/4.061,02 ms (1/2/10 leitores); resolver canais uma vez reduziu esses valores, sem mudar os 1,6 MB aproximados da resposta. A testemunha inicial de 10 pedidos rodou junto da suíte ampla: sua latência não é comparação controlada. A primeira preparação falhou por ausência de `Hold.target_date`; fixture corrigida, sem mascarar o erro. Os dois ensaios finais completos estão arquivados com todas as amostras, primeira leitura e contagem por tabela. Dez threads compartilham um processo Python; não equivalem a dez dispositivos nem a um pool de servidores. **Budget concorrente de 500 ms não demonstrado para dez clientes; HTTP/BFF/render e campo permanecem pendentes.** R e A não mudam por este ajuste; nenhuma confirmação foi retirada.

Migração: nenhuma, nenhuma tabela ou configuração nova. Rollback: revert deste commit volta às leituras individuais; recibos, histórico e regras permanecem íntegros. Nenhum efeito financeiro, fiscal ou externo foi executado.

### WP02/WP03/WP06 — recusa e cancelamento por intenção

Antes: ambos os POSTs devolviam somente sucesso/erro e o cliente reenviava sem chave após uma resposta perdida. Cancelamento já tinha política, assinatura e proteção da revisão financeira; esses guards foram preservados. Recusa já relia status e identidade externa sob lock.

Agora: ambos exigem ator, base opaca e intenção; efeito e recibo local são atômicos. Consulta GET e replay respondem sem repetir política/provedor após commit. A preparação de motivos iFood ocorre fora da transação; identidade e revisão são revalidadas dentro dela. O fingerprint normaliza motivo/código/base e exclui credenciais. A Action de cancelamento permanece no detalhe com a mesma política/permissão e confirmação explícita; recusa conserva seu motivo e código.

Assinatura: o endpoint existente retorna 422 para desafio de gerente. O cliente conserva a chave e o motivo ao apresentar esse desafio, envia a assinatura apenas na tentativa corrente e **não retém PIN** na intenção. Não houve alteração de autoridade nem aprovação automática. J04: resposta perdida permite GET do recibo, sem segundo efeito. J11: motivos indisponíveis continuam erro tipado; J12: assinatura não exige redigitar o motivo. Medição em campo permanece pendente.

Validação PostgreSQL: 49 passed + 5 subtests de políticas/API/domínio, 8 passed de recibos e captura concorrente, 69 passed + 13 subtests de Actions/contratos/recibos (grupos se sobrepõem, não somar como testes únicos). As testemunhas verificam consulta externa fora de `atomic`, um único evento, replay sem nova consulta/assinatura, conteúdo diferente com mesma chave rejeitado, clientes sem contrato sem efeito e PIN ausente no recibo. Orders: **242 passed + typecheck**. Preparação inicial dos novos testes falhou por tentar alterar canal selado e por supor 403 no desafio (o contrato é 422); corrigidos os testes e o cliente, preservando o selo e o HTTP existente. Fixtures de UI receberam Actions reais do novo contrato; os testes continuam cobrindo motivo, conflito e assinatura.

Migração: nenhuma tabela/coluna. Consumidores HTTP desses dois comandos precisam enviar o novo contrato; clientes antigos recebem recusa antes de efeito. Retenção segue a infraestrutura vigente, G08 pendente. Rollback: revert coordenado de API/UI deste commit; preservar recibos e não repetir manualmente cancelamentos já aplicados. Nenhum cancelamento real, comunicação externa ou estorno foi realizado.

### WP09 — integração real local atualizada em `ea46e2cd8`

Backend reiniciado apenas no processo próprio de laboratório; Nuxt reconstruído apontando para 8014. Seed gerou refs novas e usuário dedicado para cancelamento. **6 testes Playwright/Chromium passaram em 32,5 s**, sem retry: avanço com resposta perdida (1 POST + 1 GET), SSE durante nota divergente, preço exato após prévia, resposta atrasada de produto A após abrir B, lock/reauth da mesma pessoa e isolamento da outra pessoa, cancelamento com resposta perdida (1 POST + 1 GET). Nenhum adaptador externo ativo. O teste de cancelamento exige abrir o diálogo, informar o motivo e confirmar; a recuperação não pede redigitação nem nova confirmação de um efeito já aplicado. A execução coincidiu com a suíte ampla, portanto seus tempos não são benchmark de budget. Isto comprova integração sintética, não piloto nem rollout.

### WP02/WP05/WP06 — feeds: intenção, revisão e rascunho por recurso

Defeito revalidado em PostgreSQL: o serviço de `e5eb4b521`, carregado somente no processo do teste, perdeu `collections` na concorrência entre seleção e rotação (1 teste falhou com `[]` em vez de `[bread]`). Mesmo teste com o serviço atual passou. O ensaio pausou a primeira gravação e iniciou outra conexão; não houve acesso a plataforma externa.

Implementação: todos os escritores locais de `Channel.config.display` deste serviço (incluindo pausa individual/lote) relêem sob lock; rotação, coleções e ativação têm revisões independentes. Os três POSTs exigem intenção/ator/base; recibo e efeito confirmam juntos e GET recupera o resultado por pessoa/feed/operação. Rollback após gravação antes do commit preserva o canal e não deixa recibo falso. SSE continua no callback pós-commit existente. Não foi criado Feed/Listing/preço próprio.

Actions e tipos de feed agora saem do exportador existente de Orders; removido o espelho manual que ainda chamava Channel de model Feed. A página mantém rascunhos em memória por feed/pessoa, inclusive ao fechar e reabrir o popover. A base é a de abertura do editor; atualização concorrente não a substitui. Conflito mostra o valor atual, conserva seleção/valores e exige `Manter…` ou `Usar valor atual` antes de aplicar. Sair da página com alterações pede confirmação; descartar é explícito. Nenhuma gravação em localStorage, ampliação de autoridade ou publicação real.

Testes: 34 passed PostgreSQL de feeds/schema/motivos iFood, seguido de 21 passed nos escritores/API incluindo pausa individual/lote e rollback (há sobreposição); **244 testes Orders e typecheck aprovados**. Falhas de preparação da UI: harness não implementava o hook de navegação nem `window.confirm`; stubs adicionados com verificação de que recusar a saída mantém o rascunho. J10: perda da resposta consulta 1 GET com a mesma chave/ref, sem segundo POST; R=0 no teste. Conflito exige decisão explícita, não força redigitar. Navegador integrado da nova tela de feeds ainda não ensaiado; resultados de UI são Vue/Vitest.

Migração: nenhum DDL nem campo persistido novo. API/UI/export precisam andar juntos; clientes antigos são recusados antes da mutação. Rollback: revert coordenado, preservando recibos; retorno às leituras sem lock reabre o defeito, portanto não é estratégia de rollout. G05/G08 e ganho em campo continuam pendentes.

Suíte SQLite iniciada em `ea46e2cd8`: 8.565 passed, 3 failed, 56 skipped, 38 subtests, 694,13 s. Duas fixtures de indisponibilidade iFood ainda enviavam o contrato antigo; atualizadas e aprovadas mantendo a exigência de 503 sem efeito. A terceira foi o drift de schema porque o arquivo foi regenerado para feeds enquanto o processo da suíte ainda tinha o renderizador anterior importado. A execução ampla não é declarada verde; o teste em processo fresco passou. Próxima execução ampla deve usar árvore estável durante todo o ensaio.

### WP02/WP03/WP08 — comentário e devolução de equipamento

Testemunha anterior: `mark_equipment_returned` usando instância antiga apagou nota concorrente (1 failed). Agora a custódia é relida sob lock e gravação/evento ficam no mesmo commit. Revisão de equipamento cobre somente seus campos de custódia, preservando notas/atribuição; comentário é append-only, com revisão da identidade selada, e não conflita com outro comentário legítimo.

Os dois comandos exigem intenção/ator/base e devolvem recibo consultável. Um replay não duplica comentário ou evento de retorno. A pendência `equipment_out` existente carrega sua própria Action autorizada: **pedido completed continua permitindo registrar o aparelho que efetivamente voltou**, sem reabrir venda nem inferir dinheiro. O cliente usa essa Action mesmo se o pedido saiu das colunas ativas. Permissões e gesto físico existentes foram mantidos; nenhum aparelho ou valor real foi movimentado.

Validação PostgreSQL: 26 passed dos caminhos afetados + 3 passed de recibo/pendência completed. Orders: **245 passed + typecheck**. Os testes conferem um evento por intenção e desaparecimento da pendência após o retorno. Export de schema regenerado pelo comando existente. Migração: nenhuma. Rollback: revert coordenado de UI/API/schema, conservando recibos; retirar o lock reabre perda de contexto, portanto não deve ser usado como mitigação de rollout.

Validação ampla independente em andamento: worktree `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-orders-validation-20260910`, branch `codex/orders-validation-20260910`, fixado em `9eb5d9525`. Os próximos commits não alteram aquela árvore durante a execução.

### WP02/WP04 — recibos de reprocessamento fiscal e reenvio do link

- **Antes:** `fiscal-requeue-before.txt` reproduz 1 falha: com emissão solicitada, sem backend e sem Directive, o serviço anunciava reprocessamento e emitia evento sem trabalho enfileirado. O resolver fiscal permanece dono da regra; a correção exige evidência concreta de enqueue.
- **Implementação:** ambos os comandos do Gestor usam intenção por pessoa/operação/pedido, revisão relevante, GET de recibo e commit local único. Reprocessamento trava Order e Directives fiscais, relê e preserva o mesmo mecanismo de retry/adoption. Reenvio trava Order/Payman, relê e conserva URL, consentimento e cadência existentes. Resposta informa `queued` e Directive; não afirma entrega/emissão. POS conserva seu contrato HTTP e recebe a proteção de estado fresco no serviço compartilhado.
- **Testes:** 61 testes PostgreSQL de serviços/API passaram; 5 adicionais provaram ausência de falso enqueue, resposta perdida consultável, replay único nas duas ações, revisão obsoleta sem efeito e cadência contra uma segunda intenção. Orders: 245 testes e typecheck passaram. Ruff dos arquivos alterados e diff-check passaram. Adaptadores externos não foram executados.
- **Esforço:** J14 mantém 1 ativação; perda de resposta usa GET automático (0 redigitação). J13 fiscal só confirma agendamento comprovado; falha de configuração permanece junto ao pedido. Nenhuma medição em campo.
- **Migração/rollback:** sem DDL; novos escopos usam IdempotencyKey existente e retenção vigente. Manter API/UI na mesma versão; reversão dos arquivos remove novo protocolo sem excluir recibos ou Directives. Não repetir efeito desconhecido após rollback. Retenção alternativa continua em G08.
- **Limites:** fila fiscal não comprova aceite remoto; recuperação remota/homologação continuam dependentes de G03. Esta fatia não conclui os WPs inteiros.

### Gate amplo em fonte imutável

O ensaio SQLite em worktree de validação fixado em `9eb5d9525` terminou com **8574 passed, 57 skipped, 3 warnings, 38 subtests passed**, em 767,39 s. Log integral: `orders-20260910/broad-runtime-stable-9eb5d9525.txt`. Os skips não são ensaios PostgreSQL aprovados; as 3 advertências são de testes que substituem DATABASES. Equipamento/comentário e fiscal/link posteriores têm validações direcionadas separadas. A execução anterior contaminada por edição simultânea não foi renomeada como sucesso. Os achados PostgreSQL reproduzidos na base continuam explicitamente registrados.

### WP04/H03 — cobrança enfileirada e estado que mudou antes do worker

A testemunha anterior confirmou que o handler ainda chamava a entrega do link depois de cancelamento/vencimento. O caso de captura inicialmente usou indevidamente `PaymentService.settle(card)` e falhou na preparação: esse serviço exige atestação para cartão. O fixture corrigido usa create_intent/authorize/capture, somente livro sintético, sem gateway. Não contamos aquela falha como evidência da corrida.

O handler agora reutiliza `payment_link_resend_refusal` imediatamente antes da entrega e grava `notification_delivery.skipped` com o motivo canônico. A projeção explica pagamento recebido, cancelamento ou vencimento; não os chama de envio. A mesma evidência accepted continua impedindo novo envio no replay. Não se adicionou regra de pagamento ou consentimento.

**Validação:** 62 testes PostgreSQL passaram (novos casos + consentimento, reenvio, produção/avisos). Logs de preparação e resultado preservados. Ruff e diff-check passaram. Não há DDL/migração de dados; rollback reverte handler/copy e conserva as evidências gravadas. Limite: cobre mudanças já confirmadas antes da leitura do worker; não prova exclusão mútua com captura durante a chamada remota nem aceite perdido no fornecedor. G03 continua necessário para essa fronteira externa.

### WP02/WP03 — recibo e turno observado no acerto COD

- **Evidência anterior:** a serialização Shift→Order já impedia o segundo lançamento (proteção em `test_cod_custody_concurrency`); o endpoint ainda não tinha GET de recibo e o facade chamava `current_shift()` sem o modo estrito já existente. Uma nova gaveta/turno entre leitura e gesto não fazia parte da precondição. Não recriamos o ledger nem sua constraint.
- **Implementação:** intenção atômica no Gestor para acerto, revisão de status/total/payment/dispatch e turno/terminal aberto, validação sob Shift→Order. O resolver canônico estrito recusa ambiguidade entre gavetas; não se escolhe uma nova custódia. Projeção em lote consulta esse contexto uma vez, apenas quando há COD elegível, e GET não cria terminal. Card/detalhe usam Action autorizada; diálogo identifica caixa/turno, congela a revisão ao abrir e mantém valores se atualização exigir conferência explícita. A confirmação física e os campos de troco/aparelho continuam existentes.
- **Testes:** 27 PostgreSQL passaram, incluindo 4 novos: resposta perdida + replay com exatamente um PaymentIntent/Entry/evento; substituição de turno recusada; duas gavetas recusadas sem nova atribuição; falha ao persistir recibo desfaz Order/Payman/Entry. Concorrência com duas conexões e rollback do ledger anteriores permanecem verdes. Orders: 247 testes (incluindo componente real de troca de turno sem redigitação e Action bloqueada no card); typecheck e Ruff/diff-check passaram.
- **Esforço:** caminho normal conserva abertura/conferência/confirmação (J06); troca de turno acrescenta uma conferência explícita, R=0. O total conhecido aparece na confirmação; vazio usa o total canônico, nunca valor inventado. O ensaio não atesta dinheiro físico.
- **Migração/rollback:** sem DDL ou reconciliação real. Recibos no escopo vigente; reverter API/UI juntos, conservar livros/chaves, nunca reexecutar uma intenção já aplicada. A proteção do ledger e Shift→Order é independente do cliente.
- **G02 pendente:** decidir estação→terminal e entrega física entre responsáveis antes de habilitar a coorte com múltiplas gavetas. Nesta fatia essa capacidade fica bloqueada pelo resolver existente, em vez de assumir autorização. Nenhuma nova permissão financeira foi concedida.

### WP06/WP07 — leitura preservada e rajadas no detalhe/feeds

A revalidação encontrou o detalhe removendo todo o conteúdo quando `error` ficava preenchido, mesmo com pedido ainda disponível; a fila tinha a mesma exclusão visual. Agora mantêm leitura confirmada na falha, exibem explicação separada e recusam nova mutação até obter leitura válida. O textarea permanece o mesmo elemento DOM, sem reconstruir o draft. Estado continua limitado à instância/cache de pessoa; nenhuma persistência após reload foi introduzida.

Detalhe e feeds reutilizam `operator-kit.coalesceRefresh` (uma ativa, uma posterior), com dedupe de transporte e recuperação da identificação. SSE do pedido refaz leitura ao reconectar; feeds têm poll de 30 s e atualização ao acordar/reconectar. Não se confunde SSE conectado com leitura recente. Um recibo já aplicado permanece sucesso mesmo se apenas a leitura posterior falhar; a mensagem distingue os dois fatos e não sugere repetir o comando.

**Testes:** 252 Orders passaram, incluindo 503 com leitura preservada/zero POST, dez disparos reduzidos a duas leituras, textarea preservado no componente e sucesso confirmado com GET posterior falhando. Typecheck passou. **Limites:** poll de 30 s é configuração, não medição de p95; ainda são necessários ensaios integrados atuais. Sem DDL/migração; rollback reverte composables/templates e não altera recibos. G05/G08 continuam pendentes para pós-reload.

### Revalidação integrada em `92d97d01d`

Nuxt/Nitro reconstruído para Django local 8014; Daphne reiniciado após conferir PID **e cwd** do próprio laboratório. Seed novo cria apenas pedidos/coleção/display/turno sintéticos no PostgreSQL próprio; sem worker de comunicação/fiscal/courier. **9 testes Chromium passaram em 43,3 s, sem retries**, via HTTP real + Redis/SSE. As seis jornadas anteriores continuam verdes e foram acrescentadas:

1. Acerto COD com resposta descartada **depois** do commit: 1 POST/1 GET de recibo, turno mostrado, diálogo fecha apenas após confirmação do resultado; nenhuma segunda submissão.
2. Coleções do display com resposta perdida: 1 POST/1 GET com a mesma ref, seleção canônica exata e editor fecha após recibo.
3. GET 503 com nota dirty: textarea visível/conteúdo preservado, explicação persistente, tentativa de salvar faz **zero POST** enquanto stale.

Screenshot de nota inspecionado visualmente: ref/valor/quantidade fracionária/nota/histórico aparecem no recurso correto, sem corte do editor. Ainda não constitui ensaio com leitor de tela ou hardware do operador. O tempo total inclui inicialização (a primeira jornada levou 21,4 s); não é p95 de interação nem comprova budget em campo. Livros reais, provedores e rollout não foram exercitados. Seed/testes/log reproduzíveis estão em `orders-20260910/integration/` e no teste Playwright versionado.

### WP03/WP04 — H03 reclassificada por mais três testemunhas

**Antes:** PostgreSQL reproduziu três violações: self-cancel após leitura permitida ainda cancelava quando captura já havia chegado; instância anterior ao preparo ainda cancelava; timeout auto_cancel lia NEW, operador confirmava com sucesso em outra conexão, e o timeout depois cancelava ACCEPTED. `h03-confirmation-before.txt`: 3 falhas, nenhuma inferida apenas de código.

**Implementação:** self-cancel trava Order→Payman, relê e aplica a MESMA `payment.can_cancel`; devolve bool ao facade e a API responde 409 quando a decisão concorrente vencer. Permissões, acesso ao pedido e política de captura/estado permanecem existentes. O timeout compara NEW dentro do commit da transição; auto-confirmação revalida pagamento/confirmabilidade sob Order→Payman. A chamada remota de cancelamento do pagamento permanece fora desse helper local. Auto_cancel continua política configurada, sem nova autoridade.

**Testes:** 50 PostgreSQL passaram (barreiras, cancelamento fresco, conformance, customer orders); 8 adicionais/overlap passaram (barreiras/API + IDOR), incluindo captura entre leitura da API e comando, respondendo 409 sem cancelar. No teste com duas conexões, qualquer decisão pode vencer o lock, mas nunca se reporta aceite do operador seguido de cancelamento por timeout obsoleto; exatamente um evento de transição. Ruff e diff-check passaram.

**Migração/rollback:** sem DDL. Compatibilidade do facade passa de retorno ignorado a bool explícito; chamada HTTP antiga continua protegida pelo guarda sob lock. Reverter API/facade/domínio juntos, sem apagar eventos, Directives ou recibos. Nenhum cancelamento real executado. Esta prova não encerra todos os interleavings H03 nem constitui piloto.

### WP03/H03 — pagamento estável do guarda ao commit

A primeira preparação usou timing `pre_commit`, inexistente neste checkout; as falhas de configuração foram registradas, não classificadas como corrida. Com `at_commit` válido, **2 falhas/1 proteção aprovada**: confirmação e avanço manuais podiam transicionar após refund já comprometido na janela entre guarda e transição; timeout já protegido em `e123ff737` passou.

Os comandos agora mantêm Order→Payman durante o guarda e commit, pelo helper local `payment.lock_order_payment` (nenhuma rede), também reutilizado pelo timeout e self-cancel. Ele trava os intents por Order e a referência efetivamente lida, em ordem de PK. Não muda a regra de saldo ou cria livro paralelo. O teste mede saldo no ponto imediatamente anterior à transição em uma conexão enquanto outra tenta o refund canônico; o refund conclui depois do commit quando o comando ganha.

**Validação:** 17 PostgreSQL passaram na matriz/barreiras/leitura; 92 + 18 subtests passaram nas regressões de projeção, política, APIs e contrato do operador. A testemunha de mudança de config da fila também foi corrigida para `at_commit` válido. Ruff/diff-check passaram. **Migração/rollback:** sem DDL, trava de linha transitória; reversão conserva Payman/eventos/chaves. Budget de contenção sob carga ainda precisa medição, e o lock não equivale a reconciliar um provedor real.

### WP03 — saldo do Payman inclui valores devolvidos por chargeback

A lacuna mantida aberta no ensaio de leitura foi revalidada pelo contrato canônico de `packages/payman/shopman/payman/service.py`: dinheiro ainda disponível é `captured_total - refunded_total - chargeback_total`, e chargeback **não altera status**. Três testemunhas PostgreSQL falharam antes: chargeback parcial/total continuava disponível para preparo/novo refund, e refund+chargeback mistos divergiam do livro.

A correção só alinha a leitura do shop (ao vivo e batch) à soma já definida pelo Payman. Não cria estado de pagamento nem nova política financeira; a política existente volta a receber o saldo correto. A regra de suficiência continua comparar o saldo com o total: 2000 capturados menos 200 refund e 300 chargeback ainda cobrem total 1500. A leitura batch conserva uma query; a leitura direta agrega também chargeback. Os guards/recuperadores que já usam o saldo canônico passam a respeitar valores já devolvidos.

**Testes:** 195 PostgreSQL passaram (novos saldos, batch, webhooks de disputa, refund idempotente, política de cancelamento, serviços). Sem adaptador externo real. Ruff/diff-check passaram. **Migração/rollback:** sem DDL ou reconciliação histórica; fatos persistidos intactos, somente cálculo de leitura corrigido. Reverter read-side restaura a divergência conhecida, por isso capacidade afetada deve permanecer bloqueada se revertida. Aprovação de ações/custódia continua em G01/G02; não foi concedida nova permissão.

### WP05/C06 — merge nutricional e recusas de rotulagem

O painel já envia nutrientes parciais, mas `_apply_nutrition` começava com dict vazio. A testemunha confirmou perda de campos não enviados (ou erro por sumir a porção obrigatória); `{nutrition_facts: {}}` removia tabela/proveniência inteira. Seis casos de forma inválida em alérgenos/dieta também escapavam como `AttributeError_` do registro, em vez de `CatalogError`; não foram classificados como aceites válidos de dados errados.

O merge agora parte do valor fresco e só marca override manual se um nutriente realmente mudou. Patch vazio mantém o dado derivado. Listas exigem lista de strings antes do registro; opções continuam validadas por `attributes`, cuja recusa é traduzida para o erro contratual. Não inventamos rótulo, nutriente, fonte ou enumeração.

**Prova:** 8 falhas anteriores; **94 testes PostgreSQL passaram** após a correção, incluindo API de catálogo, gates fiscal/nutricional e preservação integral de nome quando campo posterior é inválido. Ruff/diff-check passaram. Sem DDL/reconciliação; rollback reverte parser/merge e conserva dados, mas reabre a perda conhecida. Valores reais e aceite de rotulagem continuam sujeitos à fonte e G05; ensaio exclusivamente sintético.


### WP02/WP05 — edição parcial de produto vinculada à intenção

Base anterior: `b774f5ee2`. A transação/merge frescos já existiam e foram preservados. A API ainda aceitava PATCH sem base ou recibo; uma edição do mesmo campo sobrescrevia a leitura de outra pessoa sem conferência (evidência de sequência no writer anterior, sem alegação de incidência). Agora o GET oferece Action canônica com revisões das folhas editáveis; PATCH vincula pessoa, produto, conteúdo e chave. A validação compara apenas as folhas alteradas sob lock de Product. O recibo usa a transação existente de remote_mutations; GET de resultado é leitura local. Replay não reaplica a edição e pode apresentar o produto já atualizado posteriormente.

A interface mantém rascunho e mostra valores atuais dos campos em disputa, exigindo escolha explícita para manter ou descartar. Manter apenas atualiza a base da intenção, sem salvar automaticamente; descarte é explícito. Fechar o painel com alterações pede descarte e conserva a digitação se a pessoa continuar. O transporte compartilhado conserva o método PATCH na intenção e reconhece o código de conflito na resposta de catálogo.

Validação efetiva: 97 testes PostgreSQL de API/preservação; mais 3 PostgreSQL de concorrência com conexões independentes e rollback por falha no recibo; 255 testes Orders/Vitest; typecheck. A primeira rodada de concorrência teve 1 sucesso e 2 falhas de preparação por registro de atributos vazio após flush; a fixture passou a criar as definições canônicas a cada teste. O primeiro teste de transporte esperava boolean em executePath, que retorna recibo; corrigida a expectativa, sem alterar contrato. A primeira fixture do painel omitia listas obrigatórias; corrigida para representar a projeção. Logs anexos registram a preparação PostgreSQL e os resultados finais.

Esforço demonstrado localmente: resposta perdida de PATCH usa GET automático (zero nova gravação ou redigitação); conflito conserva os valores, acrescentando escolha explícita e Salvar. Não há prova de ganho de campo nem orçamento p95 deste painel. Migração: sem schema novo; backend e frontend precisam coexistir na versão do contrato, pois cliente antigo recebe 400 antes de escrever. Rollback: reverter a fatia de código em conjunto; conservar produtos/recibos, sem apagar chaves ou reexecutar mutações antigas. Piloto/rollout continuam pendentes dos gates aplicáveis. Restam outras ações de catálogo no inventário de C02/C03.
