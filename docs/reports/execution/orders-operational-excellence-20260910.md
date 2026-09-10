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
