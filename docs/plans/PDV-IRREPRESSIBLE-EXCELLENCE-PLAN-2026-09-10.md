# PDV — plano de excelência irreprimível

**Data:** 2026-09-10

**Estado:** planejamento concluído; execução de produto não iniciada; gates humanos não aprovados por este documento.

**Baseline principal:** `696f541055f396a16fb1c080c7bea69243df720d`, referência local `origin/main` no momento da auditoria. Não houve fetch nem verificação do HEAD remoto.

**Escopo:** `surfaces/pos-nuxt` e a cadeia que sustenta balcão, comandas, pedidos, recebimento, caixa, cozinha, comprovantes, cliente, estação e periféricos.

**Evidências e limites:** [auditoria desta sessão](../reports/PDV-EXCELLENCE-PLANNING-AUDIT-2026-09-10.md).

**Delegação:** [prompt de execução](PDV-IRREPRESSIBLE-EXCELLENCE-PROMPT-2026-09-10.md).

> O resultado pretendido é um balcão que permite atender, cobrar e seguir com certeza: cada valor tem uma origem, cada efeito tem uma prova, cada pendência tem uma próxima ação e cada interrupção preserva o trabalho. O programa começa pelas fronteiras incompletas de terminal, pagamento, revisão e recuperação; conserva as garantias já existentes nos domínios.

## 0. Contrato para a sessão executora

### 0.1 Autorização e limites

Ler este documento integralmente antes da primeira alteração. A futura instrução de execução autoriza inspeção, implementações reversíveis no repositório, testes sintéticos, documentação, migrations aditivas necessárias e commits locais coesos em worktree e branch `codex/` exclusivos. Esta sessão de planejamento não executou essas mudanças de produto.

Não autoriza merge, push, PR, deploy, escrita em produção, cobrança ou estorno real, emissão/cancelamento fiscal real, envio de comprovante a pessoa real, provisionamento/revogação de estação, alteração de credenciais, instalação de agente no balcão nem acionamento de impressora/gaveta/balança reais. Nenhum roteiro de piloto constitui autorização para executá-lo.

Não remover confirmação ou segunda assinatura para cumprir budget. Não decidir política de dinheiro, identificação, fiscal, crédito, retenção ou hardware por conveniência técnica. Não abrir exceção silenciosa às ADRs. Gate pendente permite preparar alternativas e provas sintéticas, sem habilitar a política dependente.

### 0.2 Preparação e convivência entre sessões

1. Registrar `git status --short --branch`, `git rev-parse HEAD` e `git worktree list --porcelain`; ler os `AGENTS.md` aplicáveis, se existirem.
2. Identificar a base de integração disponível e sua relação com o SHA auditado. Uma branch de nome recente pode conter código antigo. Conferir SHA, ancestralidade e diff; não assumir que o checkout de entrada é a base correta.
3. Criar worktree exclusivo a partir da base commitada escolhida, branch `codex/pdv-<escopo>-<session-id>`. Não reutilizar diretório de outra sessão nem implementar no checkout compartilhado.
4. Se o plano ainda não existir na base, transportar somente este plano, o prompt e o relatório de auditoria como inputs explícitos, verificando SHA-256. Não copiar código não commitado alheio.
5. Se uma correção necessária estiver em outra branch, conferir código e testes. Preparar dependência/handoff; não incorporar automaticamente a branch, cherry-pick ou mudanças sujas sem coordenação do integrador.
6. Criar log exclusivo `docs/reports/execution/pdv-<session-id>.md`. O plano é referência; progresso pertence ao log, sem múltiplos agentes escrevendo no mesmo placar.
7. Antes de editar, reler trecho e `git diff -- <arquivo>`. Contexto divergente exige nova análise. Preservar mudanças rastreadas e não rastreadas de terceiros integralmente.
8. Proibidos `git reset --hard`, `git clean`, `git restore`, `git checkout --`, stash abrangente, `git add -A`, `git add .`, formatter/codemod repo-wide e resolução mecânica por ours/theirs.
9. Adicionar apenas paths próprios explícitos, revisar diff staged e fazer commits pequenos por comportamento. Nenhum commit com teste vermelho acidental; reproduções de lacunas podem ficar em branch de investigação ou como evidência, sem enfraquecer a CI.
10. Serializar hotspots: `api/operations.py`, `backstage/contracts.py`, permissions/URLs centrais, `shop/services/pos.py`, `remote_mutations.py`, migrations de todos os cores, `operator-kit`, geradores/contratos, lockfiles, CI e arquivos de release. Declarar owner e janela antes de mexer; sem coordenação, trabalhar em testes/documentação locais independentes.
11. Caso haja delegação explicitamente autorizada, cada agente recebe WP, paths, dependências e critérios; não compartilhar writer de migration/schema/arquivo central. O integrador regenera derivados e repete gates após integração semântica. Este protocolo não exige criar subagentes.
12. Handoff inclui SHA-base, branch/worktree, commits, paths, gates, decisões, migrations, flags, comandos/resultados, riscos, ordem de integração e rollback. Não integrar por conta própria.

Sem isolamento, continuar somente em leitura. Um gate bloqueia sua fatia dependente; continuar fatias independentes seguras. Parar integralmente quando não restar caminho autorizado.

### 0.3 Leituras normativas

- ADR-002 (centavos), ADR-003 (directives), ADR-005 (orquestração), ADR-006/007/010 (lifecycle/handlers), ADR-011 com refinamentos atuais, ADR-012/014 (Projection + Actions e apresentação), ADR-013 (offline), ADR-015 (compatibilidade), ADR-016 (SSE), ADR-018/019 (canal/promoção), ADR-022 (Cashman) e ADR-025 (signals/on_commit).
- `docs/specs/pos.md`, `docs/reference/backstage-pos-surface-contract.md`, `docs/reference/headless-surface-contract.md`, `docs/reference/projection-contracts.md`, `docs/engineering/nuxt_design_system.md`, `docs/engineering/backstage-design-system.md` e README do `operator-kit`.
- Skill `unfold-admin-canonical` antes de qualquer Admin: seus três cânones são `unfold_admin_page_playbook.md`, `unfold_canonical_policy.md` e `unfold_canonical_inventory.md`; gate final `make admin` sem escopo.
- Planos antigos de PDV, Cashman e hardware servem como histórico. Especificações têm passagens defasadas: confrontar com ADRs posteriores, decisões registradas e código. Divergência de política vai a G-02/G-03; não escolher o texto mais conveniente.

### 0.4 Ciclo obrigatório e estados de conclusão

Por fatia: **reproduzir → contratar → implementar verticalmente → provar sob falha → registrar**. Atravessar domínio, API, projection/action, cliente, UI, observabilidade e documentação quando a mudança exigir. Evitar uma fase longa de interfaces sobre contratos inseguros.

Achado já resolvido vira `já satisfeito`, com teste no HEAD atual. Hipótese só vira defeito após reprodução ou prova inequívoca da cadeia. Não reescrever Cashman, Payman, KDS ou idempotência existentes para cumprir um nome de WP.

- **WP tecnicamente concluído:** aceite, testes e evidência local satisfeitos; gates de ativação continuam visíveis.
- **Implementação técnica concluída:** todos os WPs técnicos necessários fechados; não implica operação autorizada.
- **Pronto para piloto:** gates de política/segurança, candidato, capacidade e ensaios aprovados; aguarda janela/alvo autorizados.
- **Rollout concluído:** piloto e expansão autorizados, observados e reconciliados.
- **Plano concluído:** Definition of Done integral assinada. Testes locais não comprovam hardware nem produção.

## 1. Avaliação dos planos de referência

Marketing oferece maior detalhamento de evidências, resultados parciais/desconhecidos, WPs com migração e reversão, contratos, budgets e DoD. Produção oferece sequência vertical clara, preservação de garantias dos cores, disciplina de worktree e omotenashi atravessando P0/P1/P2. Ambos acertam ao separar implementação de piloto/rollout e ao exigir recuperação acionável.

Para PDV, conservar esse rigor e ajustar quatro pontos:

1. **Uma base recente e explícita.** O checkout de entrada estava em `b589e22c5`; a referência local mais recente contém muitas correções. Este plano revalidou os achados principais em `696f54105`.
2. **Não prescrever infraestrutura duplicada.** Cashman já é ledger, Orderman já tem idempotency keys e KDS já tranca Session. “Outbox operacional” significa visão/progresso dos efeitos canônicos; não um novo domínio financeiro ou command bus do PDV.
3. **Dependências sem ciclos.** Baseline e descobertas podem anteceder decisões; nenhuma decisão de piloto precisa estar tomada para criar uma reprodução local. Cada gate informa exatamente qual transição impede.
4. **Garantias de balcão concretas.** Dinheiro recebido, pedido criado, pagamento confirmado, cozinha acionada, nota autorizada, job de impressão aceito e papel entregue são certezas diferentes. O fechamento não pode esconder uma delas nem exigir que o operador confira tudo em outros sistemas.

Não copiar percentuais de rollout de campanha para terminais. A unidade inicial de piloto é uma estação/equipe, com turno e troca de operador completos. Budgets são hipóteses mensuráveis até a observação humana; não resultados já atingidos.

## 2. Resultado operacional e omotenashi

O operador deve conseguir:

- identificar-se e ver a estação/gaveta correta sem redigitar contexto;
- iniciar venda direta sem inventar comanda, quando o canal permite;
- localizar produto, lançar quantidade/unidade, observação e desconto permitido sem perder o carrinho;
- abrir, pausar, retomar, transferir/dividir comanda e enviar o delta correto à cozinha;
- reconhecer cliente recorrente com segurança, usar endereço já conhecido e distinguir cadastro de dados só do comprovante;
- cobrar no meio escolhido, enxergar restante e troco canônicos, perceber claramente PIX pendente e cartão declarado versus integração comprovada;
- terminar a venda e tratar impressora, nota ou cozinha pendentes sem vender/cobrar de novo;
- pedir troco, registrar suprimento/sangria, devolver dinheiro autorizado e fechar a custódia correta cegamente;
- recuperar Wi-Fi, sessão, resposta perdida e conflito sem reconstruir pedido ou memorizar valores;
- entregar o turno com pendências, responsáveis e próximas ações prontas.

**Pergunta de aceite de toda fatia:** que toque, memória, espera, redigitação, busca, consulta externa ou incerteza previsível foi removido, e qual evidência prova isso sem reduzir controle?

O caso comum deve pedir apenas decisões novas. Dados já conhecidos são pré-preenchidos, mas preço, prazo, disponibilidade, pagamento e autorização são revalidados pelo backend. Sugestão nunca captura dinheiro, concede crédito, troca identidade ou aprova exceção sozinha. Acessibilidade, feedback e precisão fazem parte do trabalho seguro, desde P0.

## 3. Baseline verificada e limites

### 3.1 Execução desta auditoria

Leitura integral dos planos Marketing (1.743 linhas) e Produção (1.005 linhas), leitura dirigida de PDV e dependências, comparação de refs locais, testes em worktree exclusivo com dados sintéticos. Não houve acesso ao app vivo, dados reais, gateway, SEFAZ, impressora ou gaveta. Não houve observação de operador, carga representativa nem corrida PostgreSQL nesta sessão.

| Gate/ensaio | Resultado | Alcance |
|---|---|---|
| Instalação PDV com Node 22 e `npm ci --no-audit --no-fund` | passou | lock respeitado; warning de dependência deprecated registrado |
| `npm test -- --reporter=dot` | 48 arquivos, **833 testes passaram** | muitos warnings Vue; não comprova E2E |
| Backend/agente: sete módulos selecionados | **182 passaram, 1 skip** | SQLite de teste; skip de serviço Linux em macOS |
| `npm run lint` | **falhou: 4 erros, 25 warnings** | defeitos preexistentes listados no relatório |
| Typecheck após instalar também o kit; build | **ambos passaram** | build com warnings de plugin/sourcemap; setup incompleto do kit havia feito a primeira tentativa de typecheck falhar |
| Quatro módulos backend adicionais | **44 passaram** | regressões de correções recentes; total das duas rodadas: 226 passed, 1 skip |
| Ensaios isolados das funções atuais | terminal do corpo vence estação; review/close consultam turno default; tender único perde valor; action ausente usa fallback | demonstração com dependências fake; efeito financeiro completo exige teste integrado |

### 3.2 Garantias existentes a preservar

| Evidência no código atual | Consequência para a execução |
|---|---|
| `shop/services/pos.py::close_sale/_claim_sale_request` usam transação e unique claim do Orderman | não afirmar “venda sem idempotência”; completar escopo, fingerprint, obrigatoriedade e recovery |
| `cashman.services.ledger` e `shifts` usam locks; Entry tem constraints para efeitos de pedido | não criar segundo livro; testar conservação/reconciliação e crash windows da borda |
| `_cash_idempotent` já envolve várias mutações e frontend mantém chave | não refazer dedupe; provar atomicidade de efeito+receipt e replay isolado |
| `kds.fire_lines` serializa Session e deduplica por `line_id`; linhas do carrinho já têm identidade estável | preservar delta e identidade; investigar wrapper, cancelamento/reenvio e concorrência com save/move |
| `open_cash_shift` já rejeita negativo; `resolve_terminal(strict=True)` já recusa ambiguidade em vários writes | relatório antigo está parcialmente superado; fechar os chamadores restantes |
| Aprovação de desconto já delega ao validador comum PIN/crachá, com anti-self-approval | não restabelecer PIN-only nem exigir dois fatores sem gate humano |
| Já existem recibo servidor ESC/POS, comprovante de movimento, sonda do agente, trava/sensor de gaveta e eventos | não mandar construir tudo do zero nem declarar “hardware apenas simulado” para todo o sistema |
| Há política de contato/CPF do comprovante, conflito de identidade, agenda de retirada/entrega e `/tickets` | preservar essas jornadas e testes recentes; evolução precisa incluí-las |

### 3.3 Achados atuais rastreáveis

Prioridade é risco para expansão/piloto, não alegação de incidente real. `V` = confirmado em código/ensaio isolado; `H` = hipótese que exige reprodução integrada; `D` = decisão/discovery. Cada linha deve receber teste e fechamento no WP indicado.

| ID | Grau/prioridade | Fato observado e limite | WP |
|---|---|---|---|
| PDV-F01 | V/P0 | POSView recebe estação, mas `_open_cash_shift_for_request` chama `current_shift()` sem ref/strict; review/close usam esse helper. Leitura e venda podem apontar gavetas diferentes. | 01 |
| PDV-F02 | V/P0 | `_terminal_do_pedido` prefere `terminal_ref` do corpo ao cookie, sem comparar; abrir caixa também aceita ref do corpo. Não há vínculo uniforme estação→terminal nos comandos. | 01 |
| PDV-F03 | V/P0 | `resolvePayment` descarta valor/reference/collection da linha única não cash; `buildPosSaleIntent` envia tenders somente em mixed. O valor informado não atravessa a borda integralmente. | 03 |
| PDV-F04 | V/P0 | Sale claim aceita ausência de chave; não compara hash semântico. `_cash_idempotent` aceita ausência e usa escopo por ação sem ator/terminal/payload. Replay não é um contrato completo de intenção. | 02 |
| PDV-F05 | V+H/P0 | `run_idempotent_mutation` confirma claim, executa efeito e grava resposta em etapas separadas; crash após lançamento e antes de receipt pode deixar in_progress e replay tardio perigoso. Reproduzir nos comandos Cashman. | 02 |
| PDV-F06 | V+H/P0 | `save_pos_tab` calcula ops a partir de leitura anterior à transação; payload/TS não carregam revisão esperada. Lock interno não detecta edição obsoleta de outro tablet. | 02/04 |
| PDV-F07 | V/P1 | `actionHref` fornece endpoint fallback mesmo com Actions vazias; gerador cobre versão/enums, Action e payloads amplos continuam manuais. Não equivale a autorização ausente no servidor. | 05 |
| PDV-F08 | V+H/P0 | `reviewSale` aceita resposta sem fingerprint/epoch; close não carrega identidade da revisão mostrada. Resposta antiga e preço/agenda alterados entre review/close exigem reprodução. | 03 |
| PDV-F09 | V/P0 | Fallback de erro de `submitSale` diz “O pedido não foi fechado” mesmo em falha de transporte; exceção também pode ocorrer no refresh após sucesso. Mensagem pode negar efeito já ocorrido. | 02/06 |
| PDV-F10 | V/P1 | Um `pendingPixOrderRef` em memória pode ser substituído pela próxima venda e encaminhado por toast ao gestor; pendências simultâneas/reload não têm prova de continuidade no PDV. | 06 |
| PDV-F11 | V/P1 | `searchCustomers` transforma erro em lista vazia e não cancela resposta obsoleta. Pode sugerir inexistência/mostrar seleção antiga. | 07 |
| PDV-F12 | V+H/P1 | Display usa BroadcastChannel global `pos-customer-display`, sem identificador de estação/publisher; snapshot do consumidor não é validado/versionado. Duas janelas vendedoras na mesma origem podem disputar o display. | 08 |
| PDV-F13 | V+H/P1 | Recibo browser é congelado a partir do carrinho/review; existe recibo canônico servidor. Verificar paridade real em desconto, taxa, troco e replay, sem remover snapshot útil. | 06/08 |
| PDV-F14 | V+H/P1 | Fire protege criação no KDS, mas wrapper atual salva `Session.data` lida antes, após o serviço, sem uma fronteira única com save/move/unfire. `client_request_id` aparece em log, não como receipt da operação completa. | 04 |
| PDV-F15 | V/P1 | Testes E2E configurados cobrem guards/resiliência via mock, um projeto desktop. README ainda diz que PDV não tem pages/router. Não há prova CI do turno integrado nesta configuração. | 00/11 |
| PDV-F16 | V/P1 | Lint preexistente vermelho; warnings de props/lifecycle nos testes reduzem confiança no harness. | 00/11 |
| PDV-F17 | H/P1 | Draft direto, tentativas, contato e pendências precisam de ensaio reload/logout/troca de operador; estado reativo/autosave online não prova recuperação durável segura. | 06/07/09 |
| PDV-F18 | H/P1 | HTTP, headers, cache, sessão, tokens do agente e `/display` precisam de matriz por rota/erro; herdar operator-kit não prova deploy atual seguro. | 09 |
| PDV-F19 | D/P1 | Sem baseline de turno, disponibilidade de hardware e capacidade observada, não há prova de budgets/SLO nem de ergonomia real. | 00/08/10/12 |

Não transportar como defeitos: crachá inexistente, falta absoluta de ESC/POS/gaveta, perda de `line_id` em todo save, aprovação de desconto PIN-only, clamp negativo ainda vigente ou inexistência de cliente/agenda/tickets. Verificá-los como regressões do que já funciona.

## 4. Fronteiras e invariantes

### 4.1 Um dono para cada fato

| Fato | Dono | Papel do PDV |
|---|---|---|
| Produto, preço, promoção e canal | Offerman/Shopman e política do canal | apresentar valor resolvido e solicitar intenção |
| Sessão/comanda, pedido, estoque comprometido | Orderman/Stockman via orquestrador | preservar identidade e revisões; mostrar resultado |
| Pagamento, captura, reembolso por método | Payman e serviços de pagamento | mostrar fonte/estado; executar apenas Action autorizada |
| Custódia, entradas/saídas e contagem cega | Cashman | operar turno correto; nunca criar saldo paralelo |
| Produção/cozinha/retirada | KDS/Craftsman/Orderman | enviar delta, acompanhar e apontar pendência exata |
| CPF, telefone, endereço e identidade | Guestman/Doorman e política de cliente | escolher pessoa; separar dado da venda de atualização cadastral |
| Fiscal | Fiscalman/adapters/directives e política aprovada | exibir intenção, autorização/falha/unknown; não escolher regra fiscal |
| Estação, operador e aprovador | Doorman/Django/capabilities | manter identidades distintas e auditáveis |
| Job e sensor físico | agente local/spooler/dispositivo | relatar somente o nível de certeza comprovado |
| Configuração/auditoria | Admin Unfold canônico | deep-link contextual; sem segunda operação no Admin |

### 4.2 Invariantes sem error budget

1. Uma intenção aceita tem no máximo um pedido e os efeitos financeiros correspondentes; mesma chave com payload diferente conflita.
2. Terminal/turno vêm de contexto confiável validado; body não pode trocar gaveta silenciosamente. Modo remoto autorizado é capability distinta, se aprovado.
3. `money_q` é inteiro em centavos, quantidades seguem unidade/precisão canônica. NaN, infinito, truncamento parcial, sinal indevido e enum desconhecido são rejeitados, nunca convertidos em operação válida.
4. Preço/desconto/frete/total/recebido/troco da revisão aceita coincidem com o resultado canônico, ou a venda exige nova revisão explícita.
5. Receita por meio é Payman; dinheiro físico é Cashman. COD não entra na gaveta antes da liquidação. Cancelamento não implica devolução concluída.
6. Caixa fechado não aceita novo movimento ordinário. Corrida com fechamento tem um resultado serializável; correção posterior usa mecanismo gerencial auditado, sem editar Entry antiga.
7. Fechamento do turno e fechamento do dia são processos distintos. Contagem permanece cega no endpoint, HTML/SSR, cache, relatório e export acessíveis ao contador.
8. Comanda não é uma cópia local de pedido. Nenhuma edição obsoleta sobrescreve outra sem conflito; transferir/dividir conserva linhas/quantidades e vínculo de cozinha.
9. Falha de impressora, fiscal ou refresh não desfaz venda confirmada nem cria autorização para repeti-la. Unknown não equivale a falhou.
10. Offline é leitura/rascunho seguro: sem pedido local, captura local, caixa local ou replay automático de efeitos. ADR-013 continua vigente.
11. Troca de operador não carrega PIN, autorização ou PII privada da pessoa anterior. Um rascunho compartilhável exige vínculo explícito à comanda e nova autorização.
12. O display do cliente nunca autoriza mutação nem exibe PIN, telefone/email completo, CPF, token ou histórico administrativo.

### 4.3 Fora do escopo automático

Commit offline; gateway/TEF novo; cobrança autônoma; política fiscal nova; crédito/limites de conta novos; gestão profunda de clientes; BI; novo scheduler de produção; sugestão de troco baseada em estoque de cédulas não medido; monitor remoto público; redesign geral de todos os Nuxt. Registrar discovery separado se necessário. Correções mínimas nos owners para garantir a jornada estão no escopo, coordenadas com seus responsáveis.

## 5. Gates humanos

Gate não é caixa de seleção preenchida pelo executor. Registrar decisor, data, alternativa escolhida, escopo, evidência e eventuais condições. Não interpretar aprovação de um plano anterior como aprovação de política nova.

| Gate | Decisão/decisor | Bloqueia | Preparação segura anterior |
|---|---|---|---|
| G-01 Base e integração | responsável do repositório: base aceita e owners de hotspots quando houver dependência paralela | integrar trabalho de outra sessão ou editar hotspot disputado | diff, mapa de colisões, testes em isolamento |
| G-02 Estação e autoridade | proprietário/Ops + Segurança: presencial/remoto, múltiplos cookies, terminal único legado, personas e segunda assinatura | mudar enforcement de identidade/terminal e exceção remota | matriz proposta, testes de mismatch/negação, relatório de compatibilidade |
| G-03 Dinheiro e fechamento | proprietário/Financeiro + Ops: split/troco, cartão externo, conta, COD, bloqueios reais do fechamento e destino de pending | mudar política de recebimento, liberação ou fechamento | invariantes existentes, simulação e proposta de casos |
| G-04 Hardware | Ops/owner da estação: aparelho, SO, navegador, capacidade de sensor, fallback, critérios de reimpressão/abertura | instalação, acionamento real, mudança da política advisory/bloqueante | fake spooler/sensor, UX/bytes, inventário e runbook |
| G-05 Dados e fiscal | owner Fiscal + Privacidade/Produto: contato/CPF só da venda versus cadastro, retenção, acesso/reenvio e contingência | alterar regra fiscal/dados ou usar pessoas/provedores reais | fixtures sintéticas, redaction, contrato e falhas simuladas |
| G-06 Experiência | Produto + operadores de balcão/gerência: roteiros, hardware primário, budgets e linguagem | aceitar UX definitiva/piloto com metas finais | protótipos, instrumentação e metas provisórias |
| G-07 Contratos e Admin | Arquitetura + owners dos cores/Admin: extensão mínima, compatibilidade, schema/migration e superfícies | novo modelo/estado de domínio ou nova superfície administrativa | proposta, alternativas e testes de consumer; preservar padrões já aceitos |
| G-08 Capacidade e operação | Ops/SRE + Produto: pico, SLO, alarmes, on-call e janela de observação | declarar pronto para piloto | carga sintética, dashboards e drills locais |
| G-09 Piloto/expansão | proprietário do ambiente + Release/Ops | cada instalação/deploy/write, recebimento real, emissão/envio e expansão | candidato revisável, comandos exatos, blast radius, rollback |

Ao parar: apresentar o fato, opções, recomendação, impacto e decisão exata necessária. Preparar a proposta concreta antes de perguntar. Não impor G-02 a uma simples correção de mensagem já exigida pelo contrato; aplicá-lo a mudança de política. Ausência de resposta nunca autoriza execução dependente.

## 6. Sequência e dependências

| WP | Prioridade | Resultado | Dependências técnicas | Gates para a parte dependente |
|---|---|---|---|---|
| WP-00 | P0 | baseline, provas, harness e inventário de tarefa | nenhuma | G-01 se base disputada; observação em G-06 |
| WP-01 | P0 | contexto confiável e autoridade fim a fim | 00 | G-02 |
| WP-02 | P0 | comando, revisão, idempotência e recuperação | 00; integração com 01 | G-07 para extensão de domínio |
| WP-03 | P0 | review/close e pagamentos sem perda de intenção | 01, 02 | G-03 |
| WP-04 | P0/P1 | comandas e cozinha concorrentes e rastreáveis | 01, 02 | G-03 se mudar política de item já produzido |
| WP-05 | P1 | Projection + Actions, errors e cliente gerado | 01–04 | G-07 |
| WP-06 | P0/P1 | resultado, pendências e recuperação no balcão | 02, 03, 05 | G-03/G-05 para política; correção de incerteza pode sair antes |
| WP-07 | P1 | cliente, catálogo, agenda e retomada sem retrabalho | 03–05 | G-05/G-06 |
| WP-08 | P1 | periféricos e display honestos, escopados | 01, 02, 05, 06 | G-04/G-05 |
| WP-09 | P1 | sessão, web security e acessibilidade | 01, 05; integração 06–08 | G-02/G-06; shared em G-01 |
| WP-10 | P1 | caixa, turno, fechamento e handoff | 01–06, 08 | G-03/G-06 |
| WP-11 | P1 | performance, CI, observabilidade, Admin/docs | 05; validação final 06–10 | G-07/G-08 |
| WP-12 | P2/rollout | ensaios, piloto, expansão e encerramento | todos anteriores | G-04/05/06/08/09 |

Ordem padrão: 00 → 01/02 → 03/04 → 05 → 06/07/08/09/10 → 11 → 12. “/” permite progresso independente, não múltiplos writers no mesmo arquivo. Baseline, arquitetura, testes de segurança e protótipos podem avançar antes de gates; domínio/UX definitivos dependentes não.

Primeira entrega útil: impedir contexto de gaveta inconsistente, preservar tender e dar certeza honesta após timeout. P0 não precisa esperar uma reforma visual completa. Descoberta de risco P0 novo entra no log com reprodução e dependências, sem expansão arbitrária de escopo.

## 7. Work packages executáveis

Todos os WPs herdam invariantes, gates e disciplina de evidência. `N/A` para migration/telemetria/teste exige justificativa concreta. Prova simulada de efeito externo deve manter esse rótulo.

### WP-00 — Baseline recente, reproduções e placar de esforço

**Problema e resultado.** Impedir retrabalho e conclusão falsa a partir de testes verdes de contratos antigos. Produzir matriz `F-ID → reprodução → alvo → teste → WP → evidência → status` e baseline operacional.

**Execução.** Instalar runtimes pelo lock em isolamento, incluindo operator-kit; identificar import real de cada pacote Python; testar regressões já corrigidas. Montar fixtures sintéticas: duas gavetas, três personas, múltiplas comandas e linhas do mesmo SKU, turno compartilhado, desconto, frete, PIX pendente, conta, COD, devolução e fiscal/print falhando. Programar clock, barreiras de concorrência e fake provider com falha antes do efeito/depois do efeito/antes da resposta. Corrigir o harness mínimo e lint preexistente com patches próprios, sem suprimir warnings genericamente. Preparar observação de turno e tarefas da seção 9.

**Paths.** Suites PDV de `shopman/backstage/tests`, `shopman/shop/tests`, `surfaces/pos-nuxt/tests`; testes Cashman/Payman/KDS, `tools/pos-counter-agent`; config de teste apenas se necessária e coordenada.

**Prova/aceite.** Cada F01–F18 classificado em reproduzido, já satisfeito ou hipótese com caso pendente; nenhuma hipótese usada como certeza. Baseline inclui SHA, ambiente, comandos, contagens, skip reason, warnings e falhas. Testes vermelhos falham na assertiva certa. Nenhuma rede externa ou hardware real. Duração, toques e passos instrumentáveis, sem gravar PII.

**Observação/migração/reversão.** Artefatos de teste e relatório, sem migration de domínio; rollback do harness não altera runtime, mas não dispensa prova equivalente. G-06 ratifica tarefas; G-01 resolve base disputada.

### WP-01 — Estação, operador, terminal e caixa dizem a mesma coisa

**Problema.** F01/F02: leitura passou a usar estação, mas venda ainda injeta turno default; alguns comandos privilegiam body. O operador pode ver um contexto e produzir efeito em outro.

**Contrato/execução.** Criar/reusar resolução canônica de runtime por request com `station_ref`, `terminal_ref`, `shift_ref`, operador e postura. Aplicar a leitura, review/close, abrir/fechar, movimento, conta, COD, refund, recibo/reprint, relatório e SSE. Verificar terminal ativo e vínculo do turno na transação do efeito. Body divergente é conflito/negação, não troca implícita. Múltiplos cookies válidos exigem resolução deliberada; jamais “primeiro cookie”. Modo remoto/multi-terminal gerencial só por capability aprovada, terminal explícito e auditoria. No modo bloqueado, projection segura mostra o reparo em vez de apresentar outro terminal como pronto.

**Paths.** `station_trust.py`, `api/operations.py`, `api/permissions.py`, `permissions.py`, `projections/pos.py`, `services/pos.py`, Cashman Terminal/Shift, `usePosTerminal`, `usePosCashSession` e `server/routes/sse/cash.ts` conforme caminho atual.

**UX.** Estação/gaveta/operador/turno visíveis sem pedir ref manual a cada ação. Conflito explica qual vínculo precisa reparo; ação abre equipamento exato no Admin autorizado. Troca de pessoa não abre outra custódia da mesma gaveta.

**Prova/aceite.** Matriz A/B: projection, venda, entrada/saída, COD, refund, recibo, contagem e relatório ficam na gaveta correta; payload A em estação B recusado; sem ref/estação, duas gavetas não são escolhidas por ordem; revogação/desativação entre GET e POST bloqueia. Testar terminal único legado conforme G-02, sem criar `Terminal.default()` ocultamente em caminhos que exigem cadastro válido. Autorização negativa via URL/API e replays passa.

**Telemetria/migração/reversão.** `runtime_mismatch`, `ambiguous_terminal`, `station_revoked` por code, sem cookie/token; relatório de estações desvinculadas antes de enforcement. Não provisionar automaticamente. Contrato aditivo primeiro; rollback pode bloquear contexto incompatível, nunca voltar a selecionar gaveta errada. G-02 aprova compatibilidade e modo remoto.

### WP-02 — Intenção estável, concorrência e resultado recuperável

**Problema.** F04–F06/F09: proteção parcial não basta para chave reutilizada com outro conteúdo, crash do receipt, edição obsoleta ou resposta perdida.

**Contrato/execução.** Inventariar claims existentes e estender o mínimo. Chave obrigatória para comandos com efeito; fingerprint canônico exclui credenciais e inclui objeto, revisões, valores, canal e runtime material. Escopo explicita ator/estação/terminal/recurso conforme operação, com retomada autorizada de turno; não expor receipt de outro operador. Mesma key+hash reproduz outcome, key+hash diferente dá conflito. Revalidar autoridade antes de entregar/reexecutar receipt. Sem gerar nova key automática após timeout.

Para dinheiro interno, provar ou tornar efeito + receipt atômicos na mesma transação; onde houver efeito externo, usar tentativa/dispatch canônicos e recuperação explícita, sem manter lock de banco durante rede. Claim órfão tem detecção e reconciliação antes de voltar a executar. Guardar resultado suficiente para recuperar após reload e após fechamento do turno, sem obrigar novo write. Propagar revisão da Session ao save/rename/move/clear/fire/close com CAS/lock e ordem de locks determinística. Reusar revisão existente no Core; extensão exige G-07.

**Paths.** `shop/services/pos.py`, `pos_intent.py`, `remote_mutations.py`, `api/operations.py`, Orderman idempotency/session, Cashman ledger, `usePosAction`, `usePosSale`, `usePosCashSession`.

**UX.** Diferenciar envio em andamento, confirmado, recusado, conflito e resultado desconhecido. “Consultar resultado” preserva chave/objeto; nunca declara “não foi fechado” apenas porque a rede falhou. Após sucesso, refresh falho mostra dados desatualizados e receipt confirmado. Conflito apresenta diferença e mantém edição local; retomar não dispara automaticamente pagamento.

**Prova/aceite.** Dois POSTs simultâneos, mesma/diferente key e payload; crash antes/depois do lançamento e da resposta; expiração do claim; retry depois de fechar turno; permissão revogada; dois atores/terminais usando mesma string de key. Nenhuma duplicação ou vazamento. Dois saves obsoletos não fazem last-write-wins; confirmar correção exige nova intenção. PostgreSQL obrigatório para alegar serialização.

**Telemetria/migração/reversão.** Contagem de replay/conflict/claim age/outcome unknown, correlação entre request e efeito. Migration aditiva somente se insuficientes campos atuais, sem apagar evidência; backfill não fabrica hash histórico. Compatibility window mantém readers e recusa writes inseguros. Não limpar in_progress nem repetir depois de TTL sem reconciliar.

### WP-03 — Total revisado e pagamento digitado sobrevivem ao commit

**Problema.** F03/F08: tender único perde informação, revisão não identifica a intenção mostrada e UI pode ficar com resposta obsoleta.

**Contrato/execução.** Distinguir tender recém-informado de pagamento já persistido; enviar valor/reference/collection explícitos quando houve entrada. Definir schema para single cash com troco e mixed sem inferir política nova. Review e close compartilham resolver de preço/promoção/desconto/frete/quantidade/meios; validação final estrita preserva avisos úteis durante edição. Review devolve fingerprint/revisão, validade e fatos de pagamento; close comprova que corresponde à revisão aceita. Resposta antiga não atualiza review nem habilita commit: epoch/abort e chave de contexto por carrinho/comanda. Alterar dados materiais invalida revisão imediatamente.

**Paths.** `posIntent.ts`, `presentation/payment.ts`, `PosPaymentWorkspace`, `usePosSale`; `shop/services/pos_intent.py`, `pos.py`, pagamentos/ofertas/entrega, API review/close, Payman.

**UX.** Valor do total, restante, recebido e troco vêm do resultado canônico; cálculo local provisório é rotulado e não autoriza fechar. Cartão manual/externo não aparenta autorização bancária inexistente. Troco sugerido não é captura; PIX com QR não é pago. Mudança real de preço/taxa mostra delta e preserva escolha/digitação, pedindo só a decisão alterada.

**Prova/aceite.** Casos cash exato/excedente/insuficiente, único PIX/cartão parcial ou excedente, mixed com COD/conta conforme política, zero, negativos, floats em campo inteiro, limites, acentos/locale, duplicação de reference e payload forjado. A cifra digitada nunca é substituída silenciosamente; revisão e pedido/Payman/Cashman/recibo coincidem ao centavo. Alterar preço, horário disponível ou carrinho durante request nunca confirma total velho. Falha de gateway não retorna dinheiro como capturado.

**Telemetria/migração/reversão.** `review_mismatch`, `stale_review_discarded`, `tender_validation`, `payment_unknown` por códigos. Versionar intent/client sem duplicar pricing; preservar leitura histórica. Rollback mantém validação corrigida e reader compatível; G-03 decide excedente/mixed/cartão externo, nunca o frontend.

### WP-04 — Comandas, linhas e cozinha sem ambiguidade

**Problema.** F06/F14: locks internos não compõem automaticamente save, fire, move, cancel e fechamento; pedido “mais um” não pode reaparecer como duplicação da linha anterior.

**Contrato/execução.** Conservar `line_id` e identidade de Session; versão para comando completo. Save monta delta sob leitura/trava atual e não substitui `Session.data` obsoleta. Fire seleciona linhas por identidade e revisiona o efeito completo; ledger KDS continua autoridade. Cancel/unfire/refire tem semântica explícita por ocorrência, sem confundir retransmissão com solicitação nova. Move/split trava origem/destino em ordem determinística, conserva quantidades, notas, descontos e vínculos; falha não deixa comanda vazia órfã. Cozinha indisponível/sem roteamento vira impedimento/pendência explicada conforme contrato, não selo de enviado.

**Paths.** POS services, Orderman session operations, `shop/services/kds.py`, adapters KDS, `usePosSale`, `PosTabBoard`, `PosMoveLinesDialog`, `presentation/moveLines.ts`, `kitchen.ts`, `/tickets` e `usePosOrderTickets`.

**UX.** Comanda indica salvo/salvando/não salvo e origem do conflito. Enviar à cozinha mostra exatamente o delta. Dividir/transferir já traz origem, destino, quantidades e resultado; item enviado ou produzido recebe tratamento explicado. Retirada/entrega marcada no ticket não vira regra duplicada no PDV.

**Prova/aceite.** Save×fire, fire×fire, save×close, move A→B×B→A, cancel×fire, refire após cancel, SKU repetido em linhas distintas, observação editada e produto sem estação. Conservação e no máximo um ticket lógico por ocorrência; mirrors convergem ao ledger sem apagar metadata concorrente. Rascunho não pode ser marcado salvo por resposta referente à versão anterior.

**Telemetria/migração/reversão.** Reconciliation mismatch, ticket delta, command conflict, orphan tab, unsaved age. Reusar reconcilers existentes; não gerar tickets históricos para “corrigir” contagem. Compatibilizar schema de linhas e revisões; rollback mantém ledger/identidades e pausa operação incompatível. Política de descarte após produção vai a G-03.

### WP-05 — Projection + Actions completas e contrato gerado

**Problema.** F07: enums gerados coexistem com Actions/tipos manuais e fallbacks que fazem UI inventar rota quando o contrato não ofereceu comando.

**Contrato/execução.** Ampliar gerador atual para inputs, responses, errors, Actions, capabilities e versões; não editar TS gerado à mão. Resolver ação por usuário/runtime/revisão/readiness. Transportar fatos puros, refs, enums e chaves semânticas; apresentação/copy configurada respeita ADR-014. Remover fallback de mutação crítica; ausência/enum desconhecido rende estado seguro e diagnósticos. BFF conserva status, correlação, versão e metadados allowlisted. Paginar listas/tickets/histórico onde necessário, mantendo filtro e contexto. SSE invalida, refetch é verdade.

**Paths.** `backstage/contracts.py`, `projections/pos.py`, API, `export_pos_schema.py`, `app/generated/posContract.ts`, tipos, `posIntent.ts`, presentation/actions e composables; contratos compartilhados coordenados.

**Prova/aceite.** Gerar em temporário e comparar; missing/disabled Action nunca chama POST; método/rota/schema de UI correspondem ao servidor; backend reautoriza comando forjado; scopes de counts e recursos não vazam. Golden cases de 401/403/409/validation/429/5xx/degraded/unknown. Snapshot de apresentação separado do dado.

**Telemetria/migração/reversão.** Contract mismatch, action missing, unknown enum, projection age/bytes/queries. Evolução aditiva e política de compatibilidade real dos consumers; remover legado após uso zero. Nomes v2 são proposta, não obrigação de reescrever API inteira. G-07 decide extensão mínima; rollback conserva writers corrigidos.

### WP-06 — Venda concluída, pendências e recuperação no mesmo contexto

**Problema.** F09/F10/F13/F17: toast ou uma única ref em memória não provam continuidade de PIX/fiscal/print nem resultado após perda de resposta.

**Contrato/execução.** Produzir leitura canônica por pedido/tentativa com eixos independentes: commit comercial, pagamento, efeito de caixa, cozinha/fulfillment, fiscal, entrega de comprovante e jobs físicos. Reusar Payman, Cashman, Directives e estados de fiscal/KDS; não criar ledger concorrente. Disponibilizar fila operacional das pendências autorizadas de estação/turno, recuperável após reload. Buscar resultado pelo receipt antes de oferecer reenviar. Retry é por efeito elegível, nunca a venda inteira. Sessão expirada reautentica e consulta; não autosubmete.

**Paths.** POS close/status/receipt/recent APIs e projections, serviços de pagamento/fiscal/notification, `usePosSale`, `PosSaleResult`, `PosPaymentResult`, `PosRecentSales`, páginas venda/tickets/sessão.

**UX.** O comum termina com total, meio, troco e próxima venda disponíveis. Pendência acompanha o pedido em área persistente, sem cobrir todo o balcão nem sumir com o próximo cliente. Ação “Consultar PIX deste pedido”, “Reimprimir este comprovante” ou “Ver falha da nota” abre alvo exato. Cancelar pedido e devolver dinheiro são passos diferentes com resultado declarado. Handoff de pending tem owner e prazo.

**Prova/aceite.** Duas ou mais vendas PIX pendentes, reload, pagamento tardio/expirado/cancelado e webhook duplicado; fiscal recusado/unknown e email falho; resposta de close perdida; refresh falho após close confirmado; replay retorna recibo do pedido original. Pagamento confirmado não regride com resposta antiga. Sem recobrança/revenda automática; cancelamento/refund mantém valores e vínculos corretos. Budgets R01/R06/R07/R10 atendidos ou pendentes de G-06, nunca inventados.

**Telemetria/migração/reversão.** Idade de pending por estágio, owner ausente, recovery outcome, retry impedido e receipt consultado. Views agregam dados atuais; persistência nova só para evidência que ainda falta, com G-07. Rollback deixa pendências consultáveis e pausa novos efeitos incompatíveis. G-03/G-05 decidem contingências e reenvio.

### WP-07 — Cliente, catálogo e agenda sem redigitação ou troca silenciosa

**Problema.** F11/F17: busca falha pode parecer inexistência e nova resposta pode pertencer ao cliente anterior; continuidade da jornada precisa cobrir identidade/contato/agenda recentes.

**Contrato/execução.** Busca tipada com abort/epoch, loading/zero/degraded separados e seleção explícita. Identidade atual não muda por preencher CPF/email só da nota. Preservar escolhas de salvar contato e resolução de conflito já implementadas, revendo permissão e revisão quando necessário. Endereço salvo preenche campos, geocoding mantém proveniência/confiança e entrada manual se indisponível; não faz promise de entrega por estimativa local. Agenda, taxa, disponibilidade e prazo vêm do owner canônico; virada de data usa timezone da loja. Catálogo mantém busca, filtro e scroll durante refetch, sem ressuscitar disponibilidade antiga.

**Paths.** `PosCustomerModal`, `PosCustomerSearch`, `PosReceiptSaveOffer`, `PosFulfillmentModal`, `PosScheduleModal`, product grid/cart, presentation/customerDecision/receiptContact/schedule, `usePosSale`, API de cliente, Guestman e serviço de fulfillment.

**UX.** Venda anônima comum não força cadastro. Selecionar recorrente reaproveita dados pertinentes; pergunta apenas o ausente. Conflito traz quem está selecionado, dado proposto e ações válidas; não exige abrir cadastro externo para decidir o que já foi resolvido. Campos conservam entrada segura em erro; nunca persistir PIN/token no draft.

**Prova/aceite.** Busca A lenta/B rápida, falha, resultado vazio verdadeiro, homônimos, cliente sem telefone, nota para outro CPF/email sem gravar cadastro, autorização de alteração, geocode indisponível, prazo vencendo, meia-noite, item esgotado após seleção, quantidade decimal só quando unidade permite. Matriz de rascunho: refresh, rede, logout, operador diferente, comanda compartilhada e retenção. Nenhuma troca de identidade implícita. Budgets R02/R08/R09.

**Telemetria/migração/reversão.** Search degraded/stale discard, re-entry count agregado, conflict outcome, draft restore. G-05 aprova retenção/escopo de draft; preferência por refs e storage mínimo. Não cachear CPF/contato em storage global. Migração aditiva de draft versionado se necessário; versão incompatível oferece recuperação segura, sem reexecutar venda.

### WP-08 — Impressão, gaveta, scanner e display com prova real

**Problema.** F12/F13 e fronteiras físicas: a aceitação de um job não prova impressão, e um canal global pode misturar terminais. Há hardware implementado; falta provar a jornada inteira no equipamento autorizado.

**Contrato/execução.** Reusar counter-agent e recibos servidor. Definir `configured`, `reachable`, `job_accepted`, `device_reported`, `operator_verified`, `unknown/failed` somente quando há fonte correspondente. Jobs têm ref/hash/escopo e tentativa; retry não presume ausência de efeito depois de timeout. Reimpressão é novo ato auditado do mesmo documento, rotulado, sem novo pagamento/fiscal. Pulso de gaveta não depende de impressão e não altera saldo sozinho; sensor unknown não vira closed. Preservar política atual de trava/advisory até G-04.

Escopar BroadcastChannel e handshake ao terminal/publisher/instância de tela autorizada, com versão, sequence e expiry. Evitar múltiplos publishers disputar display; modo sem suporte explica indisponibilidade. Limpar conteúdo no abandono, troca de operador e expiração; não inferir identidade por nome de canal. Separar shell do display de fetches/auto-lock de operador. Scanner diferencia identidade, produto e digitação humana; Enter do leitor não aciona cobrança nem aprovação indevida.

**Paths.** `tools/pos-counter-agent`, `services/pos_hardware.py`, `pos_terminal.py`, `receipt_escpos.py`, APIs de recibo/DANFE, `useCounterAgent`, `useDrawerLock`, `useDrawerIdleWatch`, `useAgentHealth`, `useCustomerDisplay`, `PosDisplayPublisher`, `/display`, print CSS/geometry, scanner compartilhado.

**Prova/aceite.** Fake spooler rejeitado, job aceito/resposta perdida, papel ausente, sensor stale/invertido/unknown, agente antigo/fora do ar, duas chamadas iguais, CORS/origin/token incorretos, limites de bytes e SSRF de URL/config. Dois publishers/terminais e reconexão de display não misturam dados. Recibo browser/ESC-POS conferem itens/descontos/frete/total/troco canônicos em 58/80 mm se suportados. No aparelho: papel curto/longo, acentos, QR quando pertinente, corte, régua, abertura e sensor, assinatura de operador. Fake não encerra G-04.

**Telemetria/migração/reversão.** Job outcome/age/version/capability, probe freshness, reprint reason, display stale/publisher conflict; sem token ou conteúdo de nota. Compatibilidade agent/client explícita e instalador verificável; flag preserva caminho comprovado. Fallback manual só conforme política, visível/auditado. Nenhuma instalação/acionamento real antes de G-09.

### WP-09 — Sessão segura, erros honestos e operação acessível

**Problema.** F18 e experiência transversal: overlay, sessão, rascunho e pedidos em andamento precisam contar a mesma história; headers herdados não são prova no host.

**Contrato/execução.** Mapear checking/anonymous/locked/authenticated/expired/forbidden/unsupported/offline por rota; evitar conteúdo protegido interativo sob gate. 401, 403 permissão e `station_locked` têm recuperações diferentes. Auto-lock/hold de pagamento respeita política de segurança e não prolonga privilégio indefinidamente; retomada preserva contexto seguro com reautorização. BFF/API/HTML/erro/SSE têm cache privado, CSRF/origin, headers e limites testados. Tokens do agente permanecem restritos à função local aprovada e não aparecem em display, logs ou exports. Validar headers reais somente em etapa autorizada de rollout; fonte `provider: google` em build não prova request de terceiro no browser.

**Paths.** `app.vue`, pages, login/OperatorLock/OperatorManagerAuth do kit, `usePosAction`, `usePosTerminal`, session/connectivity/identity capture, BFF/Nitro/config e telemetria shared.

**UX/prova.** Matriz da seção 10: teclado e leitor, foco inicial/restaurado, fundo inert, atalhos sem roubar digitação, touch ≥44 px, ações frequentes 48–56 px onde cabe, safe area/teclado virtual, 200% zoom, cores/ícones/texto, reduced motion e nomes longos. Sem toast como única evidência. Ataques API: CSRF, recurso alheio, permissão revogada, receipt replay cross-user, URL maliciosa e cache de outra sessão. `axe` sem serious/critical e roteiro manual aprovado.

**Telemetria/migração/reversão.** Session recovery, denied action, stale context, CSP violation sanitizada. Mudança no kit exige consumers impactados e owner de G-01; pode implementar local quando específico do PDV. Headers devem ser compatíveis com dependências reais; rollout report-only de diretiva quando necessário, sem relaxar autenticação. G-02 aprova eventual mudança de lock; G-06 aceita geometria.

### WP-10 — Caixa, fechamento cego e passagem de turno

**Problema.** Mesmo com ledger correto, operador não deve conciliar manualmente estado de venda, custódia, troco, devolução e fechamento do dia. Fechamento não pode revelar esperado nem abandonar efeito monetário desconhecido.

**Contrato/execução.** Reusar um writer Cashman para abrir, movimento, troco, refund e contagem. Garantir request id, fingerprint, runtime e autoridade da fatia anterior. Projetar bloqueios/avisos por tipo de pendência: dinheiro desconhecido exige reconciliação; print falho não deve automaticamente bloquear custódia sem regra aprovada; fiscal e cozinha têm owners próprios. Resolver corrida close×sale/movement/refund/COD sob lock do turno. Dia tem seu contrato de estoque/produção e não fecha gaveta por coincidência de data. Inventory closing rejeita quantidade inválida, stale e período incorreto; não transforma erro em zero. Reusar evolução recente de fechamento/Produção.

**Paths.** Cashman, `services/pos.py`, cash projections/APIs, `usePosCashSession`, `useDayClosing`, `useCashReport`, `session/index.vue`, `session/closing.vue`, `session/report.vue`, testes de day closing e integração com Produção.

**UX.** Suprimento não pergunta informação sem alternativa; sangria pede valor, motivo e aprovação efetiva. Pedido de troco não é retirada; mostra status/destinatário/atendimento. Contagem por denominação ajuda sem revelar esperado; não sugerir composição de troco a partir de inventário inexistente. Fechar mostra o que foi contado, custódia encerrada e pendências transferidas. Próximo turno recebe resumo por responsável com deep-links exatos, sem copiar planilha/WhatsApp.

**Prova/aceite.** Abertura negativa/typo, dia virando, segunda pessoa mesma gaveta, duas gavetas, count repetido, cashout/refund concorrentes, COD já liquidado, conta parcialmente quitada, pendência unknown, print pendente. Contador não vê saldo/esperado/diferença via API/SSR/relatório/export; auditor só com capability. Preservar políticas de gerência/segunda assinatura atuais. Reconciliação Payman×Cashman passa sem lançamento duplicado ou atribuição errada.

**Telemetria/migração/reversão.** Closure blocked reason, pending transferred, reconciliation mismatch, time-to-close e esforço observado. Não alterar Entry histórica, não reexecutar backfill Cashman antigo. Novas evidências são aditivas; legacy incompleto é marcado, não inventado. G-03 assina política de bloqueio e handoff; rollback preserva contagens/eventos.

### WP-11 — Provar, observar, documentar e manter um único Admin

**Resultado.** Pipeline confiável, SLO medido, diagnóstico acionável e documentação fiel. Não acumular aqui todos os testes/telemetria: cada WP anterior entrega os seus; aqui ocorre prova integrada.

**Execução.** Integrar suite real Django+BFF+Nuxt+DB de teste, dois browser contexts e fake providers; manter mocks para matriz visual, com finalidade explícita. Completar schema drift, lint/type/build, a11y, testes de segurança, carga e falhas. Medir queries/payload/projeção, separar dependências lentas, limitar listas/histórico e pausar polling oculto sem perder reconciliação ao retorno. Telemetria liga receipt→Order→Payment→Entry→ticket→fiscal/job, com cardinalidade limitada. Health distingue processo, API/DB, stream e agente da estação.

Admin: inventariar modelos realmente registrados; configurar Terminal/agent/perfis autorizados em Unfold existente; auditoria liga turno/pedido/tentativa/segunda assinatura de modo read-only. Não criar cockpit de venda no Admin nem tela de ajuste histórico no PDV. Alteração necessária usa skill/cânones e `make admin`. Atualizar spec (custódia por gaveta, pagamento de todos os métodos), contrato, README com rotas reais, offline, setup/testes e níveis de prova física.

**Paths.** CI de surfaces/runtime, testes e scripts dedicados PDV, `operator-kit`, API/projections, Cashman Admin/Backstage POS Admin, docs de referência e runbooks; migrations/lockfile só por necessidade real coordenada.

**Aceite.** Gates da seção 11 passam no SHA final integrado; nenhum warning estrutural escondido; query/latency/memory/lock budgets medidos; scanner de segredos/PII em sucesso/falha; drill feito por pessoa não autora; docs descrevem código e artefatos reais. Dashboard aponta ação e owner, não BI genérico. G-08 aprova objetivos finais.

**Migração/reversão.** Instrumentar antes de otimizar; índices/backfills ensaiados e resumíveis; configs de alerta inicialmente em teste até calibradas. Rollback mantém evidência e guards financeiros. Admin pode voltar a read-only; não restabelecer dupla escrita.

### WP-12 — Ensaio de balcão, piloto e convergência

**Entrada.** WPs técnicos e gates de política completos; documentação, rollback, hardware e on-call preparados. Sem P0/P1 necessário aberto. Exceção de escopo tem justificativa/owner, sem dispensar invariante.

**Execução.** Candidato sintético integrado → ensaio em equipamento autorizado → uma estação/equipe → turno e troca de operador → expansão por estações autorizadas. Observar pico, interrupção e fechamento; repetir tarefas/budgets antes/depois. Não dividir clientes aleatoriamente entre dois writers da mesma gaveta. Cada estágio recebe G-09 específico e preserva compatibilidade.

**Aceite.** Zero duplicação, dinheiro no terminal errado, captura falsa, vazamento de contagem cega ou perda silenciosa; pendências reconciliadas com owner; metas de esforço e SLO ratificadas; validação do hardware real documentada; sete dias operacionais após expansão, ou janela mais exigente definida por G-08. Assinar go/no-go por estágio.

**Observação/reversão.** Freeze de novos efeitos perigosos quando integridade desconhecida, consulta/reconciliação continuam. Reverter UI compatível sem apagar receipts/events nem reabrir guard inseguro; forward-fix preferencial para schema. Não reenviar unknown, não recapturar nem reemitir nota para “recuperar”. Finalização exige DoD, não apenas imagem antiga no ar.

## 8. Contratos de comando, resultado e recuperação

Nomes abaixo são proposta semântica a adaptar ao contrato existente em G-07. Não criar entidades novas só para reproduzir estes exemplos.

### 8.1 Envelope operacional

```text
POSContext
  contract_version, generated_at, source_revision, fresh_until
  runtime: station_ref, terminal_ref, shift_ref, operator_ref, posture
  freshness: fresh | stale | degraded | unavailable
  facts / relationships / action list / safe recovery

Action
  ref, kind, label_key, priority, enabled, reason_code
  method, href, payload_schema, resource_ref, expected_revision
  idempotency_requirement, confirmation, approval_requirement

Command
  client_request_id, expected_revision, reviewed_intent_ref/hash (quando aplica)
  payload tipado; ator/estação/turno resolvidos/revalidados no servidor

Receipt
  ref, outcome, resource_ref, resulting_revision, accepted_at/completed_at
  effect_refs, recovery_actions, replayed
```

Não pôr PIN/crachá bruto no fingerprint, log ou receipt; vincular aprovação verificada à ação/intenção/valor e expiração. Mudança material requer reaprovação. Fatos conhecidos podem ser reaproveitados na retomada; permissão sempre revalidada.

### 8.2 Eixos de resultado

| Eixo | Exemplos de fatos | O que não prova |
|---|---|---|
| Comercial | pedido ref criado/recusado, versão | dinheiro capturado ou cozinha pronta |
| Pagamento | pending, captured, rejected, refunded, unknown conforme Payman | QR criado não prova pagamento; declaração externa não prova gateway |
| Caixa | Entry ref por shift, valor assinado, count/refund | gaveta abriu fisicamente |
| Cozinha | ticket/linha/ocorrência, pendente/enviado/produzido/cancelado | envio não prova preparação nem entrega |
| Fiscal | solicitação, autorização/rejeição/unknown, documento ref | pedido criado não prova autorização fiscal |
| Comprovante | canal, job/ref, aceito/falhou/unknown/confirmado se houver evidência | spooler aceitou não prova papel/email recebido |

“Sucesso parcial” não é novo status do pedido: é composição de fatos desses owners, com próxima ação. Receipt não pode congelar para sempre estado externo que evolui; manter referência e refetch canônico.

### 8.3 Erros e alertas

Preservar HTTP e códigos existentes quando válidos; normalizar campos `code`, `field_errors`, `request_id`, `current_revision`, `retryability`, `actions`. Distinguir 401 (sessão), 403 (autoridade/lock com code), 409 (conflito), validação 400/422 conforme convenção, 429 e falha de dependência 5xx. Não mapear exception arbitrária a erro do operador nem expor traceback/vendor body.

Um alerta operacional tem fonte/ref/revisão, gravidade, owner, prazo, lifecycle, ação primária e impedimento explicado. `seen` não resolve; `acknowledged` assume responsabilidade; `resolved` exige fonte confirmada. Reusar infraestrutura de alertas/pendências existente. Não levar toda confirmação ao sino.

| Condição | Providência no contexto | Critério de resolução |
|---|---|---|
| Resultado do close desconhecido | consultar receipt desta tentativa | pedido/ausência de efeito provados |
| PIX aguardando | consultar/reconciliar este pagamento | fonte canônica settle/expiry; nunca relógio local sozinho |
| Autosave falhou/conflitou | retomar/diff da comanda exata | versão salva confirmada |
| Nota recusada | abrir erro e reparo autorizado desse documento | fiscal confirma resultado |
| Print unknown | consultar job; reimprimir conscientemente se permitido | evidência de job/ato, sem fingir papel confirmado |
| Caixa/estação divergentes | corrigir vínculo autorizado | runtime revalidado |
| Pendência de troco/refund | atender ou escalar objeto exato | lançamento/estado canônico final |

## 9. Budgets operacionais e prova de omotenashi

**Protocolo.** Observar ao menos um turno com pico, troca de operador e fechamento; incluir balcão e gerência. Fazer antes/depois com mesmas tarefas/dataset/equipamento, pelo menos 20 repetições instrumentadas das tarefas comuns e participação de 3–5 operadores, ou todos se a equipe for menor. Amostra pequena é rotulada exploratória; tempos totais com gente são relatados por distribuição e erros, não apresentados como p95 confiável de produção.

Separar tempo de ação humana, latência do sistema, espera de cliente/provedor e recovery. Contar todos os cliques/toques, inclusive confirmação, foco/abertura de modal; registrar scrolls e mudanças de tela separadamente. Quantidade de caracteres não equivale a esforço: medir campos redigitados e origem do dado. Não excluir exceções para melhorar média.

Metas abaixo são **provisórias de desenho**, ratificadas em G-06. Caso comum inicia com tela carregada, contexto válido e sem exceção. Espera acima de 300 ms recebe feedback; em 2 s informa estado e saída segura, sem spinner indefinido.

| ID/tarefa | Budget de interação | Digitação/navegação | Espera local inicial | Prova de certeza/recuperação |
|---|---|---|---|---|
| R01 Venda direta de 1 item conhecido, cash exato | ≤4 ações desde selecionar item até confirmar | 0 campos, sem cadastro/comanda obrigatórios; checkout no mesmo fluxo | review p95 ≤500 ms; receipt ≤1 s | pedido, valor, método e troco persistentes; sem conferência externa |
| R02 Cliente recorrente/último endereço | ≤3 ações após informar critério de busca | 1 critério, 0 campos conhecidos redigitados; ≤1 painel | busca p95 ≤500 ms | identidade escolhida, endereço/taxa/prazo canônicos |
| R03 Retomar comanda e adicionar/enviar item | ≤4 ações após localizar comanda | 0 contexto redigitado; 0 rota externa | saved ack ≤1 s; fire ack ≤1 s | versão salva e delta cozinha explícitos |
| R04 Dividir/transferir linhas | selecionar linhas/destino + ≤2 ações de revisão/confirmação | quantidade só se parcial; um painel | receipt ≤1 s | antes/depois conserva linhas e tickets |
| R05 Pagamento misto de 2 meios | ≤6 ações incluindo revisão/confirmação, fora digitação do valor | digitar só primeiro valor quando segundo é restante válido | revisão ≤500 ms após debounce | soma, restante, collection e troco sem memória |
| R06 Retomar close com resposta perdida | ≤2 ações após reconexão/auth | 0 reconstrução de carrinho/valor; 0 consulta manual | consulta receipt ≤1 s | confirmado/recusado/unknown com próximo passo; sem recobrar |
| R07 Tratar pendência PIX/fiscal/print | ≤3 ações para consulta/reparo elegível | 0 refs copiadas/redigitadas; ≤1 painel exato | feedback ≤300 ms; externo separado | estado de cada efeito e owner, mesmo após próximo cliente |
| R08 Agendar retirada/entrega recorrente | ≤5 escolhas incluindo confirmar, fora endereço novo | dados conhecidos preenchidos; sem calendário externo | slots/taxa ≤1 s ou pending explícito | data/horário/timezone e promise validados |
| R09 Nota em CPF/email só da venda | selecionar intenção + campo + ≤1 decisão adicional se conflito | só dado novo; não exigir cadastro | validação local imediata | nota pretendida preservada e cadastro só muda por escolha |
| R10 Sangria | abrir ação, informar valor/motivo, aprovação + confirmar | valor/motivo apenas; terminal/turno automáticos | receipt ≤1 s; hardware separado | Entry, aprovador e comprovante/pendência no contexto |
| R11 Pedir troco conhecido | ≤3 ações + quantidade se pertinente | sem procurar gerente/ref de turno | receipt ≤1 s | pedido enviado/owner/status; sem simular entrada de dinheiro |
| R12 Fechar turno | uma superfície de contagem + revisão/confirmação; ≤2 navegações | contar uma vez; não copiar totais entre telas | blockers ≤1 s; count receipt ≤1 s | contagem cega persistida e custódia/pendências explícitas |
| R13 Trocar operador/retomar trabalho | identificar + ≤1 escolha contextual | credencial pelo método aprovado, sem redigitar comanda | retorno ≤1 s após auth | ator novo, sem aprovação herdada; draft acessível só se permitido |
| R14 Handoff | ≤2 ações para abrir resumo e assumir item | 0 compilação manual | resumo ≤1 s | cada pendência com objeto, responsável e ação |

**Ganho exigido.** Para fluxos que excedem budget na baseline, reduzir pelo menos 30% de ações desnecessárias ou tempo de sistema controlável, sem aumentar erro; para fluxos já curtos, preservar desempenho e eliminar falhas de recuperação. Percentual é proposta a ratificar, não substituir orçamento absoluto. Em todos: zero redigitação de fatos conhecidos; zero consulta externa para o caso comum; zero “não sei se cobrou” escondido. Dependência externa realmente incerta é exibida e escalada, não apagada para satisfazer a meta.

Evidência por roteiro: baseline/after, SHA, dispositivo, cenário, ações, digitação, telas, tempos, erros, dúvidas e resposta do operador ao que aconteceu. Preferência estética não aprova piloto com mais retrabalho. Exceção justificada precisa de G-06; segunda assinatura e autorização não contam como desperdício removível.

## 10. Matriz de UI, estados e acessibilidade

Primários propostos: terminal 1366×768, desktop 1440×900 e tablet 1024×768/768×1024. Display: 1366×768/1920×1080 conforme hardware. Mobile 390×844 é secundário para consulta/apoio, com 320 px e zoom 200% para reflow; não prometer operação completa no menor viewport sem G-06. Light-first; dark e reduced motion onde suportados, sem regressão de contraste/foco.

| Rota/fluxo real | Estados/casos obrigatórios | Critério de interação e prova |
|---|---|---|
| Shell/login/lock | checking, locked, expired, forbidden, revoked, wrong credential, rate limit, backend down | nenhum fundo interativo; foco/Enter/scanner corretos; contexto preservado sem privilégio herdado |
| `/` catálogo/carrinho | loading, vazio real/filtrado, sold out, nome longo, linhas mesmo SKU, desconto, autosave erro/conflito | quantidade/unidade/preço legíveis; seleção estável; teclas fora de input não roubam foco |
| Checkout em `/` | reviewing, changed total, partial tender, mixed, cash change, PIX, account, COD, approval, receipt unknown | dinheiro domina leitura; bloquear só pelo impedimento correto; review não é spinner eterno |
| Cliente/comprovante/agenda | homônimos, sem fone, dado só da nota, identidade conflitante, geocode down, slots mudando | error junto ao campo; entrada mantida; nada de cadastro implícito |
| Comanda/move/fire | nova/direta, salva/não salva, outra estação, produzido, origem/destino inválidos | delta/impacto antes de confirmar, linha exata, nenhuma escolha por primeiro item |
| `/tickets` | pendente, pronto, pago/não pago, retirada/entrega, vazio, filtro, stale, cancelado | não confundir cozinha com pagamento; próximo passo autorizado, link exato ao pedido |
| `/session` | caixa fechado/aberto, terminal inválido, movimento, troco, conta, refund, outra pessoa, receipt pending | runtime visível; dinheiro não sai sem aprovação; pendência não vira sucesso total |
| `/session/closing` | contagem, produção pendente, validação, concurrency, data virada, já fechado | fechar dia ≠ turno; preservar input; não mostrar esperado por engano |
| `/session/report` | role denial, nenhum evento, muitos eventos, filtros, export, print | sigilo da contagem/esperado conforme persona; paginação estável |
| `/display` | idle, sale, payment, result, publisher perdido/duplicado, versão inválida | somente dados de cliente permitidos, TTL/limpeza, sem login/auto-lock side effect |
| Print/agent | sem configuração, desconectado, antigo, job accepted, failed, unknown, reprint | mensagem baseada na evidência; 58/80 mm sem clipping/página vazia indevida |

Aplicar teclado, leitor de tela, foco/restauração, Escape, modal/dialog nomeado, toque mínimo 44×44, ação comum 48–56 quando definido, texto ampliado e teclado virtual. Sem truncar dinheiro, unidade, estado, consequência ou ação primária. Alvo e foco nunca dependem de tooltip ou apenas de cor; animação não atrasa cobrança.

Screenshots `rota__estado__viewport__tema.png` com fixtures/clock fixos e sem dados reais; before/after/diff revisados. Visual mock prova layout, não domínio. Não atualizar goldens em massa. Erros de validade, loading, offline, session-expired, stale, conflict e unknown entram nos fluxos críticos em browser real com backend de teste.

## 11. Testes, SLO e observabilidade

### 11.1 Gates por camada

| Camada | Gate mínimo | Evidência que não substitui |
|---|---|---|
| Domínio/API | suites POS/Cashman/Payman/KDS/cliente/fiscal afetadas; negativos e invariantes | mock de composable não prova dinheiro |
| Concorrência | PostgreSQL isolado, conexões separadas, barreiras determinísticas, resultado e ledger inspecionados | SQLite não prova `select_for_update` |
| Contrato | gerador `export_pos_schema --check` ou sucessor, snapshot/compat, Action parity | TS manual não prova schema |
| Frontend | `npm ci` PDV e kit, `npm test`, lint, typecheck, build; zero warning estrutural não triado | suppress console não é correção |
| Browser integrado | Django semeado+BFF+Nuxt+DB/fakes, dois contexts, jornada completa | mock backend é só guard/layout |
| Segurança | RBAC/runtime/CSRF/IDOR/replay/PII/cache/headers/origin/agent limites | UI esconder botão não é gate |
| Visual/a11y | matriz seção 10, axe+teclado/leitor/zoom/touch e revisão de screenshots | axe verde sozinho não comprova AA |
| Hardware | simulador em CI; aparelho e SO autorizados em G-04/G-09 | bytes/spool aceito não provam papel/gaveta |
| Admin/shared | `make admin` integral se Admin mudar; consumers reais do kit se shared mudar | gate scoped isolado não encerra integração |
| Runtime integrado | CI/runtime do projeto em PostgreSQL/Redis isolados com suites pertinentes | teste com skip do invariante não conta |

Executar focados após cada fatia; ampliar só por impacto. No candidato final, todas as camadas pertinentes. Script/teste proposto deve existir e passar antes de ser registrado como comando aprovado. Não rodar seed, migrations ou cleanup contra banco compartilhado. Portas, DB, Redis namespace e artefatos de browser pertencem à sessão; não usar `reuseExistingServer` para anexar a servidor de terceiro sem identificação.

### 11.2 Matriz adversarial mínima

- Dois terminais, dois operadores e body de terminal trocado; cookie antigo/revogado/múltiplo; replay entre personas.
- Cash sale/close/refund/movement/COD concorrentes; stock/fiscal/notification falhando depois do commit; exceção na gravação do receipt.
- Timeout antes do efeito, após efeito e após resposta; worker/processo morto; claim expira; cliente reloga e consulta.
- Uma key com payload diverso, key ausente, key repetida por outro recurso, key igual após turno fechado; nenhum retry silencioso perigoso.
- Review velha chega após carrinho/endereço/data atual; preço muda entre review/close; tender único preservado; amounts extremos/locale/unidade.
- Save/fire/move/clear/close concorrentes, mesma linha e SKU repetido; conservações de tickets/quantidade.
- PIX múltiplo e callback tardio/duplicado; cancel/refund disputa com pagamento; external card não aparenta gateway.
- CPF/email da nota não reescreve cadastro; erro de busca não cria cliente falso; PII não atravessa display/logs.
- Poll/SSE cai, browser fica oculto, tablet dorme, meia-noite/timezone, auth expira e outro operador entra.
- Spooler falha/aceita e perde resposta; agente antigo; sensor stale; display de outro publisher; reprint idempotente conforme contrato.

### 11.3 SLO iniciais, sujeitos a G-08

| Serviço/indicador | Meta inicial | Medição/ação |
|---|---|---|
| Projection principal | p95 ≤500 ms, payload comprimido ≤300 KB | medir 1/10/100 comandas e até 1.000 SKUs; fixar query budget a partir do plano de queries |
| Review e customer search | p95 ≤500 ms em carga acordada | degradar explicitamente acima de timeout; nunca vazio falso |
| Aceitação de comando interno | p95 ≤1 s | receipt persistido; separar latência de provider |
| Commit/pagamento/pendência visível | mudança canônica refletida ≤2 s com SSE; fallback ≤15 s | medir; backoff/jitter sem storm; prazos ratificados por capacidade |
| Hardware local | feedback imediato; timeout explícito ≤3 s | unknown quando efeito não comprovado; sem insistência cega |
| Browser | INP p75 ≤200 ms; LCP p75 ≤2,5 s; CLS ≤0,1 | dispositivo de referência, não workstation ideal |
| Unknown monetário | nenhum sem owner; alvo de triagem ≤2 min durante turno | bloqueio/escala conforme G-03; não meta de “resolver” sem fonte |
| Integridade | zero duplicações, terminal errado, captura falsa, PII indevida e contagem cega vazada | incidente e interrupção da expansão, independentemente de percentil |

Carga sintética: zero/um/muitos recursos; 100 comandas abertas, 10 mil eventos históricos, combinações de pagamentos/pendências e duas a dez estações como cenários iniciais. Dimensionar pico observado ×2 em G-08. Medir DB queries, scans, locks/deadlocks, memory, payload, latência, fila e conexões SSE; não impor número arbitrário de queries sem baseline. Nenhum cache de total/autoridade pode ignorar revisão/estação/ator.

### 11.4 Telemetria e runbooks

Métricas por tipo/outcome/code: runtime mismatch, receipt/replay/conflict, unknown age, review stale, autosave pending, payment pending, fiscal/print pending, reconciliation mismatch, close blocked, query/latency, SSE fallback e recovery. Não usar ref de pedido/cliente/telefone/CPF/chave/token/conteúdo como label de métrica. Correlacionar refs técnicas em logs/traces com acesso e retenção aprovados; PIN/crachá/token/credencial e payload bruto nunca.

Runbooks mínimos, com diagnóstico read-only, efeito conhecido/desconhecido, ação permitida/proibida, owner, escalada, reconciliação e encerramento:

1. terminal/estação incompatíveis ou revogados;
2. venda/lançamento com resultado desconhecido;
3. PIX/cartão externo/COD/conta e cancelamento versus devolução;
4. fiscal e entrega de comprovante pendentes;
5. impressora/agente/gaveta/sensor indisponíveis;
6. comanda/cozinha conflitante ou sem roteamento;
7. fechamento cego bloqueado e handoff de turno;
8. rollback/reconciliação pós-incidente e recuperação de sessão/rede.

Reusar runbook existente quando adequado e registrar path real. Não criar oito documentos vazios para preencher checklist. Operador não autor executa os drills sem precisar perguntar a sequência.

## 12. Migração, flags, integração e rollout

- **Um writer por efeito.** Shadow compara leituras/resoluções sem disparar cobrança, nota, kitchen fire ou job duas vezes. Não copiar dual-write de Marketing para ledgers monetários.
- **Expand/contract.** Migrations aditivas e backfills resumíveis, idempotentes, com dry-run/checkpoints/contagens e teste de compatibilidade. Não inventar hashes, recibos ou confirmação física de eventos antigos. Drop/cleanup só em release posterior e autorizado.
- **Flags por capacidade real.** Exemplos de intenção: runtime binding, contract reader novo, recovery view, receipt jobs e display scoped. O executor define nomes existentes/necessários, owner, default, expiração e fallback no log. Flags não desativam autorização, idempotência, blind count ou regras monetárias.
- **Integração.** Comparar com base-alvo atual; resolver semanticamente cada hotspot, regenerar schemas/lock quando necessário e repetir gates no SHA integrado. Uma suite verde em worktree antiga não aprova merge posterior.
- **Canary local/sintético.** Mesma cadeia operacional com adapters fake, nenhuma credencial real. Ensaiar rollback com comando in-flight.
- **Piloto.** Uma estação/equipe autorizada, equipamento conferido, on-call, backup e janela. Observar pico, suspensão/rede, múltiplos operadores e fechamento. Não interromper loja para caber em roteiro.
- **Expansão.** Acrescentar próxima estação somente após gate com métricas/reconciliação; depois conjunto acordado e cobertura total. Não aplicar porcentagem que divida uma mesma custódia entre versões incompatíveis.
- **Abortar.** Qualquer duplicação, cross-terminal, captura/nota falsamente confirmada, vazamento de cego/PII, unknown sem owner ou recovery sem saída interrompe expansão. Perda de SLO sustentada usa política de burn aprovada.
- **Rollback.** Pausar novos efeitos afetados, preservar e consultar receipts/ledgers, reverter interface/reader compatível, reconciliar in-flight, reabrir somente com decisão. Nunca apagar Entry, forçar “pago”, repetir cobrança/nota ou restaurar seleção insegura do primeiro terminal.

Cada produção exige autorização explícita de alvo, janela e ações; documento de rollout não a substitui. Sete dias operacionais pós-expansão são mínimo proposto, com observação de fechamento; G-08 pode ampliar conforme operação.

## 13. Manifesto de cobertura e hotspots

Lista orienta leitura/decisão, não autorização para reescrever tudo. Cada grupo recebe `alterar`, `preservar com prova`, `consolidar` ou `aposentar` no execution log. Resolver renomes pela base atual.

| Área/path | Cobertura exigida | WP |
|---|---|---|
| `surfaces/pos-nuxt/app/app.vue`, `pages/index.vue` | gate/contexto, checkout, pending, retomada e composição de jornada | 01/06/07/09 |
| `pages/session/{index,closing,report}.vue` | custody/cego/dia/handoff, validação e resultado | 10 |
| `pages/tickets.vue`, `usePosOrderTickets.ts`, `presentation/orderTickets.ts` | cozinha/pedido/pagamento, scopes e deep-links | 04/06 |
| `pages/display.vue`, `useCustomerDisplay.ts`, `PosDisplayPublisher.vue`, `types/customerDisplay.ts` | publisher/runtime/schema/TTL/PII; sem fetch privilegiado desnecessário | 08/09 |
| `usePosSale.ts`, `usePosAction.ts`, `posIntent.ts`, `posTabLifecycle.ts` | revisão, fingerprint, erro, rascunho e comandos sem fallback | 02–07 |
| `usePosTerminal.ts`, `usePosEvents.ts`, `usePosCashSession.ts`, `useDayClosing.ts`, `useCashReport.ts` | contexto, freshness, lifecycle/pending, teardown, autoridade | 01/05/10 |
| `PosPaymentWorkspace.vue`, `PosSaleResult.vue`, `PosPaymentResult.vue`, `PosRecentSales.vue` | meios, total, troco, resultado canônico e recovery | 03/06 |
| `PosTabBoard`, `PosTabHeader`, `PosCartPanel`, `PosMoveLinesDialog`, `PosCancelSaleDialog` | linhas/revisões/delta/impacto e confirmação | 04 |
| `PosCustomerModal`, `PosCustomerSearch`, `PosReceiptSaveOffer`, `PosFulfillmentModal`, `PosScheduleModal`, `PosAddressAutocomplete` | seleção/dados só da venda/agenda e erro recuperável | 07 |
| `PosProductGrid`, `PosProductTile`, `PosFunctionRail`, `PosShortcutsHelp`, `PosPinPad` | busca/unidade/foco/scanner/ergonomia | 07/09 |
| `PosCashReadingCard`, `PosDenominationCounter`, `PosTerminalHealth`, `PosDrawerLockDialog` | cego, impedimentos, certeza da sonda e aprovação | 08/10 |
| `useCounterAgent`, `useAgentHealth`, `useDrawerLock`, `useDrawerIdleWatch`, `usePosAutoLock` | efeito físico, timeout, lock e recuperação | 08/09 |
| `PosReceipt`, print CSS, `presentation/printGeometry.ts` | canonização/paridade, 58/80mm e reprint | 08 |
| `app/presentation/**`, `types/**`, `generated/posContract.ts` | sem política duplicada, contrato gerado e enum exhaustive | 05 |
| `app/components/Ui/**`, CSS, config Nuxt | tokens/44px/teclado/semântica/headers/assets | 09 |
| `tests/**`, Playwright/Vitest configs, package/lock, README | fluxo real versus mock, install limpo e gates | 00/11 |
| `shopman/backstage/api/operations.py` e URLs/permissions/contracts | hotspot: runtime, comandos, Actions/errors/replay e read scopes | 01–05/10 |
| `shopman/backstage/projections/pos.py`, presentation POS/cash e services POS/terminal/hardware | fato/autoridade/ledger/readiness | 01/05/08/10 |
| `shopman/shop/services/{pos,pos_intent,pos_links,payment,remote_mutations,kds}.py` | writers existentes, transações, revisão, resultado e vínculo | 02–04/06 |
| services de cliente/entrega/agendamento/fiscal/notification e handlers atuais | owner canônico e efeito pós-commit; confirmar paths antes de editar | 03/06/07 |
| `packages/{orderman,cashman,payman,stockman,guestman,doorman,fiscalman,craftsman}` | só extensão/reparação necessária, com testes dos consumidores; sem dependência Core→Backstage | 01–04/06–11 |
| `tools/pos-counter-agent/**` e downloads/config Admin | versão, spool, sensor, origin/token, jobs e instalação autorizada | 08 |
| `operator-kit` session/identity/manager auth/proxy/SSE/tokens | coordenação com Marketing/Produção; consumer regressions | 09/11 |
| Admin Cashman/POS/terminal, `admin_console/pos_counter_agent.py` e templates correspondentes | configuração/auditoria nativas, sem segundo cockpit | 08/11 |
| CI/deploy/readiness/runbooks/docs de surface/spec/contract | candidate/rollback, ambiente isolado, realidade documentada | 11/12 |

## 14. Backlog de entregas com rastreabilidade

Cada item fecha com artefato/teste/commit, não com intenção. Itens de rollout permanecem bloqueados até autorização. Priorização pode ser ajustada com evidência e decisão registrada, sem reduzir invariantes.

| ID | Prioridade | Entrega e aceite específico | Depende de |
|---|---|---|---|
| PDV-001 | P0 | mapa de baseline/achados/provas e ambientes isolados | WP-00 |
| PDV-002 | P0 | runtime request canônico, sem default em venda ambígua | 001, G-02 |
| PDV-003 | P0 | negar body terminal divergente; scopes A/B e modo remoto explícito | 002 |
| PDV-004 | P0 | idempotência requerida, fingerprint e receipt por comando/escopo | 001, G-07 se extensão |
| PDV-005 | P0 | dinheiro e receipt atômicos/reconciliáveis sob crash | 003/004 |
| PDV-006 | P0 | revisão Session e CAS em comandos de comanda | 004 |
| PDV-007 | P0 | preservar tender único com semântica de cash/mixed aprovada | 003/004, G-03 |
| PDV-008 | P0 | review fingerprint/epoch e close correspondente | 006/007 |
| PDV-009 | P0 | resultado desconhecido honesto; consulta depois de timeout | 004/005 |
| PDV-010 | P0 | fire/save/move/clear integrados sem perda/delta duplicado | 006 |
| PDV-011 | P1 | contrato gerado completo e sem fallback de mutação | 003–010 |
| PDV-012 | P1 | outcome por pedido/efeito e fila recuperável de pending | 009/011 |
| PDV-013 | P1 | vários PIX + callback/reload/cancel/refund reconciliados | 007/012 |
| PDV-014 | P1 | fiscal/email/print com recuperação específica e sem revenda | 012, G-05 |
| PDV-015 | P1 | recibo canônico/paridade, jobs e reprint auditado | 012/014 |
| PDV-016 | P1 | busca de cliente sem falso vazio/resposta antiga | 011 |
| PDV-017 | P1 | identidade versus comprovante preservadas em conflito | 011/016, G-05 |
| PDV-018 | P1 | agenda/frete/catálogo revalidados sem redigitação | 008/011/017 |
| PDV-019 | P1 | draft/receipt retomados com isolamento e TTL aprovados | 006/012/017, G-05 |
| PDV-020 | P1 | display escopado/versionado/expirável e sem PII | 003/011 |
| PDV-021 | P1 | agente e sensor com nível de evidência explícito | 015, G-04 |
| PDV-022 | P1 | scanner e autorização compartilhada sem regressão | 003/011, G-02 |
| PDV-023 | P1 | auth/lock/reconnect preservam contexto e reautorizam | 019/022 |
| PDV-024 | P1 | HTTP/cache/headers/origin/redaction testados | 011/023 |
| PDV-025 | P1 | geometria/teclado/leitor/zoom/matriz visual | 012–024, G-06 |
| PDV-026 | P1 | fechar turno/dia sem mistura nem vazamento do cego | 003/005/012, G-03 |
| PDV-027 | P1 | troco/conta/COD/refund/handoff rastreáveis | 013/026 |
| PDV-028 | P1 | harness sem warning estrutural, lint/type/build verdes | 001; final após 025 |
| PDV-029 | P1 | browser integrado e PostgreSQL/Redis adversarial | 010–028 |
| PDV-030 | P1 | SLO/carga/redaction/dashboards/runbooks/drills | 029, G-08 |
| PDV-031 | P1 | Admin canônico mínimo e documentação atualizada | 020–030, G-07 |
| PDV-032 | P1 | budgets antes/depois e tradeoffs ratificados | 025/027, G-06 |
| PDV-033 | P2 | equipamento real e ensaio de turno assinado | 029–032, G-04/G-09 |
| PDV-034 | P2 | piloto em uma estação e go/no-go | 033, G-08/G-09 |
| PDV-035 | P2 | expansão, reconciliação e observação pós-release | 034, G-09 por estágio |
| PDV-036 | P2 | cleanup posterior, handoff e DoD assinada | 035, G-07/G-09 |

Discovery não autoriza feature: offline commit, TEF/novo gateway, balança integrada, estoque de denominações, cobrança autônoma e assistência por IA precisam de pedido/decisão separados. Neste plano, antecipação pode ser determinística por fatos e Actions, sem introduzir IA.

## 15. Definition of Done

### 15.1 Integridade e autoridade

- [ ] Todos os achados têm reprodução ou fechamento `já satisfeito` no HEAD final; nenhuma alegação de incidente sem prova.
- [ ] Estação/terminal/turno/ator coincidem na leitura, comando, ledger e resultado; mismatch/ambiguidade bloqueiam efeito indevido.
- [ ] Permissions e aprovação operam no servidor, com executor/aprovador distintos quando exigido; replay não vaza nem herda privilégio.
- [ ] Comandos críticos exigem key estável, fingerprint e revisão pertinente; mesmo gesto não duplica e conteúdo diverso conflita.
- [ ] Crash de efeito/receipt, response lost e concorrência real PostgreSQL convergem sem duplicação ou abandono silencioso.
- [ ] Review aceita = valor/tenders/collection/preço/desconto/frete/troco do resultado canônico, ou nova revisão explícita.
- [ ] Comanda/linhas/transferência/cozinha conservam identidade, quantidade e ocorrência; nenhum dado concorrente é sobrescrito silenciosamente.
- [ ] Payman e Cashman reconciliam; COD fica fora até liquidação; cancelamento e devolução não são confundidos.
- [ ] Fechamento cego não expõe esperado/diferença ao contador por nenhum caminho; turno e dia têm contratos próprios.

### 15.2 Recuperação, sessão e periféricos

- [ ] Timeout não nega nem confirma efeito sem fonte; receipt consultável após reload/reauth/turno fechado conforme autoridade.
- [ ] PIX simultâneos, fiscal, email, cozinha e impressão pendentes permanecem rastreáveis por pedido/owner e têm Actions exatas.
- [ ] Nenhuma falha de efeito secundário provoca revenda, recobrança, reemissão ou retry cego de unknown.
- [ ] Draft seguro recuperável não mistura operadores nem persiste PIN/crachá/token; dados da nota não alteram cadastro implicitamente.
- [ ] Offline não cria pedido/pagamento/caixa nem autoriza commit; reconexão consulta e revalida antes da próxima decisão.
- [ ] Agent/job/sensor/display declaram o nível real de certeza; display escopado/expirável não mistura publishers nem vaza PII.
- [ ] Impressão e gaveta aprovadas no aparelho autorizado; byte/health/spooler fake não assinam gate físico.
- [ ] Lock/revogação/expiry, scanner, teclado e troca de operador não deixam fundo interativo ou aprovação herdada.

### 15.3 Omotenashi e qualidade

- [ ] R01–R14 medidos antes/depois, metas ratificadas/atendidas ou exceções assinadas sem reduzir controle.
- [ ] Nenhum dado conhecido exige redigitação no caso comum; próximo passo e consequência são visíveis no contexto.
- [ ] Pendências não exigem caça em outra superfície quando PDV já tem fonte/capability; handoff dispensa compilação manual.
- [ ] Catálogo, cliente, agenda, comanda, checkout, tickets, caixa, display e print passam pela matriz de estados/viewports.
- [ ] A11y automatizada e manual passam: foco, teclado/leitor, touch, reflow, contraste e reduced motion.
- [ ] Contrato gerado e Actions sem fallback passam; lint, types, build, unit/component e browser integrado passam.
- [ ] Warnings estruturais não são silenciados; skips relevantes estão resolvidos no ambiente adequado; teste mock não é confundido com E2E.

### 15.4 Operações, documentação e conclusão

- [ ] SLO/capacidade ratificados e medidos em pico×2; integridade tem zero violações fora de qualquer error budget.
- [ ] Logs/metrics/traces não contêm credenciais/PII indevida; correlação de efeitos e alertas acionáveis funcionam.
- [ ] Runbooks executados por não autor; rollback com in-flight ensaiado e sem apagar evidência.
- [ ] Admin permanece configuração/auditoria canônicas; `make admin` integral passa quando alterado.
- [ ] Spec/contratos/READMEs/rotas/setup/documentação refletem sistema final e decisões posteriores às fontes antigas.
- [ ] Migrations/flags/compatibilidade/cleanup estão documentados; um writer por efeito; integração semântica revalidada.
- [ ] Todos os gates aplicáveis têm decisor, data, escopo e evidência, sem aprovação presumida.
- [ ] Piloto de turno, hardware, expansão e observação pós-release foram autorizados e aprovados.
- [ ] Handoff final contém base, branch/worktree, commits, comandos/resultados, métricas, riscos e rollback.
- [ ] Responsável humano assinou encerramento dos PDV-001–036 e DoD. Itens não realizados têm decisão explícita; invariantes não podem receber N/A.

Enquanto houver gate físico/piloto/produção pendente, declarar o máximo estado verdadeiro. **Plano concluído** exige que dinheiro, pedido, cliente, cozinha, fiscal, papel, operador e auditoria concordem na operação observada, inclusive quando algo falha.
