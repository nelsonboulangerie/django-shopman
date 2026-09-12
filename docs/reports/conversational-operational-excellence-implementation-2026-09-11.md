# Evidências da implementação conversacional — 11/09/2026

**Estado atual: implementação técnica v3 testada em ambiente isolado no SHA `e87b9c4de04db9b48e3f02b0bf1ac6345a70c2fc`; homologação, piloto e rollout não executados.** As seções anteriores ao adendo v3 preservam a evidência histórica do candidato v2 e os SHAs que nomeiam. O adendo ao final é a conclusão vigente. O aceite integral continua limitado pelos gates e provas humanas/fornecedor. Nenhuma contagem de testes comprova redução de esforço humano ou entrega no WhatsApp.

## Proveniência e isolamento

Base: `1138c95eee0862630330328cf3bfe2f0b6424796`. Worktree exclusivo: `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-conversational-implementation-20260911`. O checkout original e alterações de terceiros foram preservados. Ao fechamento, HEAD do checkout original permaneceu `b589e22`, com seus arquivos untracked preservados; `origin/main` local continuou `1138c95` (sem fetch). Agentes trabalham com propriedade explícita de arquivos no mesmo worktree: runtime/modelos/transporte (integrador), tools (autoridade comercial), ingresso/Guestman e evidências/fulfillment (H12). Não há merges concorrentes nem troca de branch no principal.

Runtime: Python da `.venv` original, com todos os imports de `packages/` reposicionados pelo runner `evidence/conversational/run.py`. Configuração `config.settings_test` remove credenciais externas e fixa gateways de teste. PostgreSQL privado `localhost:56419`, usuário sintético `concierge_test`; Redis privado `localhost:56420`. Evidências usam banco `concierge_evidence`/`test_concierge_evidence` e Redis DB9, separados das demais suites dos agentes. SQLite não é prova de locks.

SHA final de código e testes validado: **`97aaad216f409486c58a65ec8b88207fafbab685`**. Branch `codex/conversational-excellence-implementation-20260911`. Relatório/evidências são versionados separadamente desse commit. Este é candidato técnico, não release implantada. Nenhum ambiente externo, conta, contato real ou gateway foi utilizado. A aprovação desta implementação não autoriza migrar banco real.

## Registro executável e limitações

Os arquivos `.txt` em `evidence/conversational/` são saídas de comandos; não são ledgers do produto. Os diagnósticos do apêndice foram reproduzidos antes das alterações: **13/13 defeitos observados**, `baseline.txt`, 14,42s. O arquivo `diagnostics-baseline.py.txt` preserva o diagnóstico como documento e não é coletado como teste. Não integra o gate verde.

| Artefato | Comando/escopo | Resultado observado |
|---|---|---|
| `final-integration.txt` | seleção em `final-selection.json`, PG `concierge_final`, Redis DB12, `--reuse-db`; SHA 97aaad216 | **400 passed, 42,67s; zero skips, zero warnings** |
| `integration-ff1c9bee3.txt` | checkpoint ff1c9bee, PG `concierge_final`, Redis DB12, `--reuse-db` | 378 passed, 30,91s; zero skips, zero warnings |
| `core-commit-final.txt` | core `test_commit_branches`, processo separado | **9 passed, 11,37s** |
| `cart-consumers.txt` | consumidores da projection de sacola | **5 passed, 14,01s** |
| `make-admin.txt` | `make admin` integral após alterações do Admin | **264 passed, 64,44s; Admin canônico aprovado** |
| `schema-check.txt` | Django check e `makemigrations --check --dry-run`, DB sintético migrado | sem problemas de schema / sem mudanças detectadas |
| `baseline.txt` | runner + diagnósticos do apêndice na base, SQLite | 13 passed exigindo defeitos; somente baseline |
| `mature-postgresql.txt` | runner + 10 módulos maduros do segundo lote do plano, PG/Redis | 102 passed, 19,23s, zero skips; warning de teardown por conexões de threads; processo encerrou |
| `h12-before.txt` | `test_concierge_runtime_fulfillment.py` inicial, PG | 3 failed: órfão após criação; update sem sync; criação concorrente duplicada |
| `h12-after.txt` | ensaio intermediário H12 | 6 passed no primeiro ensaio; ampliação revelou erro do teste (`event_type` em vez de `type`), corrigido no teste |
| `h12-mature-after.txt` | 6 regressões H12 + consumers fulfillment/stock/KDS/fiscal/courier | 99 passed, 13,35s; zero skips |
| `ingress-tests.txt` | C01 + sync Guestman, comando em `INGRESS.md` | 78 passed, 12,39s; zero skips |
| `capabilities-tests.txt` | núcleo em ManyChat fake e adapter opaco + ingresso | 41 passed, 17,24s; zero skips |
| `runtime-final.txt` | 6 módulos runtime: Admin, turnos/ingresso/coorte, migração/contenção, H12, vertical e carga | 30 passed, 15,19s; zero skips |
| `runtime-load.txt` | 100 conversas, 10 mil mensagens, 109 entradas, burst 10, 4 workers PG | 1 passed, 2,05s; 100 respostas aceitas pelo fake, 109 inputs consumidos, zero Orders |
| `runtime-vertical.txt`, `runtime-vertical-final.txt` | J01/J07 real core + H06 inventário + H09 timeout; ampliação D12 segundo item | final 3 passed, 2,61s; um Order/PaymentIntent, unknown sem replay; falha no segundo SKU conserva holds/contexto |
| `browser-contained.txt`, `browser-return.txt` | Chromium148, gate desligado/ligado local e dois perfis | 4 combinações aprovadas; zero erros de console; imagens inspecionadas |
| `backup-restore.txt` | `backup_rehearsal.py`, pg_dump/pg_restore em dois bancos privados sintéticos | um Order/receipt/Message unknown preservados; sem worker/envio |
| `cohort-before.txt` | revogação de coorte após aceitação | 1 failed antes; `_claim`/tool/saída agora revalidam allowlist; regressão incluída em `runtime-final.txt` |

Invocação reproduzível dos ensaios PG deste relatório (substituir somente a seleção de testes):

```bash
DATABASE_URL=postgres://concierge_test@localhost:56419/concierge_evidence REDIS_URL=redis://localhost:56420/9 PYTHONDONTWRITEBYTECODE=1 /Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python evidence/conversational/run.py shopman/storefront/tests/test_concierge_runtime_fulfillment.py -rs --reuse-db
```

`--reuse-db` usa somente o banco sintético dedicado. Serviços privados devem estar disponíveis; não trocar a URL por um banco compartilhado para fazer a suite passar. Não somar reruns para inflar cobertura.

## Propriedade dos fatos e dependências reais

| Fato | Writer/fonte preservado | Consumidor conversacional |
|---|---|---|
| Entrada, consumo, posse, revisão oferecida, saída | Conversation / ConversationMessage | ingress/service/agent/tools/recuperação |
| Trabalho durável | Directive + dispatcher Orderman | handler concierge; sem fila nova |
| Sacola/revisão/quantidade/preço | Session + services cart/modify/catalog | ferramentas validadas; servidor determina fatos |
| Pedido/efeito local/recibo | CommitService + remote_mutations / IdempotencyKey | replay autorizado antes de exigir sacola aberta |
| Estoque/hold | Stockman + integração existente | nenhuma reserva paralela |
| Identidade | Guestman + Doorman | contato de transporte não vira credencial universal |
| Pagamento | Payman + serviços de pagamento | consulta/Action; pedido não implica captura |
| Fulfillment | serviço e handlers Shopman | H12 corrigido no owner compartilhado |
| Fases/KDS/fiscal/courier | lifecycle e handlers existentes | nenhuma execução duplicada pelo concierge |
| Continuidade de acesso | Session / AccessLink / Storefront | alvo autorizado e contexto preservado |
| Consentimento e avisos | stock_alerts / marketing safety / notificações | prova por finalidade; nenhuma fonte nova |

M01–M09 têm preservação por suites selecionadas, não certificação de todo o monorepo. M02–M06/M09: suite madura PG de 102 testes. M08: stock/KDS/fiscal/courier no lote complementar. M01/M07: ingresso, capabilities, runtime e Admin adaptados à autoridade nova; o checkpoint integrado de 378 testes preserva a referência inicial para os consumidores selecionados. Core 9 e Admin 264 têm processos próprios; as contagens intermediárias se sobrepõem e não devem ser somadas.

## Matriz D/H/G

D01–D13 foram reproduzidos no SHA base pelo apêndice. D14–D17 permanecem fatos de inspeção nessa base até regressão nova individual. A tabela não remove achados por mera edição de código.

| Achado | WP / contrato | Critério de retirada |
|---|---|---|
| D01 entrada durante turno | WP02/C02 | consumo explícito preserva entrada tardia; barreira PG |
| D02 aceitação sem trabalho recuperável | WP01/C01 | rollback conjunto e replay repara; concorrência |
| D03 saída false consumida | WP03/C03 | persistência antes da rede; certeza estruturada; unknown sem retry |
| D04 compra sem confirmação | WP04/C04 | revisão oferecida + inbound posterior; chamada direta recusada |
| D05 recibo perdido | WP04/C04 | retry retorna pedido original autorizado; um Order |
| D06 input inválido altera entrega | WP04/C04 | todos os campos e reservas intactos no erro |
| D07 quantidade inválida removida/truncada | WP04/C04 | parser canônico e decimal preservado; negativo/bool recusados |
| D08 retorno humano sem sincronizar | WP07/C07 | falha/unknown mantém contenção local |
| D09 switch ignorado pelo worker | WP07/C07 | execução/tool/saída bloqueadas após revogação |
| D10 projeção quebrada vira vazio | WP06/C06 | unavailable com alvo preservado |
| D11 ID por minuto/truncado | WP01/C01 | ID íntegro/escopado; conflito; sem ID não muta |
| D12 transferência parcial destrói origem | WP05/C05 | falha em cada item/mint preserva origem ou desativa operação por G05 |
| D13 fato inventado encaminhado | WP04/C08 | renderer determinístico inclusive preâmbulo/tool injection |
| D14 backlog para após limite | WP02/C02 | continuação durável e recuperação órfã |
| D15 link escolhe último pedido | WP05/C05 | alvo explícito/desambiguação e Action autorizada |
| D16 aviso sem prova verified | WP08/C08 | disclosure/aceite canônicos ou capacidade contida |
| D17 contexto/CTA truncados | WP02/03/C02/C03 | refs canônicas e blocos essenciais preservados |

| Hipótese | Estado / ensaio | Owner / dependência |
|---|---|---|
| H01 efeito remoto+timeout | fake registra efeito e lança timeout; unknown sem retry comprovado em runtime/vertical; capacidade real não homologada | integração/G02 |
| H02 workers/lease/posse/tools concorrentes | double claim, lease vencido, handoff durante modelo, entrada tardia e coorte removida comprovados em PG; tools têm corrida de confirmação dedicada | runtime + tools/WP02/04/07 |
| H03 preço/frete/política mudam na revisão | revisão rejeita catálogo alterado; fee completo verificado no review/Order/PaymentIntent; não muda regra comercial | tools/WP04; G05 política |
| H04 getInfo no ACK | stub proíbe rede no ACK; demonstrado em C01; latência humana/fornecedor desconhecida | ingresso/WP01 |
| H05 identidade entre contas/canais | conta/provider/canal conferidos; IDs colidentes e adapter opaco testados; legado não promovido | ingresso/WP08; G04 |
| H06 ruído lifecycle+resposta | vertical produz um `order_received` e um `preorder_reminder`, ambos do mesmo Order; resposta à intenção é do concierge. Ruído e ordem remota ainda não medidos | runtime/tools/WP03/06 |
| H07 sync Guestman | nonce de assinante e parser booleano corrigidos após reprodução; falha/replay/tipos testados; contrato real pendente | ingresso/WP01/08; G02 |
| H08 reservas/cart web | transferência com estoque exato e retry conserva quantidades/fulfillment; subcaso posterior transfer/site-edit reproduziu hold órfão e foi corrigido no writer canônico da sacola com Session lock e transação; política de conflito comercial continua G05 | tools/WP05; G05 |
| H09 status com timeout vencido | fixture worker parado + confirmation.timeout vencida; consulta reconcilia e projeta cancelled, sem domínio mock. Subcaso callback/cancel posterior confirmado e corrigido: refetch canônico evita deixar pagamento recebido sem estorno após cancelamento | tools/WP06 |
| H10 esforço/perguntas repetidas | **não medido**; corpus e observação pendentes | Produto/UX/G06 |
| H11 defaults delivery pós-compra | Order.data, CustomerAddress e CheckoutDefaults de entrega verificados no teste canônico | tools/WP04/05 |
| H12 fulfillment parcial | **confirmado e corrigido em PG**: 3 falhas antes; 6 regressões depois cobrem criação, falha no sync/agendamento e concorrência. 99 testes com consumidores verdes | evidências/WP06/09 |

G01–G07 continuam **pendentes de decisão nominal por ambiente e etapa**. G01 coorte/conta/finalidade; G02 contrato ManyChat/evento/ACK/janela/receipt; G03 autoridade/horário/SLA humano; G04 privacidade/identidade/retenção; G05 transferência/conflitos/preço; G06 budgets/amostra/carga/custo; G07 release/alvo/backup/rollback/janela. Sem gate, a capacidade dependente fica fechada. Nenhum gate é substituído por mock ou comentário no código.

## Work packages — estado de aceite

Ordem: WP00 → WP01 → WP02 → WP03/WP04 → WP05/WP06/WP07/WP08 → WP09 → WP10. Preparação independente em paralelo não certifica dependência ainda não testada.

| WP | Entrega/evidência do candidato | Estado de encerramento |
|---|---|---|
| WP00 | SHA, isolamento, baseline D e madura PG, mapa de owners, matriz e jornadas | documentação técnica; baseline humana G06 pendente |
| WP01 | ingresso/envelope/atomicidade/replay; C01 e Guestman 78 testes | mecanismos locais testados; contrato externo G02 pendente |
| WP02 | consumo/claim/fence/continuação/órfãos; PG com conexões independentes e burst após 5 loops | implementação local testada; suíte integrada final verde |
| WP03 | prepared antes da rede, accepted/unknown/not_applied, limite/janela e replay | fakes testados; fornecedor G02 pendente; nenhum aceite equivale a entrega |
| WP04 | autoridade/revisão/recibo/renderer; concorrência confirmação, fee e callbacks fora do lock | tools e consumidores testados em PG; suíte integrada final verde |
| WP05 | transferência atômica/estoque exato/recibo replay/link e preservação de origem; alvo explícito | fatias locais testadas; política/ativação G05 pendentes |
| WP06 | projeção/Actions + H12 no owner compartilhado; vertical real Order/Payman | regressões locais e consumers verdes; H06/clareza remota limitadas abaixo |
| WP07 | revogação/posse/retorno, Admin permissões e evidência legível, recuperação sync interrompido | PG e browser testados; autoridade operacional G03 pendente |
| WP08 | escopo/capabilities/consentimento; núcleo em dois adapters fake, 41 testes | testes locais; identidade G04 e canais reais novos desativados |
| WP09 | PG/Redis + regressões + carga/vertical + browser Admin | prova técnica parcial: não mede J01–J13 com pessoas nem WhatsApp/webview reais; G02/G06 pendentes |
| WP10 | MigrationExecutor 0047→0049 com legado, containment/recovery mantendo receipts/Order, tópico v2; pg_dump/restore sintético verificado | ensaios sintéticos aprovados; flow nativo/backup real/ambiente de release dependem G02/G07 |

Implementação testada, homologação controlada, piloto e rollout são etapas distintas. WP11/WP12 não foram iniciados. A suite integrada final está verde no SHA acima (400 passed); os critérios humanos e de fornecedor não são declarados concluídos. As linhas com limites não equivalem ao aceite integral dos WPs ou à conclusão operacional: as medições/gates explicitamente pendentes continuam pendentes.

## Jornadas antes/depois e esforço

O “antes” é comportamento reproduzido ou estrutural, não média de campo. O “depois” é resultado técnico a verificar na fixture. A/U/R/M/X/T/W e compreensão final **não foram medidos com pessoas**. Os budgets completos seguem na seção 6 do plano; não foram reduzidos.

| Jornada | Antes | Depois esperado / prova a associar |
|---|---|---|
| J01 compra simples | compra possível sem inbound de confirmação (D04) | revisão completa e um aceite posterior; 1 Order/receipt |
| J02 o de sempre | fração truncada, defaults dependem do fluxo | rascunho mantém decimal, diferenças antes do aceite |
| J03 mudar horário | erro já alterava entrega (D06) | validação não grava; endereço conhecido preservado |
| J04 retomar | janela textual perde contexto (D17) | refs de sessão/pedido/revisão; resumo sem autoridade |
| J05 corrigir no turno | correção invisível (D01) | inbound pendente e revisão antiga impedida |
| J06 site/chat concorrentes | H02/H08 sem prova original | conflito explícito/CAS; nenhuma perda silenciosa |
| J07 resposta perdida após compra | retry no_cart (D05) | recibo e pedido exatos, sem novo commit |
| J08 falha Pix/saída | bool ocultava certeza (D03) | Order distinto de pagamento; unknown preservado |
| J09 transferência parcial | origem abandonada incompleta (D12) | origem intacta ou capacidade fechada até G05 |
| J10 humano | remoto falha e local ativa (D08) | bot contido; pedido registrado sem prometer SLA |
| J11 dois pedidos/status | mais recente implícito; indisponível vira vazio | escolha contextual/Action exata; unavailable verdadeiro |
| J12 aviso/opt-out | consentimento verified sem evidência (D16) | inscrição só com prova; opt-out canônico revalidado |
| J13 áudio/janela/capability | fallback textual/truncamento | alternativa clara, sem download/mutação/envio indevido |

Ficha de medição humana a preencher em G06: jornada, SHA antes/depois, fixture, participante pseudônimo autorizado, dispositivo/rede, transcrição redigida, A/U/R/M/X, T ativo e W separado, falhas/assistência, resposta a “Foi feito? Está pago? Qual a próxima ação?”. Sem preenchimento, não publicar mediana/p90 ou percentual de ganho. Acessibilidade: Admin verificado em Chromium desktop 1440 e mobile 390, sem texto cortado/console error. Jornadas do cliente em 320/390px, texto ampliado, leitor de tela, baixa conectividade, retorno do banco e WhatsApp webview/browser permanecem ensaios pendentes.

## Migração, contenção e compatibilidade

Mudanças são expansão de Conversation/Message, mantendo Session/Order/IdempotencyKey/Directive como owners. Dados históricos não adquirem verificação por backfill: ID/conta legado sem prova continuam `legacy_unverified`; bool `delivered` não comprova receipt remoto; transcrição/resumo não fabrica aceite nem inscrição.

Antes de execução real, G07 deve fixar release SHA, alvo, backup testado, inventário, responsável, janela e binário compatível. Gates G02/G04 definem mapper de conta/canal, flow exportado/hash, dados permitidos e compatibilidade. O tópico novo `concierge.turn.v2` usa a MESMA fila Directive; o worker histórico não possui handler para ele e não processa o envelope novo. O novo handler rejeita payload sem `contract_version=2`; entradas legadas não são assumidas como pendências autorizadas. O campo de versão sozinho não cercaria o worker histórico: o roteamento versionado foi necessário. Ainda é preciso conter/parar workers antigos antes de habilitar a coorte, para que não processem diretivas legadas previamente aceitas.

Rollback é contenção: interromper novas intenções automáticas, invalidar claims/fences, bloquear novas saídas não autorizadas; preservar consultas e reconciliação dos efeitos já comprometidos. Inventariar Orders, intents, Messages e Directives por estado; manter receipts/unknown. Não apagar fila/histórico, devolver estoque, estornar pagamento ou reenviar transcrição por rollback de software. Compensação comercial exige serviço canônico e autoridade própria.

Nunca fazer downgrade de schema removendo recibos para “voltar ao normal”. Se binário anterior não entende `unknown`/consumo/versão, manter a capacidade desligada e corrigir adiante. Retomada exige regressão do defeito, reconciliação de pendências, revisão humana e nova autorização de etapa. Flow ManyChat e sandbox real não foram alterados.

## Runbooks para as superfícies existentes

Todo incidente deve registrar objeto exato, último fato confirmado, incerteza, idade, responsável e próxima ação permitida. IDs de correlação são restritos; não colocar telefone, endereço, token de AccessLink, Pix completo, payload ou prompt em labels de métricas/log geral. Não exportar transcrições sem G04. O operador deve resolver a causa antes de encerrar alerta.

| Cenário | Diagnóstico somente leitura | Recuperação permitida | Proibido / encerramento |
|---|---|---|---|
| Entrada aceita sem turno | Message/envelope/consumo + Directive viva/claim; conferir idade e versão | recuperar agendamento original pelo mecanismo existente após fence vencido | não inserir fala duplicada; encerrar quando consumo e próxima ação estiverem documentados |
| Saída unknown | Message lógica/bloco/tentativa e evidência do provider; distinguir accepted de delivered | owner de integração consulta identificador quando G02 comprovar capacidade; atendimento verifica sem retry cego | não converter unknown em sucesso/não aplicado; encerrar apenas com evidência ou pendência atribuída |
| Pedido sem Pix/link | Order/receipt/Payman/Action e resultado do bloco exato | consultar/recuperar intent canônico autorizado; manter mesmo pedido | não repetir commit/cobrança; encerrar após pagamento/pendência e acesso claros |
| Revisão/estoque/transferência conflita | Session/rev/Order/holds e snapshot aceito; origem/destino | mostrar diferença e solicitar escolha faltante, mantendo origem | não corrigir estoque ou abandonar carrinho à força; nova revisão/recibo verifica fechamento |
| Handoff/kill switch | posse/fence/claim + espelho remoto + alertas/contexto | conter localmente, sincronizar com evidência, atendimento aprovado G03; retorno com nova autoridade | não prometer atendente imediato sem SLA; não ativar após False/unknown; fechar só com dono e routing reconciliados |
| Janela/credencial/provider falha | resultado técnico, janela calculada, versão/capabilities; sem expor chave | preservar pendência e canal autorizado; tratar timeout como unknown se efeito possível | não trocar contato/canal nem template arbitrário; encerrar quando caminho permitido estiver disponível |
| Identidade/consentimento conflita | Guestman/Doorman, finalidade/proof e revogação canônicas | bloquear capacidade sensível, preservar draft/navegação e encaminhar validação | não promover confiança por source/transcrição; fechar com evidência de ownership/aceite |
| Rollback/incidente crítico | inventário restrito por coorte/versão/estado e objetos comprometidos | contenção, recuperação canônica, suporte com contexto, binário compatível | não apagar receipts/Orders nem replay em massa; reabertura depende de regressão/reconciliação/G07 |

Escalada: atendimento (G03) para contexto/posse, integração (G02) para certeza remota, responsável de dados (G04) para identidade/consentimento e dono do ambiente (G07) para contenção/release. Pessoas, SLA e janela ainda devem ser nomeados; os budgets propostos no plano não são compromisso operacional aprovado.


## Provas adicionais e limites do aceite

H12 corrigiu o writer compartilhado: `fulfillment.create` bloqueia Order e relê marcador, adota registro existente, grava registro+marcador atomicamente; `FulfillmentUpdateHandler` bloqueia Order→Fulfillment e transaciona estado, sync e agendamento. Os callbacks externos continuam depois do commit. Os testes inspecionam contagem de Fulfillments, transições/eventos, estado de Order e uma Directive de aviso, não só chamadas mock. Pendências legadas já divergentes exigem reconciliação humana: não são reenviadas por backfill.

Carga local: 1801 queries nos 100 turnos, 0,652s de execução em 4 workers, mediana 0,025s / p95 0,033s / máximo 0,036s por turno. Esses valores são do modelo e provider fake; não medem custo/tokens reais, fila do fornecedor, chegada ao aparelho, memória/locks em produção ou percentis sob carga operacional. Nenhum SLO foi certificado.

Vertical J01/J07: primeira entrada monta 2 pães × R$ 0,90 e retirada/slot, apresenta revisão pelo renderer e não cria Order. Novo `confirmo` cria um Order de R$ 1,80 e um PaymentIntent pendente. O fake registra efeito de resposta e perde retorno; Message permanece unknown, e replay do evento consulta a mesma entrada sem novo Order/intent/saída. H06 preserva notificação `order_received` e lembrete de encomenda `preorder_reminder`, um de cada por Order; não desativa avisos maduros indiscriminadamente. A ordem real de mensagens e o esforço/ruído percebido continuam G02/G06.

Browser: `browser_server.py seed` migra somente `concierge_browser`, cria loja/conta sintéticas e perfis `synthetic-admin`/`synthetic-viewer`. `browser_admin.py contained` prova que G03 fechado esconde retorno inclusive de superuser; `BROWSER_RETURN_GATE=true` em servidor local permite testar ação somente para superuser, com adapter inerte sem token retornando não confirmação. O aviso mantém atendimento humano, e o viewer não ganha ação. Campos são readonly e o badge de unknown explica que não se deve reenviar. Screenshots em `admin-*.png`; processos de servidor encerrados após QA. A flag local de teste não altera default de produto ou produção.

Correções do próprio harness registradas: H12 usou inicialmente `OrderEvent.event_type` em vez de `type`; vertical usou `time_slot` em vez do schema `slot_ref`, `converted` em vez de Session `committed` e recibo sem desembrulhar `result`. Foram erros dos ensaios corrigidos antes da aprovação, sem atribuí-los ao produto. O primeiro browser procurava `inner_text` sem considerar uppercase visual do badge; locator textual nativo confirmou o conteúdo e as capturas foram refeitas. O ensaio inicial `observability-tests.txt` falhou ao procurar um evento no logger raiz: o logger operacional canônico não propaga para ele. O teste final liga o capturador ao logger correto e exige IDs internos correlacionáveis e ausência dos canários sensíveis (`observability-consent-tests.txt`, 3 passed). Nenhum desses ajustes relaxou invariante.

Checklist de aceite integral: as permutações PG da tabela 8.2 estão individualizadas na ampliação adversarial abaixo e passaram no lote integrado final; UX com participantes, acessibilidade assistiva e WhatsApp real são pendentes. Export nativo/hash do flow ManyChat e backup/restauração do ambiente de release dependem G02/G07. Não alegar que a fixture JSON de flow é um export homologado, nem que screenshot de Admin prova jornada do cliente.

## Índice de regressões por contrato e achado

Prefixo de todos os arquivos desta tabela: `shopman/storefront/tests/`. Os nomes permitem selecionar regressões isoladas com o runner; as execuções combinadas não devem ser somadas às execuções individuais.

| Contrato / achado | Regressão do comportamento correto |
|---|---|
| C01 / D02 | `test_concierge_runtime_turns.py::test_d02_intake_and_queue_failure_roll_back_together_and_retry_repairs` (falha antes/depois do agendamento) e `test_d02_two_postgres_deliveries_accept_one_event_and_one_work` |
| C01 / D11 | `test_concierge_ingress_contract.py::test_long_event_identity_replay_conflict`, `test_missing_id_or_empty_allowlist_never_admits`, `test_profile_change_conflict_is_auditable_without_new_work` |
| C01 / H04 | `test_concierge_ingress_contract.py::test_rotation_and_no_network_in_ack`; webhook sem getInfo |
| C02 / D01 | `test_concierge_runtime_turns.py::test_new_input_during_model_stays_pending_and_invalidates_mutation`; `test_concierge_delivery_integrity.py::test_late_input_survives_answer_and_note` |
| C02 / D14 | `test_concierge_runtime_turns.py::test_burst_after_five_loops_defers_same_directive_then_finishes`; recuperação após cem conversas ociosas em `test_concierge_runtime_migration.py` |
| C02 / D17 contexto | `test_concierge_delivery_integrity.py::test_history_window_cannot_hide_claimed_input`; carga com 10 mil mensagens em `test_concierge_runtime_load.py` |
| C02 / H02 | `test_concierge_runtime_turns.py::test_two_workers_claim_exactly_one_turn`, `test_expired_lease_new_claim_revokes_old_worker`, `test_handoff_during_model_has_no_bot_reply_or_consumption` |
| C03 / D03, H01 | `test_concierge_delivery_integrity.py::test_prepared_before_remote_effect_and_unknown_never_retried`; `test_concierge_runtime_turns.py::test_provider_effect_timeout_is_unknown_and_same_block_is_not_retried` |
| C03 / D17 saída | `test_concierge_capabilities.py::test_semantic_blocks_preserve_every_character_and_whole_lines`, `test_semantic_blocks_never_cut_oversized_pix_line`; `test_concierge_adversarial_integration.py::test_dependent_payment_block_waits_for_accepted_summary` |
| C04 / D04 | `test_concierge_authority.py::test_d04_review_without_offered_message_and_new_confirmation_cannot_buy`, `test_d04_qualified_or_injected_confirmation_cannot_buy`; vertical não cria Order antes do segundo inbound |
| C04 / D05 | `test_concierge_authority.py::test_d05_receipt_precedes_cart_and_rejects_payload_change`; `test_concierge_runtime_vertical.py::test_j01_j07_real_core_keeps_one_order_after_lost_confirmation_response` |
| C04 / D06 | `test_concierge_authority.py::test_d06_invalid_fulfillment_preserves_all_fields` |
| C04 / D07 | `test_concierge_authority.py::test_d07_invalid_qty_never_changes_cart`, `test_d07_weight_quantity_remains_exact_in_cart_and_review` |
| C04 / D13 | `test_concierge_delivery_integrity.py::test_model_cannot_invent_critical_facts`; vertical injeta preço/afirmação de pago e renderer recusa |
| C04 / H03 | `test_concierge_authority.py::test_h03_review_channel_price_and_concurrent_catalog_change_never_buy`, `test_h03_delivery_fee_is_in_review_order_and_payment_once` |
| C04 / H02 fronteira financeira | `test_concierge_authority.py::test_c04_two_postgres_confirmation_workers_create_one_order_and_receipt`, `test_c04_provider_callback_runs_after_local_receipt_and_outside_transaction` |
| C05 / D12, H08 | `test_concierge_authority.py::test_d12_mint_failure_rolls_back_transfer_and_preserves_slot`, `test_h08_exact_stock_transfer_preserves_all_quantity_and_fulfillment`; `test_concierge_runtime_vertical.py::test_d12_second_item_failure_preserves_source_fulfillment_and_all_holds` |
| C05 / D15 | `test_concierge_authority.py::test_d15_menu_does_not_move_cart`, `test_d15_transfer_retry_returns_same_destination_without_recopied_cart`; AccessLink suite madura |
| C06 / D10 | `test_concierge_authority.py::test_d10_projection_error_preserves_existing_order` |
| C06 / H09 | `test_concierge_runtime_vertical.py::test_h09_status_reconciles_due_confirmation_with_worker_stopped` |
| C06 / H11 | `test_concierge_authority.py::test_h11_delivery_defaults_and_address_are_saved_from_session` (Order, CustomerAddress e CheckoutDefaults canônicos) |
| C06 / H12 | seis regressões de `test_concierge_runtime_fulfillment.py`; efeitos+eventos+avisos verificados após retry e concorrência |
| C07 / D08 | `test_concierge_delivery_integrity.py::test_return_failure_preserves_human_ownership`; browser retorno não confirmado; recovery sync interrompido em `test_concierge_runtime_migration.py` |
| C07 / D09 | `test_concierge_delivery_integrity.py::test_kill_switch_during_model_blocks_output`, `test_kill_switch_during_human_return_never_reactivates_bot`; revogação de coorte em `test_concierge_runtime_turns.py` |
| C08 / D16 | `test_concierge_authority.py::test_d16_disclosure_alone_never_subscribes_and_real_acceptance_links_proof`; suites maduras opt-out/expiração |
| C08 / H05 | `test_concierge_capabilities.py::test_same_subject_in_another_account_has_separate_context`, `test_identity_gate_is_closed_even_when_payload_claims_phone`, `test_account_swapped_reference_cannot_consult_receipt` |
| WP10 | `test_concierge_runtime_migration.py::test_expand_legacy_rows_preserves_evidence_without_inventing_authority`, `test_recovery_during_containment_preserves_receipts_and_does_not_send` |

Os testes H03 com fee verificam total R$ 7,80 no review, Order e PaymentIntent; estoque exato H08 usa 10 unidades disponíveis / 10 na sacola, sem duplicar hold; a transferência e promoção de identidade continuam desligadas por padrão. H09 confirmou que a consulta pode executar reconciliação canônica de timeout: é um efeito existente da fachada do Storefront, documentado, e não uma projeção pura nova.


Ensaio complementar de backup: `backup_rehearsal.py` executou `pg_dump --format=custom --no-owner --no-acl` de `concierge_browser` e `pg_restore --no-owner --no-acl` em `concierge_restore`, banco privado novo. A verificação SQL encontrou exatamente 1 Order sintético, o mesmo receipt e Message unknown / delivered NULL. Hash do dump: `b2724acbe7afa60e4f79f6cf27fb83d45752635e4a6cad50668edcc5b2b1453c`. O archive era temporário e foi descartado; o banco restaurado foi criado somente no serviço local de testes. O script recusa sobrescrever banco destino existente. Nenhum worker/modelo/fornecedor foi acionado; essa prova não certifica o backup de outro ambiente.

### Estado dos defeitos após regressões

D01–D11, D13 e D16 têm regressões locais do comportamento correto no índice acima; D12/D15 têm falha de mint, conservação em estoque exato e replay do destino; D14 tem continuidade durável após 5 loops e recuperação de órfãos; D17 tem janela histórica limitada ao claim, refs canônicas e blocos não truncados. O checkpoint integrado ff1c9bee confirmou 378 casos; a ampliação posterior da tabela 8.2 está individualizada abaixo e compõe o candidato final de 400 testes. O aceite integral do plano continua limitado pelas provas de campo/gates. A contenção de capacidades por gate não é evidência de experiência equivalente: enquanto G05 estiver fechado, a transferência não é uma jornada liberada. Enquanto G02/G03/G04 estiverem fechados, conta real/autoridade/identidade novas não são capacidades homologadas.


A regressão complementar D12 injeta falha no segundo SKU, depois do primeiro item copiado. Verifica que a origem continua aberta, itens e dados/slot são iguais, os mesmos Hold IDs/quantidades/status/quant permanecem, e não sobra Session web, receipt de transferência ou Order. O teste passou no PostgreSQL junto da vertical J01/J07 e H09 (3 passed, 2,61s; `runtime-vertical-final.txt`).

Integração mista intermediária: `integration-mixed-registry-fixture.txt` registrou 379 passed e 7 failed. A causa foi a fixture `_clean_registry` de `packages/orderman/conftest.py`, que limpa o registro de handlers e não o repovoa para testes transacionais de framework no mesmo processo; entre as falhas, o handler do concierge tornou-se `None`. O gate final separa `test_commit_branches` do core em processo próprio, preservando essa fixture e sem mascarar as falhas como sucesso. Ensaios anteriores (366 passed com warning; depois 371 passed / 3 failed em integração de coorte/escopo e scope longo) são intermediários, não resultados finais nem novas contagens a somar. Os defeitos efetivos de coorte e scope longo receberam regressões; a colisão de registry é limite do harness misto.


## Ampliação adversarial após o checkpoint ff1c9bee

A revisão da tabela 8.2 reabriu provas técnicas independentes de gates: modify/commit, confirm/edit, transfer/site-edit, callback/cancel, revoke/send e handoff/tool. O lote de 378 testes acima é um checkpoint preservado; não certifica automaticamente as novas edições.

**Novo defeito reproduzido (callback/cancel):** `test_concierge_payment_race.py::test_pix_callback_and_unpaid_cancel_preserve_money_and_terminal_truth[cancel]` pausa o callback PIX após ler o pedido/recibo e antes de capturar, em conexão PostgreSQL independente. O cancelamento canônico vence, encerra pedido e cobrança; o callback registra o dinheiro em intent substituto, mas decide usando Order desatualizado e deixa saldo capturado sem estorno. O replay reconhece o intent já registrado e não repara o estado. `payment-race-before.txt`: 1 passed, 1 failed. A permutação callback vencedor impede corretamente o cancelamento por timeout. Correção mínima em `shopman/shop/services/pix_confirmation.py`: reler Order após booking e encaminhar replay ainda não liquidado ao mesmo lifecycle/refund. O recibo concluído só encerra replay quando fase on_paid e saldo devolvido canônicos comprovam liquidação, evitando alertas repetidos. `payment-race-replay-before.txt` preserva o ensaio intermediário com alerta duplicado (96 passed/1 failed); após ajuste, `payment-race-consumers-final.txt` comprova 97 passed, 8,28s, zero skips/warnings. Inclui três novos casos, webhooks, guards de pagamento, cancelamento fresco/motivos operacionais e handlers fiscais; nenhum gateway real foi usado.


| Tabela 8.2 / fronteira | Regressão PostgreSQL e oráculo | Artefato local |
|---|---|---|
| modify/commit | `test_concierge_commercial_races.py::test_modify_waits_for_checkout_commit_and_cannot_change_sealed_order`: edição espera lock e não altera pedido selado | `commercial-races-consumers-tests.txt`, 55 passed / 1 warning teardown de 4 conexões maduras |
| confirm/edit | `test_confirmation_waits_for_cart_edit_and_records_conflict_without_order`: confirmação espera edição e registra conflito sem pedido | mesmo lote |
| transfer/site-edit | `test_transfer_and_site_edit_do_not_leave_reservations_on_abandoned_source` (add/update/remove): writer da sacola bloqueia Session antes de tocar holds; origem abandonada sem reserva órfã | mesmo lote; novo subcaso D12/H08 confirmado e corrigido no owner `cart` |
| falha de persistência após hold | `test_cart_writer_rolls_back_hold_effect_if_session_write_fails` (add/update/remove): rollback conserva Session e estoque juntos | mesmo lote |
| callback/cancel | `test_concierge_payment_race.py::test_pix_callback_and_unpaid_cancel_preserve_money_and_terminal_truth`: callback vencedor impede timeout; cancel vencedor recebe registro+estorno canônicos sem ressuscitar pedido | `payment-race-consumers-final.txt`, 97 passed / 8,28s; zero skips/warnings |
| callback tardio/replay | `test_late_pix_replay_recovers_booked_money_after_interrupted_settlement`: interrupção após booking deixa dinheiro visível; replay estorna uma vez e não duplica incidente | mesmo lote |
| revoke/send | `test_concierge_boundary_races.py::test_pg_revocation_committed_before_send_lock_blocks_provider`; teste adicional em `test_concierge_consent_race.py` verifica bloqueio real com `pg_blocking_pids` | `boundary-races-tests.txt`, 81 passed e `observability-consent-tests.txt` 3 passed |
| handoff/tool | `test_concierge_boundary_races.py::test_pg_handoff_wins_lock_before_tool_and_preserves_no_effect`: posse humana vence lock; tool sem efeito | `boundary-races-tests.txt`, 81 passed |
| conteúdo não confiável | `test_product_name_cannot_become_fact_or_action`, `test_untrusted_tool_result_message_does_not_override_factual_renderer`, `test_canonical_catalog_name_cannot_create_external_payment_action`, `test_structured_access_link_order_actions_and_pix_are_preserved` | `boundary-races-tests.txt`, 81 passed; URLs/quebras no nome canônico reproduzidas nesta ampliação, corrigidas no renderer (D13) |

Carga instrumentada ampliada (`runtime-load-final.txt`): 100 conversas, 10 mil mensagens históricas, 109 novas entradas, burst de 10, 4 workers paralelos. 100 conexões de backend utilizadas cumulativamente (não pico simultâneo), zero deadlocks incrementais e zero locks em espera ao final; RSS de pico 173.768.704 bytes, SQL somado 2,547s e consulta máxima 11ms; turno mediano 41ms/p95 63ms, espera entrada→worker p95 1,024s, zero retries de saída e saída máxima 52 bytes. O dispatcher e a latência do fornecedor não são medidos. São fakes de modelo/transporte e uma carga local, não dimensionamento de produção ou prova de ganho humano. Telemetria testa IDs internos correlacionáveis e ausência de texto, identidade bruta ou eco sensível do provedor (`test_concierge_observability.py`, lote de 3 testes com consentimento).


## Fechamento do candidato

**Código e testes: `97aaad216f409486c58a65ec8b88207fafbab685`. Integração final: 400 passed, 42,67s, zero skips e zero warnings** (`final-integration.txt`). Ruff de 49 arquivos Python alterados desde a base e diff check passaram. Django check e `makemigrations --check --dry-run` sem drift. O checkpoint anterior `ff1c9bee331e931250c10cd4a9de0c118f6dbf4e` teve 378 passed em 30,91s, zero skips/warnings e está preservado em `integration-ff1c9bee3.txt`. Os lotes complementares de pagamento (97), fronteiras (81) e corridas comerciais (55) estão verdes, com ressalva de teardown no último; não são somados porque coberturas se sobrepõem. Core: 9 passed, 11,37s em processo separado por isolamento do registry; consumidores de sacola: 5 passed, 14,01s; `make admin` integral: 264 passed, 64,44s. Esses lotes não são somados ao total integrado.

Reprodução: `evidence/conversational/ISOLATED-RUNTIME.md` descreve o ambiente sem segredos; carregar `final-selection.json` e passar os caminhos ao runner, com `DATABASE_URL=postgres://concierge_test@localhost:56419/concierge_final`, `REDIS_URL=redis://localhost:56420/12`, `PYTHONDONTWRITEBYTECODE=1` e `-rs --reuse-db`. A base de comparação permanece `1138c95eee0862630330328cf3bfe2f0b6424796`.

Não houve homologação ManyChat, mensagem a contato real, cobrança real, piloto, rollout ou migração de ambiente real. G01–G07 permanecem sem aprovação nominal nesta sessão; as flags dependentes continuam fechadas por padrão. O candidato permite revisão de código e provas locais, não autorização implícita para ativar. A conclusão humana “menos esforço/erro e resultado/próxima ação entendidos” requer as medições J01–J13 e os gates do plano; não é inferida de testes ou carga fake.

Ambiente encerrado após validação: browser local já parado; Redis privado recebeu `SHUTDOWN NOSAVE` e PostgreSQL privado `pg_ctl -m fast stop`, ambos exit 0 (`runtime-shutdown.txt`). Nenhum serviço alheio foi parado. A reprodução requer reiniciar o ambiente isolado conforme `ISOLATED-RUNTIME.md`.


## Adendo: corpo real do portão ManyChat

Em 11/09/2026, o operador confirmou o endpoint `https://api.boulangerie.com.br/api/webhooks/manychat/conversation/` e o corpo legado de quatro campos (subscriber_id, text, first_name, last_name), sem event ID. O candidato local `2583e3744c7b2f4f4330db1a5f5a6b9a11f84c08 aplica a exceção explícita C01: opt-in desligado por padrão para catálogo público e handoff determinísticos no mesmo Message/Conversation/Directive, sem modelo, identificação ou mutação comercial. Não altera flow ou servidor. Evidências e roteiro/rollback: [gateway-reuse](../../evidence/conversational/gateway-reuse/README.md).

| WP / achado revalidado | Evidência / resultado | Limite ou gate |
|---|---|---|
| WP00/WP01: Body e URL antes desconhecidos | Informados pelo operador; dados pessoais do exemplo não viram fixture | Origem de event ID estável permanece sem prova |
| WP01/WP02: formato sem ID | Agora pode registrar recebimento legacy_unverified para leitura/humano mediante opt-in; PK não é identidade de fornecedor | Sem exatamente-uma-intenção; retries podem repetir consulta |
| WP02/WP03: revogação e autoridade | Backlog legado estaciona sem loop/bloqueio de novos v2; reload não libera tool mutante; confirmação legada nunca vira prova posterior | Opt-in false; não reprocessar legado como evento verificado |
| WP06/WP07: janela e entrega | Retry legado não atualiza last_inbound_at; sem janela comprovada, not_applied/window_closed; unknown não reenvia | Janela e delivery reais não homologados |
| WP08/WP09: omotenashi e operação | Copy canônica explica consulta/atendente e ausência de alteração; leitura normal não aumenta contador de falhas | Ganho humano e roteiro real não medidos |
| WP10: testes/rollback | Integração 419 passed e, após ajuste do contador, seleção final 96 passed; gates descritos no adendo | Não é piloto, homologação nem rollout |

Antes: Body legado recusado pelo candidato por ausência de ID. Depois: com opt-in autorizado, contexto preservado e consulta pública/encaminhamento possíveis, com saída condicionada à janela previamente comprovada. Compra permanece desabilitada nesse formato. Sem nova migração; rollback funcional desliga apenas a capacidade e preserva registros. O spec continua em contract_version=0 e o drift Marketing já documentado impede aplicação integral cega do arquivo.

## Adendo de arquitetura v3 — 12/09/2026

Este adendo substitui as conclusões arquiteturais v2 para o candidato atual sem
reescrever as evidências históricas acima. A base registrada da nova worktree é
`cbda00f02e692fc7d1949a4e11024ace33245362`, branch
`codex/concierge-transport-bindings-20260912`. Após revalidação contra
`origin/main` em `12f2b1b34c3e1f4b95d3b48e69937e5a6684e287`, o código e os testes v3
validados formam o SHA `e87b9c4de04db9b48e3f02b0bf1ac6345a70c2fc`.

O operador autorizou uma arquitetura pré-go-live sem compatibilidade no runtime.
`Conversation` passa a representar a jornada lógica e os fatos comerciais.
`ConversationBinding` representa cada endereço opaco de transporte por
`provider + account + channel + subject + connection_key`. Mensagens de entrada e
resposta apontam para o binding causal. `OutboundAttempt` registra cada execução
de saída de forma append-only, inclusive estado, código e receipt do provider.

O registry de connections é explícito e a rota confiável escolhe a connection.
O domínio recebe contratos normalizados e não ramifica por WhatsApp, Instagram,
TikTok, ManyChat ou Meta. WhatsApp/ManyChat é o primeiro binding real. TikTok,
Instagram ou Meta direta exigem adapter e configuração próprios, com capacidades
e gates separados; não exigem uma nova Conversation, fila, regra comercial ou
superfície paralela.

O corpo ManyChat confirmado tem cinco campos (`subscriber_id`, `text`,
`first_name`, `last_name`, `provider_timestamp`) e usa a rota v3
`/api/webhooks/concierge/manychat-whatsapp-primary/events/`. `#c` sozinho é
normalizado para `oi`. `provider_timestamp` permanece evidência da janela de
resposta e nunca se torna `occurred_at`, ID de evento ou confirmação comercial.

Na ausência de ID oficial, cada recebimento autenticado é at-least-once, com
assurance explícita e recibo local. O lote fica somente leitura por autoridade do
núcleo. Não há modo “legado”, ID sintético ou deduplicação por
contato + timestamp. Um eventual ID enviado pelo provider só autoriza dedupe e
mutação depois de homologação e gate explícito de identidade estável.

### Prova técnica v3

As contagens abaixo são execuções distintas e se sobrepõem; não devem ser
somadas.

| Prova | Resultado | Limite da evidência |
|---|---|---|
| Storefront integral em SQLite | **1729 passed, 34 skipped**, 63,14 s | os skips exigem PostgreSQL; SQLite não prova locks |
| Concierge integral em PostgreSQL 16 + Redis isolados | **293 passed, zero skips**, 70,66 s | adapters e efeitos externos são fakes; nenhum fornecedor foi chamado |
| Concierge selecionado em SQLite | **269 passed, 24 skipped**, 27,70 s | regressão rápida; o Storefront integral foi repetido após o hardening final |
| Admin/Unfold | checker canônico + **268 passed**, 53,07 s | superfície local, sem inbox ManyChat |
| QA visual Admin | 2 perfis × 2 gates × 1440/390; console sem erros | dados sintéticos; oito capturas e JSONs em `evidence/conversational/browser-v3/` |
| Schema e higiene | `check`, `makemigrations --check --dry-run`, Ruff e `git diff --check` aprovados | não executa migração em ambiente real |
| Gate de runtime | roundtrip PostgreSQL + Redis aprovado | serviços privados temporários, sem credenciais externas |

A carga isolada cobriu 100 conversas, 10 mil mensagens históricas, 109 entradas,
burst 10 e quatro workers. Foram 100 saídas aceitas pelo fake, 3.000 queries,
zero retry, zero estado `unknown`, zero deadlock, zero lock restante, p95 de
0,043 s por turno e p95 de 0,835 s da entrada ao worker. Isso prova contenção e
concorrência do software; não mede modelo, fila do provider, aparelho, custo ou
ganho humano.

### WP00–WP10 no candidato v3

| WP | Implementação e evidência | Estado correto |
|---|---|---|
| WP00 | base/SHA registrados, worktree exclusiva, owners e diagnóstico revalidados contra `origin/main` | fatia técnica concluída; baseline humana G06 pendente |
| WP01 | rota por connection, autenticação antes da persistência, corpo ManyChat exato, ACK após Message + Directive e dedupe somente com ID verificado | software testado; contrato/flow real G02 pendente |
| WP02 | cada entrada avança o fence único; claim, ferramenta, persistência e envio com versão anterior são revogados; lote causal e recuperação permanecem duráveis | concluído em PostgreSQL isolado |
| WP03 | resposta persistida antes da rede e `OutboundAttempt` com `accepted/not_applied/unknown/delivered/read`; `unknown` sem retry | software testado; aceitação/entrega do provider G02 pendentes |
| WP04 | confirmação comercial exige evento e cliente verificados, revisão vigente, novo inbound, locks e receipt canônico | concluído no core e em corridas PostgreSQL; corpo atual sem ID permanece leitura |
| WP05 | transferência, acesso e preservação da origem continuam nos services canônicos | regressões aprovadas; ativação/política G05 pendentes |
| WP06 | status, pagamento, fulfillment e efeitos existentes preservados | vertical e H09/H12 aprovados; ordem percebida real não medida |
| WP07 | handoff lógico contém todos os bindings, sync é por binding e incerteza preserva posse humana; Admin mostra próxima ação | software e browser aprovados; owner/SLA/retorno G03 pendentes |
| WP08 | domínio sem branches de provider/canal; adapter opaco estilo TikTok prova segundo transporte no mesmo core | arquitetura testada; adapters e gates reais de novos canais pendentes |
| WP09 | Storefront, PostgreSQL/Redis, carga, regressões e browser executados | prova técnica concluída; pessoas, webview e fornecedor G02/G06 pendentes |
| WP10 | migração 0051 move transporte para Binding e cria Attempts antes de remover colunas; ensaio preserva conversa, mensagens e evidência | migração sintética aprovada; backup/alvo/janela real G07 pendentes |

### Matriz de achados v3

| Tipo | Achado | Decisão/prova atual |
|---|---|---|
| defeito comprovado | lock de Message com `select_related` no binding anulável gerava `FOR UPDATE` sobre outer join | locks separados; seleção PostgreSQL verde |
| defeito comprovado | configuração malformada podia chegar ao registry como estrutura inesperada | registry valida mapping, escopo e adapter e falha fechado |
| defeito comprovado | política de janela preparada poderia sobreviver à revogação da configuração | autorização revalida configuração completa no instante da saída |
| defeito do ensaio | MigrationExecutor com alias deixava RunPython histórico escrever em `default` | router do ensaio mantém todas as operações no banco isolado; suíte combinada verde |
| defeito comprovado | inline tabular cortava campos finais dos bindings no desktop | `StackedInline`; repetição em 1440 e 390 com admin/viewer |
| defeito comprovado | uma correção recebida durante o modelo ainda permitia persistir/enviar a resposta anterior | toda entrada avança o único `turn_fence`; resposta velha é revogada antes da persistência e revalidada antes da chamada remota |
| defeito comprovado | URL com aparência de arquivo era inferida como mídia pelo núcleo | `message_type` normalizado é a única fonte; URL textual continua texto |
| defeito comprovado | blocos extras, como Pix, não passavam pelo limite semântico do adapter | resposta principal e extras usam o mesmo fragmentador, sem cortar linha essencial |
| defeito comprovado | a evidência do ACK de handoff usava o maior PK, que podia conter timestamp mais antigo | seleção usa a melhor evidência válida entre todas as entradas consumidas |
| defeito comprovado | ferramentas gravavam origem WhatsApp/ManyChat mesmo sob outro transporte | origem vem do binding causal e é preservada no carrinho e no access link |
| defeito comprovado | duas contas ManyChat pareciam isoladas, embora o gateway atual use credencial global | adapter declara gateway de conta única e falha fechado diante de duas contas ativas |
| defeito comprovado | replay do mesmo evento podia conflitar apenas porque perfil ou janela mudaram | hash de intenção cobre subject, ID, tipo e texto; metadados voláteis ficam fora |
| defeito comprovado | chave do Access Link podia autenticar também o webhook do Concierge | `CONCIERGE_API_KEY` é obrigatória e independente; rotação usa somente a chave anterior do Concierge |
| hipótese rejeitada | receipt sintético `subscriber_id + provider_timestamp` poderia colapsar repetição legítima | não implementado; sem ID oficial o ingresso é at-least-once e somente leitura |
| hipótese testada localmente | outro provider/canal exigiria ramificações no domínio | fake TikTok/DM usa o mesmo Conversation, Message, Directive e Attempt sem branches |
| hipótese testada localmente | continuidade entre canais poderia ser inferida de nome/telefone do payload | payload nunca une jornadas; `attach_binding` exige scope configurado, gate e `IdentityResolution` verificada contra Customer canônico |
| simplificação confirmada | detectar entrada tardia exigiria watermark e consulta extra por turno | o fence já canônico resolve a versão do contexto; carga permaneceu em 3.000 queries |
| decisão humana | projeto pré-go-live não mantém rota, flags ou modelos v2 | testes e caminho runtime legados removidos; migração é forward-only |
| gate externo | documentação pública e corpo atual não comprovam ID estável da mensagem | `event_id` é opcional; só ganha assurance após G02 e flag explícita |
| gate humano | redução de esforço/erro e clareza final ainda não foram medidas com operador/cliente | G06 e jornadas J01–J13 permanecem pendentes |

### Jornadas antes/depois da separação de transporte

| Situação | Antes | Depois testado |
|---|---|---|
| entrada ManyChat | endpoint e domínio acoplados ao par ManyChat/WhatsApp | rota escolhe a connection; o adapter traduz cinco campos para contrato comum |
| ausência de ID | tentação de fabricar dedupe por contato/tempo | cada POST é preservado; consulta/menu/humano disponíveis e mutação bloqueada |
| correção durante resposta | a resposta baseada no contexto anterior podia chegar depois da correção | a entrada avança o fence, a resposta velha não sai e o lote inteiro volta com o contexto corrigido |
| troca ou novo canal | identidade de transporte dentro da conversa | novo binding mantém a conversa lógica; associação entre clientes exige verificação explícita |
| timeout de envio | um booleano não distinguia efeito possível | tentativa fica `unknown`, receipt/história permanecem e não há retry cego |
| atendimento humano | sincronização remota confundida com posse lógica | conversa continua com a equipe enquanto qualquer binding não confirma retorno |
| trabalho do operador | precisava inferir provider, canal e certeza do envio | Admin mostra bindings, assurance, estado, receipt sem sobrescrita e próxima ação |

Não houve homologação do flow ManyChat, mensagem real pelo provider, entrega no
aparelho, piloto com operador/cliente ou rollout. G01–G07 continuam pendentes
conforme sua dependência. Uma connection sem gate permanece inativa; mutações sem
assurance permanecem contidas.

### Migração e rollback

A migração v3 converte os registros existentes para Conversation + Binding +
Message + Attempt e remove da Conversation os campos de transporte que passam a
pertencer ao binding. Ela é intencionalmente **forward-only**: o reverse não
descarta evidence nem recria uma representação menos precisa.

Rollback operacional significa desligar a connection e/ou o switch global,
interromper novas admissões e saídas, conciliar `executing`/`unknown` e preservar
Conversation, Binding, Message, Directive, Attempt, pedidos e receipts. Não
executar downgrade destrutivo, apagar fila, reenviar efeito incerto ou fabricar
compensação. Correção de schema segue adiante com nova migração.

### Etapas que não se confundem

| Etapa | Estado em 12/09/2026 | Prova necessária para avançar |
|---|---|---|
| Implementação técnica | **Concluída no SHA `e87b9c4de04db9b48e3f02b0bf1ac6345a70c2fc`** | Reabrir se drift, regressão ou divergência do contrato aparecer. |
| Homologação | Não executada | Flow real, cinco campos, continuidade, janela, ACK/worker, handoff e saída/entrega observados com credenciais e coorte de teste autorizadas. |
| Piloto | Não iniciado | Gates nominais, pessoas/coorte autorizadas, owner/SLA e medição J01–J13 de esforço, erro e compreensão. |
| Rollout | Não autorizado | Release/alvo fixados, backup e rollback exercitados, reconciliação limpa, aceite dos gates e decisão explícita de expansão. |

O guia operacional atualizado está em
`docs/guides/whatsapp-concierge.md`; o desenho da connection está em
`docs/plans/CONCIERGE-MANYCHAT-CANONICAL-FLOW-2026-09-12.md`. Este adendo não
altera a exigência central do plano: o operador precisa enxergar contexto,
resultado e próxima ação com menos esforço e erro, e essa melhoria humana só pode
ser declarada após a medição correspondente.
