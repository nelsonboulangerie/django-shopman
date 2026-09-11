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


### WP06/WP07 — primeira leitura indisponível e retomada do SSE

Base `d7d0e8432`: teste de ciclo de vida reproduziu 0 conexões SSE após GET inicial 503 seguido de recuperação (1 falha/21 sucessos). O watcher `once` se encerrava na primeira transição, mesmo não estando pronto. Agora encerra somente após pending=false/error ausente, ou desmontagem. Polling canônico permanece. O primeiro ensaio após correção revelou ausência do auto-import ssePath no harness; injetada a implementação real, sem mudança de runtime para acomodar o teste. Resultado: 257 testes Orders passaram. Feeds já mantinha leitura e editor durante GET503: teste novo protege comportamento existente, sem reimplementar. Sem migração de dados; rollback de código desta fatia. Ainda não comprova o budget p95 de retomada em dispositivo de piloto.


### WP05/C06 — entrada numérica sem truncamento ou valores não finitos

Base `a4361379e`. Teste anterior: 8 falhas/9 sucessos. Preço inteiro aceitava True e truncava 12.5; infinity levantava OverflowError não traduzido. Nutrição aceitava booleanos, truncava porção fracionária e valores não finitos escapavam da recusa tipada. NaN em inteiro já era recusado e virou regressão. O parser de inteiro do facade agora segue o dialeto estrito já existente da entrada (int/string inteira; bool/float não são inteiros); nutrição usa a dataclass canônica para escolher inteiro/decimal e exige número finito. Não muda regra nutricional, origem dos fatos ou aprovação de rótulo.

Validação: 106 testes PostgreSQL API/catálogo/preservação passaram. A primeira execução pós-edição falhou na coleta por import com indentação incorreta; corrigido antes da rodada válida e Ruff. As recusas mantêm nome, preço e dados nutricionais/proveniência anteriores. Sem migração; rollback de código, sem transformação de valores comerciais. G05 de rotulagem continua pendente; nenhum dado real editado.


### WP06/WP07 — leitura e resultado confirmado do catálogo

Base `39d6b7e21`: matriz não conservava explicitamente a última leitura e rotinas incluíam refresh no try da gravação; no lote de preços, um GET falho após recibo aplicado devolvia null. Agora atualização de leitura é separada do resultado da gravação, com mensagem persistente, última matriz preservada e bloqueio de nova escrita em erro. Vazio de primeira leitura falha não sugere cadastrar produtos. Refreshes usam coalescer existente, fallback 30s e retorno de aba/rede. Troca deliberada de coleção descarta o fallback anterior; não há persistência nova.

Validação efetiva: 259 testes Orders/Vitest e typecheck passaram. Testemunhas verificam recibo de preço aplicado seguido de GET503 continua retornando contagem confirmada, e falha de GET conserva matriz/recusa célula e lote com zero POST. Migração/rollback de código apenas; não exige modificar produtos, flags ou recibos. Cadência de 30s é configuração local, não prova do budget de 35s ponta a ponta nem benefício medido em campo.


### WP02/WP05/WP06 — curadoria de ordem com conjunto/revisão/recibo

Base `3f4f2a1a8`: seis testemunhas reproduziram listas parciais, duplicadas ou com referências desconhecidas aceitas por reordenação de coleções e produtos. Agora o facade exige exatamente o conjunto completo, lê ordem e pertença sob lock de Collection/CollectionItem e recusa revisão antiga. Inativas ficam fora do escopo de coleções ativas; smart continua sem ordem manual. Não há tabela de ordem paralela. A API oferece Actions canônicas e vincula pessoa/recurso/revisão/lista à intenção; consulta por GET e replay não reordenam novamente.

A UI captura conjunto e Action no início do pointer-down. Atualização durante o gesto não substitui a base; o servidor decide o conflito. Proposta permanece na sessão quando não confirmada, com comparação da ordem atual, verificação somente GET, aceite explícito para reaplicar à base atual ou descarte do rascunho. Sair com ordenação pendente exige decisão explícita e não promete desfazer gravação. A mesma intenção desconhecida permanece no transporte, inclusive se o rascunho for descartado.

Validação efetiva: 95 testes PostgreSQL de API/conjunto; mais 9 testes de conjunto/replay/pertença/concorrência (6 se sobrepõem à primeira bateria); 262 testes Orders/Vitest e typecheck. Dois escritores PostgreSQL na mesma base terminam em aplicado/conflito. Replay antigo não desfaz ordem gravada depois. Teste de ponteiro real no DOM sintético demonstra que leitura posterior não altera os membros/posição do gesto original. A fixture antiga de falha de reorder precisou passar Action e 400 tipado para chegar à recusa pretendida; ausência de Action passou a impedir envio.

Esforço local: um arraste continua sendo uma ação quando confirmado; resposta perdida consulta recibo automaticamente, sem repetir a mudança. Conflito mantém sequência e pede decisão adicional explícita. Sem medição de ganho em campo. Migração: publicar contrato de API/UI em conjunto; clientes antigos recebem 400 antes de escrever. Sem schema novo. Rollback do código preservando Collection, CollectionItem e chaves; não reexecutar arrastes anteriores. G05/G06/G08 aplicáveis ao piloto e persistência permanecem pendentes.


### Ensaio integrado em `a8ffef754`: 12 jornadas reais no laboratório

Build Nuxt/Nitro atualizado e Daphne reiniciado a partir do worktree, com confirmação de PID, comando e cwd antes de parar somente o servidor próprio em 8014. Novos recursos sintéticos por seed; PostgreSQL/Redis dedicados. A primeira rodada teve 10 sucessos e 1 falha: a asserção do avanço verificava a contagem de GET do recibo antes de sua conclusão, pois o SSE já mostrava preparing. O comando retornou 200 e o pedido estava preparing; substituída a asserção síncrona por espera explícita da consulta exigida, mantendo exatamente 1 POST/1 GET. O teste não foi marcado como aprovado na primeira rodada.

Nova rodada com seed novo e sem retries: **12 passaram em 23,8 s**. Mantém as nove jornadas anteriores e acrescenta PATCH de produto com resposta perdida (1 PATCH, 1 GET, fechamento após recibo), disputa no mesmo campo (valor atual exibido, rascunho mantido, botão desabilitado até escolha explícita, nenhuma gravação ao escolher manter), e arraste real de curadoria com resposta perdida (1 POST, 1 GET e ordem canônica exata). Os nove testes anteriores incluem nota/SSE, bloqueio e troca de pessoa, cancelamento, COD, feed, preço exato, produto A/B e GET indisponível. Ruff integral passou após ordenar um import novo do seed.

Limites: Chromium desktop, uma sessão de execução, sem worker/provedor real, sem ensaio de dinheiro/equipamento físico e sem participante de piloto. Duração da suíte não é p95 de interação. Build usa preset node-server para o laboratório e não foi implantado. Os novos testes e seed integram o repositório; não há autorização implícita de piloto/rollout.


### WP02/WP05/WP06 — célula de catálogo: merge e intenção por campo

Base `a0dbc7814`. Primeiro ensaio de concorrência passou sem garantir sobreposição das leituras; não prova ausência do defeito. A barreira foi movida para a entrada de save, e então a pausa restaurou preço 600 após o writer de preço gravar 777. O facade agora relê sob Channel → Product → Listing → ListingItem e escreve apenas os campos do patch, preservando save/history/signals canônicos. Para display, a verificação do recorte bloqueia Collection antes de Product, em ordem compatível com a prévia; continua usando Channel.config.display, sem Listing/preço novo. A participação atual é conferida por product_queryset, como a matriz, quando há revisão do Gestor.

Cada célula oferece Action com revisões independentes por campo e destino/tier. API exige ator/base/chave e usa o recibo transacional existente; erro de mesmo campo devolve 409, campos em disputa e valores atuais. Retorno perdido consulta GET com referência opaca do par SKU/superfície. Replay não reverte alteração posterior. O editor de preço guarda a Action observada, conserva digitação, compara preço atual e exige conferir/manter antes de salvar após conflito. Cancelar/fechar preço modificado exige descarte explícito; ações da célula respeitam enabled. Preço/publicação em display são recusados integralmente.

Validação: merge inicial 90 testes PostgreSQL; depois 93 testes de API/concorrência/recibo passaram (são rodadas sobrepostas, não somáveis), incluindo preço e pausa independentes, mesmo preço 409, replay e falha de gravação do recibo com rollback do preço. 263 testes Orders/Vitest e typecheck passaram. A primeira bateria do contrato teve 1 falha/89 sucessos porque o teste de chaves exatas ainda não incluía Action; o contrato fixado foi atualizado explicitamente. A matriz gera tokens dos objetos já carregados, sem acrescentar consulta por célula.

Migração: API/UI do contrato juntas; cliente antigo recebe 400 antes de escrever. Sem schema novo e sem alteração de dados reais. Rollback reverte código desta fatia mantendo preços, pausas, histórico e recibos; não apagar chaves para retentar. Esforço local: resposta perdida exige zero nova digitação; disputa de preço preserva valor e acrescenta conferência explícita. Navegador integrado desta fatia ainda não executado; o último integrado é `a8ffef754`. G05/G06/G08 de campo/persistência permanecem pendentes.


### Nova suíte ampla SQLite em fonte imutável `a0dbc7814`

Worktree `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-orders-validation-current-20260910`, branch `codex/orders-validation-current-20260910`, sem modificações durante a execução. Comando: runner isolado com DATABASE_URL/REDIS_URL vazios, `-n 2 shopman`. Resultado: **8623 passed, 3 failed, 64 skipped, 3 warnings, 38 subtests passed**, em 862,40 s. Os skips não validam concorrência PostgreSQL. Não chamar essa rodada de verde nem atribuí-la aos commits de célula posteriores.

As três falhas ocorreram em dois testes de acerto de entregador e um de comentário de estação autônoma; enviavam os payloads antigos sem ator/base/intenção, recebendo 409 antes do comando. Foram adaptados ao helper context_payload já existente, que lê Actions reais do detalhe. Permanecem asserções de troco que saiu/voltou, livros Cashman, equipamento e autor do comentário do totem. Nenhuma permissão ou guarda foi relaxada. Revalidação direcionada em PostgreSQL: **18 testes passaram**, incluindo os módulos completos e as intenções de comentário/equipamento. A suíte ampla não foi novamente executada após essa adaptação; a rodada original e suas falhas permanecem registradas.


### WP02/WP05 — switches globais no writer/recibo de produto

Base de implementação `031aedfce` (triagem de testes em `22aac5fc6`). O caminho de pausa/publicação global ainda salvava Product carregado sem revisão ou recibo. Agora sua Action usa os mesmos tokens por campo do detalhe, calculados dos flags já lidos na matriz; o POST reutiliza o executor transacional do editor e só aceita is_published/is_sellable no patch. GET consulta por SKU/pessoa/intenção. O facade de compatibilidade também delega ao writer parcial fresco. Não há fonte de disponibilidade duplicada: os flags de Product continuam gateando canais e displays, sem mudar flags locais dos ListingItems.

A primeira tentativa de unificação exigia full_clean de rotulagem até para pausar. Uma testemunha com nutrição legada não editada falhou e o gate fiscal passou. Corrigida a regressão antes de concluir a fatia: patches apenas dos dois switches preservam a validação estrita dos flags e os validadores canônicos de save; conteúdo/rotulagem editados continuam passando pelo full_clean. Não foi criada revisão nutricional obrigatória para pausar, nem removido gate fiscal para publicar.

Validação efetiva: rodada final **114 testes PostgreSQL** de API, editor/recibo e preservação; **264 testes Orders/Vitest**, typecheck e Ruff dos arquivos. Rodadas intermediárias 93/92 testes são sobrepostas. Replay depois de reativação via detalhe não volta a pausar; a mesma chave pela rota de detalhe identifica a mesma intenção. Nota de conservação editada independentemente permanece. Campos fora do escopo global e cliente antigo são recusados antes de gravar. Fixture de resposta foi ajustada ao envelope canônico product; alvo inexistente passa a 404 com intenção válida.

Migração: API/UI do contrato em conjunto, sem schema ou transformação de dados; payload global antigo recebe 400. Rollback conjunto desta fatia preserva flags, histórico e chaves. Resultado perdido usa GET com o SKU exato, zero redigitação. Ainda falta revalidar célula/global no navegador integrado; último conjunto integrado segue em `a8ffef754`. Não há medição de benefício em campo nem autorização de piloto/rollout.


### WP05/WP06 — teclado, dimensões de interação e navegador real (11/09)

Evidência anterior: curadoria tinha gesto de ponteiro, mas as setas do handle não persistiam ordem. Ícones de toolbar tinham 36 px; handle 24 px; switch 16×28 px; ações de tabela 28 px e primárias do detalhe cerca de 38 px. O ensaio novo das setas protege a mesma base observada e o mesmo writer do arraste, incluindo limites da lista. Não há nova regra de ordenação.

Implementação: tokens compartilhados `control=44 px` e `action=48 px`, consumidos nos controles revisados do Gestor. Switch mantém trilho visual dentro de alvo maior. Alvos de card/tabela/detalhe, edição de produto/preço, menus, toolbar e coleções ampliados; setas usam intenção e revisão existentes. Na captura de 390 px, a coluna fixa cobria a área de canais e o cabeçalho alargava a página: sticky horizontal ficou restrito a desktop e o cabeçalho passou a quebrar linha. Região da matriz tem nome e foco para navegação horizontal.

Validação: 265 Vitest; typecheck e build reais. Browser→Nitro→Django→PostgreSQL/Redis: **15 passaram em 28,0 s**, incluindo perda de resposta de preço em célula e pausa global (uma escrita + um GET de recibo cada), conflitos de produto, COD, cancelamento, notas/SSE, feed e curadoria. Após o ajuste móvel, ensaio dirigido **1 passou em 3,4 s** (repetido em 3,5 s). Mede bounding boxes ≥44 px nos controles amostrados e ≥48 px na ação primária, duas larguras 1280/390, teclado e alcance real do switch via rolagem. A primeira asserção móvel falhou por usar scrollLeft fixo de 620, que ultrapassava o canal; substituída por scrollIntoView e teste de hit target, sem mudar expectativa de acesso. Logs das falhas preservados. Capturas locais inspecionadas; não são prova de uso de leitor de tela nem de ganho de campo. Outros controles não amostrados ainda precisam da auditoria integral.

Esforço local: J09 mantém um arraste; alternativa de uma seta por posição sem redigitar refs. Recuperação de resposta perdida nas duas novas jornadas de catálogo teve zero nova ativação, um GET automático e zero repetição de POST. Tempo da suíte não representa p95 de interação. Migração: nenhuma. Rollback: reverter este commit de UI/tokens, mantendo backend seguro, recibos e dados; não há efeito operacional a compensar. G06/dispositivos e piloto permanecem pendentes.


### WP06 — saída com rascunho e resposta de outra coleção (11/09)

Antes: duas regressões novas falharam (265 controles passaram): resposta de A aparecia após escolher B e o painel não informava à página que havia edição. Agora a chave de fetch inclui pessoa e coleção, o envelope precisa corresponder ao recorte e resposta de outro recorte não autoriza escrita. Última leitura confirmada só vale dentro do recurso. A navegação de coleções conserva a última lista durante carregamento; linhas de outra coleção não são conservadas como se fossem atuais.

Produto informa dirty ao pai; rota exige descarte explícito e bloqueia saída durante gravação. Preço individual e em lote também participam da guarda; trocar coleção exige resolver edição aberta. beforeunload aciona confirmação nativa para abandonar o documento. Nenhum rascunho foi persistido fora da memória da pessoa nem reenviado automaticamente.

Validação: **267 Vitest**, typecheck e build. Duas jornadas reais dirigidas **2 passaram em 5,5 s**: voltar pela navegação SPA e recusar descarte conserva texto; resposta atrasada de coleção não substitui o recorte escolhido. Primeira rodada expôs seletor desaparecendo enquanto carregava, corrigido. Teste inicial de voltar usou navegação de documento e esperou texto customizado, mas o navegador corretamente mostrou beforeunload sem texto; ajustado para exercitar rota SPA. Segunda rodada esperava response de request que Nuxt já cancelou; corrigido para aguardar finalização da entrega controlada, mantendo a asserção da coleção. Falhas e limites constam dos logs; os logs com nome `final` nesta sequência contêm uma falha, o resultado aprovado é `third`.

Esforço: recusar descarte mantém R=0; não remove confirmação nem salva por conta própria. Troca de operador continua desmontando o workspace anterior. Migração: nenhuma. Rollback: reverter UI isoladamente para versão compatível, preservando guardas backend/recibos; não ativar coorte que perca rascunhos. Persistência além da sessão, protocolo assistivo e medições de campo continuam dependentes dos gates aplicáveis.


### WP02/WP05 — recibo independente da projeção do produto

Prova anterior: a gravação commitava; `_read` falhava após o commit (500) e o GET do recibo repetia a mesma projeção quebrada, tornando o resultado indisponível embora a chave estivesse done. Ensaio PostgreSQL: **1 falhou, 3 passaram**. Correção mínima: GET com chave lê somente o recibo do ator/SKU; GET normal continua projetando produto e Action. Não executa writer, não consulta fornecedor e não depende de o produto ainda existir. O PATCH pode retornar 500 se a projeção pós-commit falhar; o fato aplicado continua verificável pela mesma intenção.

Resultado: **98 PostgreSQL passaram em 23,78 s**, incluindo concorrência de campos, atomicidade do recibo, replay sem sobrescrever edição posterior e indisponibilidade de projeção após commit. Ruff passou. Migração: nenhuma; envelope persistido inalterado. Rollback: código pode ser revertido sem apagar chave, mas não ativar versão que torne recuperação indisponível. G08 mantém retenção/remoção pendentes. Logs desta etapa normalizam apenas whitespace final; conteúdo e resultados preservados.


### WP02/WP05 — publicação/pausa em lote com prévia e recibo

Antes: publicação multicanal já era atômica e validava fiscal (proteções mantidas); a rota ignorava `preview`, aceitava cliente sem intenção e não consultava resultado. **6 regressões novas falharam** nesse contrato. Não recriado writer: seleção/locks de preço foram extraídos para um helper comum, e a aplicação chama `bulk_set` existente, com destinos congelados na prévia. Feed permanece Channel/display; só pausa dos SKUs pertencentes ao recorte, sem novo preço/Listing.

Prévia informa cada célula/faixa antes/depois e cada ausência de destino com motivo, sem gravação. Revisão inclui seleção, política, atores e contexto dos gates existentes. POST exige base, ator e chave; recibo e lote compartilham transação. Alteração de membership recusa tudo; canal criado após a validação não entra silenciosamente no lote. Mesmo protocolo de transporte do preço, com escopo distinto. UI conserva seleção/prévia após falha e exige confirmação explícita; atualizar prévia é leitura e não confirma. O texto descreve habilitação na célula, sem afirmar disponibilidade global ou envio externo. Synchronização segue a fila canônica e seus badges.

Ensaios: **114 PostgreSQL passaram em 33,95 s** (superfície, publicação, preço e schema), **268 Vitest**, typecheck, build e Ruff. Browser integral isolado: **18 passaram em 32,0 s**, incluindo nova jornada em que prévia deixa flags intactas, confirmação com resposta cortada depois do commit produz uma escrita e um GET de recibo e limpa somente a seleção confirmada. Concorrência usa conexões distintas; duas intenções na mesma base resultam 200/409. Replay não desfaz reativação posterior; falha no segundo enqueue reverte flags, Directive sintética e chave. Outra pessoa não lê recibo nem aplica a prévia. Teste de feed omite SKU fora do recorte e prova contagem de ListingItem inalterada.

Falhas de preparação/checagem preservadas: fixture nova de display omitiu `name` (1 falha/11 controles passaram; corrigida e incluída nos 114); typecheck identificou que skipped como dict genérico não garantia surface_ref (agora dataclass exportada); Ruff exigiu organizar imports. Os testes antigos de superfície passaram a pedir prévia/revisão antes de mutar, conservando as assertions de fiscal e resultado; um teste dedicado continua provando recusa do cliente antigo.

Esforço sintético: selecionar escopo/produtos, escolher operação e confirmar a prévia; resposta perdida não adiciona gesto nem redigitação. O limite de 100 células/faixas já existente é exibido e aplicado, sem mudar o budget por conveniência. Migração: nenhum model/campo/tabela nova; leitores recebem campos aditivos de preview e mutações antigas incompatíveis são recusadas. Rollback: manter recibos e dados, suspender mutação incompatível antes de retornar UI; nunca reaplicar pausa/publicação antiga para compensar. Restauração do estado anterior exigiria nova decisão sobre valores atuais. G05/G06/G07/G08 e ganho operacional continuam pendentes.


### WP02/WP05 — reenvio com referência de tarefa e recibo

Antes: rota aceitava SKU inexistente e declarava ok; não havia leitura de intenção, revisão de destino nem proteção contra replay após a tarefa deixar queued/running. **4 regressões falharam**. Mantida a deduplicação madura de `catalog.project_sku`: o helper passa a devolver a Directive criada/adotada, travando a tarefa viva durante a decisão local. Não criado novo worker, tabela ou estado de sincronização.

Action da linha contém os destinos ativos/configurados observados; API compara revisão de SKU/identidade/destinos, exige ator e chave e grava recibo + enqueue + estado pending na mesma transação. Resultado lista as tarefas reais, nunca diz enviado. GET do recibo independe da projeção. Repetir uma nova intenção enquanto a tarefa está viva adota a tarefa canônica; repetir a mesma intenção depois de done devolve recibo e não cria novo envio. Alterar destino com a mesma chave é conflito. UI usa intenção por SKU/destino e desabilita reenvio sem Action elegível.

Validação: **123 PostgreSQL** (API, quatro cenários novos, sync-state e projeção Meta), mais **6 testes dirigidos** incluindo adoção de tarefas vivas e divergência de payload (os quatro iniciais se sobrepõem); **269 Vitest**, typecheck e Ruff. Falha no segundo enqueue deixa zero trabalho parcial e zero recibo. Teste UI de resposta perdida confirma POST + GET com mesma chave/ref e zero segundo POST. Não foi executado provedor nem homologado reenvio externo; navegador integral desta capacidade ainda pendente. O script inicial de edição parou numa assertion de trecho frontend divergente após alterar backend; concluído pelo conteúdo real e validado, sem misturar execução de ambiente externo.

Migração: nenhuma, IDs/campos/tópico/dedupe canônicos preservados; cliente sem revisão/intenção recebe atualização obrigatória. Rollback mantém Directive, CatalogSyncState e recibos, suspendendo mutação se o cliente anterior for incompatível. G03 continua necessário para qualquer ensaio externo, G07 para ambiente real. Resultado local aplicado significa decisão de enfileirar registrada, não confirmação de recebimento no fornecedor.


### WP02/WP05 — writer social convergente

Antes: rota social fazia read/merge/save de metadata sem trava/revisão, paralela ao editor de produto. **3 regressões novas falharam**: cliente antigo escrevia, Action ausente e nenhum recibo comum. A rota agora é subconjunto explícito do mesmo writer de produto, com Action POST, patch social, revisão por campo, ator e recibo no mesmo escopo do detalhe. GET social mantém o payload social e adiciona Action; POST antigo sem contrato é recusado. Helpers duplicados de merge/serialização da rota foram eliminados; validadores de `ProductSocialAttributes` continuam sendo os existentes.

O helper frontend social delega ao editor parcial com base da leitura já observada. Não busca revisão nova antes de gravar para fazer uma alteração antiga parecer atual. O painel atual já usava o detalhe, então não foi criada superfície paralela.

Preservação de escopo: a primeira unificação exigia `full_clean` da nutrição intocada ao editar somente marca, comportamento que o writer social antigo não exigia. Um teste reprovou essa regressão (1 falha/3 controles). Agora edição exclusivamente social conserva seu validador canônico + fiscal do save, tal como switches globais; patch de outros conteúdos conserva a validação integral existente. A nutrição legada não é corrigida/normalizada nesta ação. GTIN inválido continua recusado.

Validação: **119 PostgreSQL em 26,34 s** (social, produto, superfície e preservação), **269 Vitest**, typecheck e Ruff. Escritas por rotas distintas em campos sociais independentes coexistem em conexões PostgreSQL diferentes; replay social depois de mudança no detalhe não restaura marca antiga. Mesma chave é consultável pela rota de produto. Migração: nenhuma; cabeçalho/corpo novos exigidos na rota antiga, sem remover a rota. Rollback preserva metadata/recibos e só admite cliente seguro; sem reconciliação real. G05/G08 continuam pendentes para políticas e retenção, e testes locais não aprovam conteúdo fiscal/nutricional em campo.


### WP02/WP05 — revisão inclui origem canônica dos campos

Hipótese revalidada: tokens olhavam apenas valor. Duas provas mudaram origem mantendo valores iguais (nutrição derivada→manual e alérgeno recipe→manual enquanto dieta continuava recipe); ambas aceitaram patch antigo indevidamente (**2 falhas/4 controles**). A leitura agora inclui origem por campo, derivada do registro `attributes.source` e do sentinel nutricional existente. Revisão desses campos inclui a origem; não nasce novo armazenamento de proveniência, regra de derivação ou superfície de promessa. Campos independentes sem essa origem mantêm seus tokens.

Conflito mostra valor e mudança de origem (ficha técnica→edição manual), preserva draft e aguarda revisão explícita. A origem é somente leitura e fica fora do tipo de patch. Não é uma decisão de publicar, congelar receita, revisar rótulo nem alterar limiar de aprovação; esses comportamentos continuam nos writers e gates existentes.

Validação: **117 PostgreSQL em 27,29 s**, **270 Vitest**, typecheck e Ruff. As duas mudanças de origem passam a 409 sem sobrescrever o servidor; o teste UI mostra origem mesmo com valor igual e não emite save. Corrigido também whitespace final no arquivo de API da etapa anterior. Migração: nenhuma; campo aditivo de leitura. Rollback preserva fontes canônicas e recibos; não ativar escrita com revisão antiga se perder a proteção exigida. Esta prova cobre mudança de origem, não certifica todos os atributos possíveis de revisão/homologação da ficha; a superfície de promessa existente continua sendo a consulta completa desses fatos.


### WP02/WP04 — intenção de despacho e recibo independente da leitura

Antes: a rota de despacho aceitava POST sem revisão/intenção e não fornecia Action; três novas provas falharam. A rota agora usa o protocolo local existente, devolve ID/status da Directive canônica e não chama o fornecedor. O writer manual bloqueia e relê Order, compara destino/cliente/pagamento/corrida e estado observados, preserva o enfileiramento e a proteção de unknown já existentes. Projeção reaproveita a capability de courier e calcula o bloco uma vez. Resposta perdida consulta recibo automaticamente; mensagem distingue solicitação enfileirada de corrida aceita.

O GET de recibo comum das ações locais deixa de depender da leitura/projeção do pedido. Autenticação, permissão e escopo pessoa/operação/recurso continuam exigidos; somente o recibo é retornado. A leitura seguinte permanece um GET separado do detalhe. Isso permite verificar efeito confirmado mesmo se a projeção falhar.

Validação: **65 PostgreSQL em 13,55 s**, **271 Vitest**, typecheck e Ruff. Testes cobrem destino alterado→409 sem tarefa, POST repetido→mesma tarefa, GET com projeção indisponível→applied e UI com resposta perdida→consulta sem segundo POST. Primeira rodada após implementação: 42 passaram/1 falhou porque o teste sem ator esperava 400 embora o guard canônico devolva 409; ajustado para isolar ausência da intenção mantendo ator válido. Dois testes antigos de despacho passaram a fornecer o contrato. Primeira asserção UI confundiu GET implícito com método explícito; corrigida sem alteração de transporte.

Migração: nenhuma; Action e recibo aditivos, comando sem contrato recusado. Rollback deve preservar Directives/recibos e suspender a escrita se o cliente antigo não respeitar intenção/revisão. G03 continua pendente para qualquer execução externa; nenhum worker ou adapter real foi acionado. Cancelamento e cotação externos ainda precisam de sua própria verificação, e o GET dedicado de avanço ainda possui implementação separada.


### WP02/WP04 — tentativa durável de cancelamento da corrida

Antes: cancel_ride chamava a central inline e tratava CourierError desconhecido como recusa; a prova de enfileiramento sem rede falhou. Agora o comando bloqueia/relê Order, compara revisão e registra somente solicitação para a corrida observada. Novo tópico courier.cancel utiliza a mesma Directive, dispatcher, dedupe vivo, backoff e erros existentes; schema documentado antes da escrita. A API exige intenção/ator/base, retorna tarefa/queued e oferece GET de recibo. Nenhuma transição comercial ou regra de motivo foi substituída; reason_id deixa de truncar/coagir entradas inválidas.

Worker grava started antes da rede e accepted antes de aplicar C pelo funil existente (que arquiva a corrida). started/unknown impedem outro POST, inclusive em nova intenção após task failed; accepted só recupera adoção local. Corrida substituta não recebe fato antigo. Ordem de locks: Order → Directive; rede fora da transação. Recusa definitiva fica not_applied e visível pelo last_error da própria Directive no painel; unknown usa alerta integration_failed já existente, sem novo tipo/modelo/política de audiência. O painel informa solicitação pendente e desabilita outro cancelamento. Confirmação em dois cliques foi preservada; mudança da Action reinicia a conferência.

Validação final: **69 PostgreSQL em 10,44 s**, **272 Vitest**, typecheck e Ruff. Inclui dispatcher registrado, duas conexões/workers→um POST, timeout/replay→um POST, aceite seguido de falha local→adoção sem POST, troca de corrida antes e durante rede, recusa definitiva, interrupção SystemExit após started, API/recibo e confirmação UI. SystemExit é injeção de interrupção, não comprovação de queda de processo/host. Sem adapter ou dado real.

Preparação: a primeira asserção de C esperava status corrente, mas o funil maduro arquiva C (4 passaram/1 falhou); corrigida para consultar o histórico sem alterar a regra. O primeiro ensaio concorrente falhou porque o callback automático consumia a tarefa antes das barreiras; callback suspenso somente na fixture, depois ensaio repetido com controle explícito. A rodada intermediária 58 não comprova a janela concorrente; evidência aprovada está em courier-cancel-all-approved.txt. Logs das falhas preservados.

Migração: nenhuma tabela/coluna; coordenar versão que reconhece courier.cancel antes de habilitar o comando. Rollback suspende novos cancelamentos e conserva tarefas/recibos started/unknown/accepted; não apagar nem reenfileirar desconhecido com worker antigo. G03 permanece pendente: aprovar procedimento, responsável e consulta homologada da corrida na central; sem isso, unknown mantém bloqueio. G07 continua necessário para qualquer ambiente real. Custo local: confirmação mantém dois cliques; resposta perdida usa GET sem nova solicitação nem redigitação. Nenhum ganho de campo ou piloto aprovado é inferido.


### WP02/WP04 — cotação preserva o destino observado

Prova anterior: o adaptador devolveu valor após outro writer trocar a latitude; store=True gravou cotação do destino antigo sobre o novo. O teste falhou. A gravação agora compara revisão sob lock fresco e recusa a adoção com 409/OrderStateConflict. Campos independentes continuam preservados pelo merge existente. O guard de cotação que já orientava o painel foi centralizado e também rege a API.

A rota de cotação recebe Action/ator/base/intenção. Preparação consulta fora da transação e não grava Order; execução local guarda somente o valor canônico e o recibo no mesmo commit. Replay não consulta fornecedor, mesmo após a revisão mudar pelo próprio save. O uso interno store=True no despacho também recebe a proteção de destino; nenhuma tarifa comercial foi alterada.

Validação: **72 PostgreSQL em 9,71 s**, **272 Vitest**, typecheck e Ruff. Inclui mudança durante consulta, recusa sem estimate, leitura do fornecedor fora de atomic, replay sem segunda consulta e recibo com valor confirmado. Migração: nenhuma; cliente antigo da rota deve atualizar contrato. Rollback preserva valores/recibos e exige suspender a escrita se perder a comparação da base. Cache de cotação e TTL existentes não foram redesenhados; este ensaio cobre mudança do pedido, não homologação de preço/distância ou mudança de origem da loja. G03/G07 seguem pendentes para fornecedor/ambiente real.


### WP07 — catálogo/feeds recebem invalidação SSE sem perder rascunhos

Antes: catálogo/feeds só consultavam por polling/visibilidade; alterações de conteúdo de Product não invalidavam uma leitura privada do Gestor. As provas de permissão para o novo canal e de atualização por metadata falharam; controle de rollback passou. Foi estendido o transporte SSE existente com backstage-catalog-main, mesma permissão shop.manage_catalog das duas APIs, payload vazio de invalidação, publicação após commit. Signals de Product/Listing/ListingItem/Collection/CollectionItem/Channel/CatalogSyncState e notificação de bulk/ordenação cobrem os writers exercitados. Não há segunda projeção/cache ou nova autorização. Canais públicos existentes mantêm seus eventos.

O ciclo de SSE já usado pelo detalhe foi extraído para useBackstageEvents e compartilhado com catálogo/feeds; filtro por pedido foi preservado no wrapper. Reconexão, polling 30 s, visibility e online usam o refresh coalescido existente. A fila conserva seu transporte próprio. O push só refaz GET canônico; não substitui draft, altera seleção nem salva automaticamente.

Validação: **58 PostgreSQL em 9,39 s**, **273 Vitest**, typecheck/Ruff/build. Rajada de 30 eventos→1 leitura ativa +1 pendente; desconexão mantém polling; desmontagem fecha stream. Permissão correta, rollback sem evento, metadata e seis famílias de recursos, bulk de coleções e sincronização exercitados. Navegador Chromium → Nitro → Django/Daphne → Redis/PG locais: **20 jornadas passaram em 45,9 s**; novas jornadas de catálogo/feed comprovam push recebido, valor digitado/seleção preservados. Duas repetições dirigidas passaram em 5,8 s e 4,8 s, esta última conferindo foco preservado em ambos os editores.

Medição de uma amostra por jornada: comando→conteúdo visível **150 ms catálogo, 94 ms feed**, sem clique de atualizar/R=0; dados em catalog-sse-latency.json. Havia suíte ampla concorrente no host. Essas duas amostras não constituem p95, hardware de operador homologado ou ganho de campo. Não confundir tempo total da suíte com tempo ativo humano.

Migração: nenhuma; novo endpoint SSE apenas de leitura, cliente tolera queda e continua polling. Rollback do consumidor volta ao polling; servidor conserva APIs/fontes/recibos e pode manter canal aditivo. Redis multiprocesso foi exercitado localmente; G06 para budgets/dispositivos e G07 para ambiente real continuam pendentes. Escritores fora das famílias/rotas inventariadas ainda exigem sua prova própria; SSE não é recibo de comando nem prova de publicação externa.


### Validação ampla imutável em 3504dec71 e fixture de calendário

Checkout somente de validação django-shopman-orders-validation-3504dec71, branch codex/orders-validation-3504dec71; mesmo runner, SQLite isolado, pytest -n 2 shopman: **8.676 passaram, 1 falhou, 68 skipped, 3 warnings, 38 subtests em 523,02 s**. Essa rodada continua registrada como falha; não inclui o commit posterior de SSE d7af378b9.

Única falha: test_data_ilegivel_cai_no_padrao_em_vez_de_estourar calculava hoje pelo relógio, mas fixava date_to em 2026-09-10. Em 11/09, o writer canônico troca intervalo invertido, portanto date_from passa a 10/09. Teste e serviço estavam idênticos à base 5a3383c9 (git diff vazio); defeito da fixture com passagem do dia, não regressão de produção. O próprio parse_period já oferece parâmetro today: a fixture agora usa data controlada 07/09 por essa costura existente. Algoritmo não mudou.

Revalidação do módulo inteiro: **38 PostgreSQL em 8,39 s e 38 SQLite em 7,62 s**. Skips/warnings da ampla permanecem no log; não equivalem a ensaios feitos. Migração/rollback: nenhuma mudança produtiva, somente teste determinístico. Suite ampla verde em versão final ainda depende de nova rodada fixa após as demais mudanças.


### WP07 — hora da leitura útil separada da conexão

Antes: as quatro leituras principais não expunham geração/versão do envelope (4 provas falharam). Fila, detalhe, catálogo e feeds agora retornam generated_at pelo servidor e contract_version=1; a Action continua sendo a precondição autoritativa. Campos seguem a nomenclatura já usada pelas projeções de produção, sem transplantar suas provas/permissões. Nenhum TTL novo de comando ou estado paralelo.

A interface conserva somente metadata de leitura bem-sucedida junto do recurso. Falha mantém horário anterior; troca de recorte limpa a marca; servidor sem metadata mostra horário indisponível. Componente comum às quatro páginas exibe última leitura útil/idade e falha separadas da conexão SSE. Usa o timer monotônico já existente; não anuncia cada segundo ao leitor de tela, não decide elegibilidade e não altera som.

Validação: **124 PostgreSQL em 27,32 s**, **277 Vitest**, typecheck/Ruff/build. Inclui geração pelo relógio do servidor, falha sem avanço da marca, troca de recurso, convivência com envelope antigo e relógio local ±5 minutos. Quatro jornadas Chromium/Nitro/Daphne passaram em **7,6 s**, mantendo horário na falha em cada página. Primeira tentativa de navegador: 1 passou/3 falharam; seletor da fila omitia o atalho do nome acessível, e duas leituras válidas on-open ainda estavam em voo quando o teste capturou horário. Corrigida preparação para aguardar falha visível e verificar que a próxima falha conserva a última marca útil. Logs iniciais preservados, sem alteração de código produtivo para atender ao erro da fixture.

Migração: nenhuma; metadata aditiva, leitores antigos ignoram, novo leitor tolera ausência. Rollback retira indicação sem mudar Actions/recibos. A idade é da geração da leitura, não prova de consistência transacional de todo o snapshot nem de efeito remoto. G06 ainda requer aparelhos/rede e budgets homologados; não constitui piloto.

### WP07 — HTTP, BFF e renderização ricos em 8a016ae2e

Ensaio sequencial completo em PostgreSQL/Redis exclusivos, Daphne/Nitro locais,
Chromium desktop: 1/10/100/500 pedidos, três itens fracionários, seis eventos,
pagamento capturado e Hold planejado por pedido. HTTP direto e BFF: fila e
pedido, 20 amostras por concorrência 1/2/10, mais primeira requisição. Navegador:
20 páginas por carga (80 ao todo), quatro execuções Playwright aprovadas.
Login excluído desta cronometragem técnica; não pode ser excluído de E integral.

Evidências reproduzíveis: `orders-20260910/http_read_lab/README.md` e
`results/summary.md`, com distribuições JSON completas, hardware, CPU/RSS,
payload e queries. Cabeçalhos de laboratório incluem autenticação/serialização;
BFF não os repassa. CPU de janela concorrente não é CPU exclusiva por request.
Primeira requisição não implica banco/processo/OS totalmente frio.

**Budget não atingido:** 500 pedidos/10 clientes: backend fila p95 3180,3 ms
(meta 500 ms); renderização/filtragem autenticada p95 2473 ms (meta 1500 ms).
Fila 500 com um/dois clientes: backend p95 434,5/478,0 ms. Navegador 1/10/100:
p95 509/318/715 ms. Sem alteração silenciosa de meta e sem conclusão WP07/T.
A funcionalidade dos 80 percursos passou; desempenho da carga maior exige
investigação/otimização e reensaio. G06 continua pendente, não autoriza relaxar
R=0/P0 ou anunciar ganho em campo.

Falhas de preparação registradas no README: runtimes ausentes (Daphne maduro
adotado), requisitos Doorman em DEBUG=False, seletor textbox incorreto,
conexões esgotadas ao herdar age=60 sem pool (guia existente prescreve age=0),
e duas limpezas recusadas pela proteção/imutabilidade do livro Payman. A fixture
final **conserva transações**, não contorna o domínio. Após as cargas, consulta
agregada pg_stat_activity não encontrou conexões residuais nos bancos orders.
Nenhum processo de terceiro, banco real, segredo ou chamada externa utilizado.

Migração: nenhuma. Rollback deste pacote de ensaio: parar servidores próprios;
artefatos não entram na aplicação. Não remover livros/chaves reais nem usar o
runner fora das portas/base sintéticas fixas. Implementação técnica/piloto/
rollout continuam distintos: aqui há medição local, não homologação operacional.

### WP02 — consulta de avanço independente e nova intenção após recusa comprovada

Revalidação em 2ddf9a933: GET do recibo de avanço ainda construía a projeção; uma
indisponibilidade da leitura escondia um commit confirmado. O hook de intenções
conservava também a chave quando a consulta retornava o recibo not_applied em
HTTP 409, impedindo enviar o rascunho novo após revisão. Antes: uma regressão
PostgreSQL e três casos UI falharam; doze controles UI passaram.

Implementação: GET de avanço usa apenas o recibo existente no escopo autorizado
por pessoa/recurso, como os demais comandos. O cliente libera a intenção quando
o GET comprova not_applied em 400/409/422, preservando o erro e exigindo novo gesto.
Falha de GET sem prova, 401/403, intention_conflict e desafio de assinatura não
liberam a chave. Nenhum autoenvio, texto reconstituído ou efeito adicional.

Resultado: 31 PostgreSQL passaram (11,19 s), 285 testes Orders passaram, typecheck
Orders e Ruff dos arquivos alterados passaram. Logs antes/depois em
`orders-20260910/{advance-receipt-before,receipt-refusal-before,receipt-recovery-*}.txt`.
J04 mantém consulta automática; nova revisão após recusa não exige redigitar.
Sem medição de esforço em campo e sem nova política de retenção.

Migração: nenhuma. Rollback: conservar o formato/chaves do recibo; cliente
anterior pode ficar preso na recusa e backend anterior pode depender da projeção.
Não apagar intenção para resolver unknown. G01/G03/G05/G08 permanecem pendentes.

### WP06 — retorno à fila com contexto por pessoa

Antes em f30d61d6d: query/channel/fulfillment/seleção eram refs da página;
sort/view eram cookies compartilhados pelo navegador, apesar do comentário
“por operador”; voltar do detalhe apontava apenas para `/`. Código revalidado,
não inferência de que o shell já preservava tudo. O shell maduro continua
preservando a página na reidentificação da mesma pessoa.

Implementação: recorte validado na URL, seleção/posição/foco em useState da sessão
atual e vinculados à pessoa. Voltar explícito usa a URL do recorte; histórico do
browser também retoma. Pessoa diferente descarta contexto e rejeita a URL com
identificação anterior. Não se implementou persistência de draft após reload,
TTL ou retenção sem G05/G08. Tokens/cookies de autenticação não entram no estado.
Os cookies antigos de modo/ordenação deixam de ser usados; não se migra uma
preferência compartilhada como se tivesse dono conhecido.

Teste real: 500 pedidos, filtrar, trocar para tabela, selecionar uma linha longe
do topo, abrir detalhe, voltar por link e pelo histórico. Ambos passaram
(14,1 s), com busca/modo/seleção/foco e scroll restaurados. A primeira tentativa
falhou por medir a seção interna: o shell efetivamente rola a janela. Correção
passou a preservar essa posição também; nenhum budget reescrito para ocultar.

288 testes Orders passaram; typecheck e build passaram. A primeira suíte UI
teve 31 falhas de preparação do mock de auto-import do novo composable; fixture
atualizada, lógica real testada separadamente para mesma/diferente pessoa e URL
inválida. Evidências `orders-20260910/board-context-*.txt`; jornada browser
reproduzível em `tests/performance/context.spec.ts` com a fixture HTTP 500.
J12/volta ao contexto: R=0 no caminho ensaiado; teste local não mede T humano nem
aprova todos os cenários C07. Diálogos/rascunhos ainda têm trabalho independente.

Migração: nenhuma no banco. Rollback UI exige manter estado/chaves em voo e
versão compatível; voltar ao código antigo perde este contexto na navegação.
Nenhuma ampliação de permissão, confirmação eliminada ou efeito externo.

### WP06/WP03 — valores físicos preservados ao interromper acerto/saída

Revalidação em eeeaddb6c: openSettle/openDispatch e openDialog zeravam os valores
em cada abertura. Fechar e reabrir exigia redigitação; reabrir também atualizava a
base da custódia sem comparação. Agora acerto/saída compartilham draft da sessão
por pessoa/pedido entre fila e detalhe. Inicializam só ao abrir pela primeira vez;
SSE e reabertura não sobrescrevem valor, equipamentos ou custódia observada.
Confirmação conhecida limpa o draft correspondente. Nova pessoa descarta todos.

A confirmação física e a comparação de turno continuam obrigatórias. O guard de
reload/saída da sessão pede confirmação nativa quando há draft efetivamente
alterado ou intenção pendente; abrir sem editar/restaurar o valor inicial não
cria confirmação redundante. Isso protege saída, não promete persistência após
reload aceito. Sem localStorage, credencial, cartão ou nova fonte financeira.

292 testes Orders passaram, incluindo fechar/reabrir com turno mudado, campos
independentes por pedido, troca/expiração de pessoa e distinção dirty/vazio.
Typecheck e build passaram. Primeira UI: 290 passaram, um teste usou rótulo
inexistente (“Acertar dinheiro” vs “Acerto dinheiro”); fixture corrigida.

**25 jornadas completas browser→Nitro→Django→PostgreSQL→SSE passaram (45,5 s)**
com seed fresco e adaptadores isolados. Incluem os 24 cenários anteriores e o
novo acerto: digitar 14,50, fechar/reabrir, navegar à fila, abrir no card, recusar
reload; valor preservado e zero POST de acerto. A jornada seguinte confirma
acerto sintético com resposta perdida e consulta um único recibo. Não há worker
externo nesta suíte nem dinheiro físico, ganho em campo ou homologação.

Evidências `orders-20260910/cash-drafts-*.txt`. O README do laboratório explicita
DATABASE_CONN_MAX_AGE=0 para seu PostgreSQL direto, conforme guia existente.
Migração: nenhuma. Rollback: preservar intenção e backend seguro; UI antiga
perde os drafts ao fechar. G02 decide custódia real; G05/G08 continuam pendentes
para persistência/retenção. Preparação técnica não autoriza piloto nem rollout.

### WP07 — custo por leitura reduzido, sem mudar contrato ou esconder o budget

Perfil aquecido em 4b265ca86 mostrou 1.000 resoluções do catálogo de textos e
63.413 visitas do serializador na fila rica de 500 pedidos. O JSON primitivo
passava por testes de dataclass/Enum/Mapping/Sequence desnecessários. Teste
anterior: rótulo repetido 20 vezes falhou no budget de uma resolução por chave;
um controle de Enum/Decimal/data passou.

Mudança mínima: fast path apenas para **tipos exatos** JSON primitivos (subclasses
como StrEnum/IntEnum continuam convertidas), e rótulos resolvidos uma vez por
chave dentro de cada projeção. Não há cache entre requests, nova regra de copy
ou campo omitido. A versão de leitura reutiliza API_VERSION já existente.

Comparação com relógio fixado: JSON completo antes/depois idêntico byte a byte
(1.798.532 bytes com espaçamento de json.dumps do ensaio). Perfil diagnóstico:
2.234.534→934.753 chamadas, serialização 214→56 ms; perfis não são p95 e foram
usados para localizar custo. 137 testes PostgreSQL + 13 subtests passaram,
incluindo produção/freshness para proteger o serializador compartilhado; Ruff
passou. Reprodutor e evidências em `orders-20260910/read_work/`.

Reensaio HTTP de 500 pedidos, 20 amostras por endpoint/concorrência: fila backend
p95 229,7/377,4/1599,1 ms (1/2/10 clientes). Antes: 434,5/478,0/3180,3 ms.
BFF p95 266,1/433,5/1903,5 ms. A melhora local **não satisfaz 500 ms com dez
clientes** nem substitui reensaio de renderização/dispositivo/rede piloto.
WP07/T não encerrados; G06 permanece pendente. Não se aumentou a meta.

Migração: nenhuma. Rollback retorna apenas resolução/serialização anterior,
sem tocar livros/recibos. Nenhum dado, ação, permissão ou confirmação retirado.

### WP07 — hipótese de renderização refutada no ensaio

Após otimizar backend, 20 páginas com build 4b265ca86: navegador p50 2131,5 ms,
p95 2473 ms. Experimento apenas no harness (CSS injetado antes do documento,
`content-visibility:auto`/tamanho intrínseco por article): 20 páginas p50 2895 ms,
p95 3179 ms. Ambos funcionais passaram; a hipótese de melhora foi refutada neste
ambiente. **Nenhum CSS dessa alternativa foi incluído na aplicação.** O patch do
experimento e as distribuições foram preservados em `read_work/` para reprodução;
o harness padrão voltou ao conteúdo anterior.

Referência técnica consultada: [MDN content-visibility](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/content-visibility).
A propriedade auto permite adiar layout/pintura mantendo foco e acesso ao
conteúdo; também exige cuidado com descendentes intencionalmente ocultos. Essa
possibilidade não substitui medir o aplicativo nem comprova acessibilidade por
leitor de tela. Aqui não houve ganho, portanto não se adotou a alternativa.

G06 continua sem aprovação; 500/dez clientes e renderização de 500 não atendem
aos budgets propostos. Evidência não autoriza diminuir a meta, restringir coorte
por conta própria ou declarar WP07/T concluído. Pacotes técnicos independentes
continuam; não há autorização de piloto/rollout.

### WP08 — correlação de requisição e recibo (preparação técnica parcial)

Antes em 4cf8aa3bb, operational_event/JsonLogFormatter eram maduros, mas os novos
comandos/recibos não os correlacionavam. Reutilizados: contexto local à execução,
request_id próprio, operação finita pelo tipo da view, pessoa **após** permissão,
ref do recurso, digests de chave/base, código/outcome e refs de Directive quando
presentes. O header X-Request-ID identifica a resposta Django. Não logar nota,
cliente, endereço, telefone, PIN, payload integral ou chave opaca literal.

operator.command.local_result só é emitido em on_commit, inclusive diante de
outer atomic. Receipt/replay fica separado de execução; falha da projeção após
commit produz recibo aplicado e transporte desconhecido correlacionados. GET e
recusa de permissão não produzem gravação atribuída a ator autorizado. ContextVar
é limpo no finally e testado com duas threads. Tempo view_elapsed_ms inclui a
view, não equivale ao HTTP completo/serialização final; o laboratório HTTP
continua sendo a prova separada desses budgets.

51 testes PostgreSQL passaram; ampliação por famílias (catálogo, feed, publicação,
resync, courier e observabilidade): **138 passaram (34,83 s)**. Primeiro ensaio:
47 passaram/4 falharam porque o logger shopman não propaga ao root capturado pelo
pytest. Fixture passou a escutar o logger existente diretamente; produção não
teve sua configuração alterada para acomodar o teste. Testes incluem ausência
literal de segredos sintéticos nos JSON, rollback externo sem falso commit,
permissão, replay e falha de resposta depois da gravação. Ruff passou.

Evidências `orders-20260910/observation-*.txt`. Usar o JsonLogFormatter existente
(SHOPMAN_JSON_LOGS) no ambiente homologado; não se ativou Sentry nem exportação
externa. Retenção/acesso aos logs continuam dependentes de G08/G07.
Migração: nenhuma. Rollback preserva todos os recibos; perde apenas essa
correlação adicional. Não criar tabela de auditoria paralela. WP08 permanece
parcial: efeitos externos, placar e runbooks ainda exigem complemento; WP07 e
os gates de piloto não foram encerrados por estes testes.

### WP08 — evidência de tentativa courier e custódia confirmada

As máquinas de estado courier já tinham recibos duráveis started/accepted/unknown,
mas sem evento estruturado por mudança. Agora publicam metadados após commit:
Directive/tópico, pedido, tentativa do worker (não contagem inventada de POST),
identificador remoto conhecido, início/registro e classificação. Unknown registra
“aceite não comprovado”, sem copiar erro livre do fornecedor. O evento started
é comprovadamente emitido antes do fake de rede, fora do lock.

O acerto registra após commit a ligação entre request/intenção, Entry real criada
pelo writer canônico, Shift, PaymentIntent e recebedor. Replay não produz segundo
evento de acerto nem outro lançamento. O novo helper de on_commit reutiliza
operational_event e captura metadados; nenhuma nova fila/tabela/regra.

60 testes PostgreSQL passaram (13,30 s), cobrindo logs, rollback, courier
concorrente/timeout/aceite, acerto e recibo. Evidência:
`orders-20260910/observation-effects-postgresql.txt`. Tokens e detalhes privados
sintéticos não aparecem nos eventos de tentativa. Migração: nenhuma. Rollback
conserva recibos e livros; remove apenas metadados adicionais dos logs.
WP08 continua parcial (notificações/fiscal/placar/runbooks), sem homologação
externa nem definição unilateral de SLA G03 ou custódia real G02.

### WP04/H01 — notificação: resposta perdida e fence antes do transporte

- Evidência anterior no HEAD daa08a6b7: 2 falhas/1 controle aprovado (`notification_unknown/notification-unknown-before.txt`). Adaptador simulado aceitava e perdia resposta; a cadeia enviava pelo segundo canal. SystemExit(17) depois do aceite deixava a Directive sem marcador. Este ensaio é injeção de SystemExit, não morte de processo pelo SO.
- Implementação: NotificationResult conserva classificação de incerteza; exceção de transporte não autoriza fallback. O worker lê Order→Directive com locks, grava started e libera transação antes do transporte. Segundo worker/replay started/unknown não envia. Aceite persistido é monotônico. Recusa comprovada continua permitindo fallback/retry; tentativa histórica sem prova não é declarada falha segura. Nova ação de reenvio também recusa histórico unknown/started ou failed sem prova not_applied. Projection do link explica a pendência no pedido.
- Adaptadores existentes: WhatsApp/Manychat/SMS/email não convertem erro de transporte em False; notify classifica como unknown sem copiar exceção/contato. HTTP sem prova de rejeição é conservadoramente unknown (inclui 4xx; sem homologação G03 não deduzimos ausência de efeito). APIs preservam bool de sucesso; Manychat não fabrica ID a partir de subscriber_id; email só aceita count=1. Não houve chamada a fornecedor real. Consentimento, canais e destinatários existentes preservados.
- Testes: família PostgreSQL 218 aprovados/11,54s; após fence de nova chave histórica e ajuste da ordem dos guardas, 50 aprovados/10,18s. Concorrência usa duas conexões independentes, uma fake externa bloqueada e uma segunda execução recusada; um efeito, aceite final preservado, transporte fora de atomic. Família inicial 82 aprovados. Preparação: teste Manychat usou chave API_TOKEN em vez de api_token (6 aprovados/1 falha); corrigida a fixture. Dois mocks antigos de serviço não escreviam evidência, corrigidos para representar recusa explícita; teste separado protege tentativa antiga sem prova. Logs de falha preservados, não contados como verdes. Ruff dos arquivos alterados e diff --check aprovados.
- Observabilidade: estados started/accepted/unknown geram operator.effect.state após commit, ligados à Directive/resource; sem destinatário/erro do provider. Incerteza devolvida gera OperatorAlert existente sem dizer falsamente “5 tentativas”. Crash/replay sem retorno continua visível como started na Directive; runbook/placar integrado ainda pendente WP08.
- Migração: sem DDL; schema JSON documentado antes das escritas novas. Não reclassificar nem reconciliar dados reais automaticamente. Rollback: manter banco/chaves, impedir que worker antigo consuma Directives started/unknown; drenar/parar consumidor antigo é pré-requisito de ativação, ainda não ensaiado WP09. Reverter código sozinho não é rollback operacional seguro desse fence.
- Limites: adapters bool ainda não entregam todos os IDs reais ao recibo; API auxiliar Manychat fora de notification.send e notificações de sistema não receberam protocolo durável de pedido. Consulta homologada/reconciliação externa e SLA continuam G03. WP04 não é declarado integralmente concluído por este incremento.

### WP09 — suíte ampla fixa e E2E de backend simulado

- Snapshot imutável d5ba08477: **8.699 passed, 68 skipped, 3 warnings, 38 subtests, 486,03s**, SQLite, xdist 2. Worktree de validação limpo após execução. Evidência `orders-20260910/broad-d5ba08477.txt`. Warnings são três testes de deploy que substituem DATABASES. A execução não pediu -rs; inventário nominal dos skips ainda deve ser extraído/reexecutado. Não representa PostgreSQL nem os commits posteriores daa08a6b7 e fence de notificação.
- Playwright padrão completo: **4 passed/17,6s**, Chromium, backend simulado 8796, Nitro 3004, build incluído. Evidência `orders-20260910/default-e2e.txt`. É complementar aos 25 cenários integrados reais já registrados; não substitui worker/PostgreSQL/SSE integral.
- G06 apresentado novamente: 500 pedidos/10 clientes backend p95 1.599ms e tela p95 2.473ms continuam acima dos budgets. Solicitados dispositivo/rede/personas/volume de aceite; pergunta pendente não muda os limites e não bloqueia ensaios independentes.

### WP09 — restore populado e consumidor anterior

Ensaio reproduzível e evidências em `orders-20260910/restore_lab/README.md`. PostgreSQL
local isolado: 140 tabelas/129 sequências preservadas byte a byte por manifesto de
linhas e valores de sequência; 44 pedidos, 43 Directives, 157 chaves, 7 lançamentos
de caixa, 7 intents/7 transações Payman, 2 movimentos fracionários Stockman. Primeira
cópia tinha estoque vazio; repetida em novo destino com entradas/saídas pelo writer
canônico. Nenhum banco de terceiros substituído, nenhum ledger apagado.
Código anterior 5a3383c9 lê os novos campos, porém tenta reenviar unknown no fake;
atual e5fae331e bloqueia. Probes revertidos, manifestos ainda idênticos. Isso reprova
convivência irrestrita/rollback ingênuo de workers, não bloqueia leitura. Ativação e
rollback exigem parar/drenar consumidores antigos e preservar as Directives/chaves;
verificação em ambiente autorizado continua pendente G03/G07. Sem DDL novo. O ensaio
não mede RTO de produção nem cobre ainda browser antigo/todos os tópicos externos.

### WP09 — segunda suíte ampla fixa, skips nominais e correções de contrato de teste

Snapshot e5fae331e (worktree separado, nenhuma edição durante a execução): **8.709
passed, 2 failed, 68 skipped, 3 warnings, 38 subtests; 503,89s**, SQLite/xdist2.
Log completo com -rs em `orders-20260910/broad-e5fae331e.txt`. Falhas: fake_send_mail
em test_notification_placeholders não devolvia o inteiro contratado; e dois
excepts classificados como unknown não emitiam log exigido pelo gate existente.
Fixture agora devolve 1; ambos logam aviso fixo sem conteúdo da exceção. Acrescentadas
provas count=0 não aceito/count=1 aceito. **23 testes PostgreSQL aprovados/6,42s**
(unknown, placeholders e higiene de exceções). A suíte ampla anterior permanece
registrada como falha, não se transforma em verde por esta execução direcionada.
Skips nominais: grafos complexos ausentes na smoke de Admin, dez testes de webhook
Manychat pendentes preexistentes, um dígito fiscal de fixture, e testes que exigem
locks/conexões PostgreSQL. O log lista módulos/linhas/motivos; ensaios PostgreSQL
direcionados registrados anteriormente cobrem os locks alterados, não equivalem a
executar todos os skips históricos de domínios fora do escopo.
