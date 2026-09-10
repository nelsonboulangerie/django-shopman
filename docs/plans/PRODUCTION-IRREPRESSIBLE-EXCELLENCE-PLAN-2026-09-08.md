# Plano adversarial — Produção Backstage rumo à excelência irreprimível

**Data da auditoria:** 8 de setembro de 2026

**Superfície:** `surfaces/production-nuxt` e toda a cadeia Django/Craftsman/Stockman/Orderman que ela comanda

**Natureza deste documento:** plano de implementação e verificação; não é autorização para alterar produção

**Ordem de prioridade:** verdade operacional → segurança → confiabilidade → omotenashi operacional

## 0. Contrato de execução para um agente externo

Este documento é autocontido como backlog técnico, especificação de experiência, sequência de implementação e Definition of Done. Um agente externo deve lê-lo inteiro antes da primeira alteração e tratá-lo como contrato de resultado, não como lista opcional de sugestões.

### 0.1 Instrução curta canônica

Depois desta seção, a delegação pode ser feita com apenas:

> Analise integralmente e execute, na ordem e com todos os gates e critérios de aceite, o plano `docs/plans/PRODUCTION-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md`. Continue autonomamente até o último resultado seguro que não dependa de decisão humana, credencial, hardware, escrita em produção ou autorização adicional; registre evidências e pare somente nos gates explicitamente definidos pelo próprio plano.

“Executar” autoriza alterações reversíveis no repositório, testes, documentação, schemas, migrações backward-compatible, criação de worktree/branch local isolado e commits locais atômicos necessários ao escopo. Não autoriza merge na branch compartilhada, push, PR, deploy, escrita em dados reais, provisionamento/revogação de estações, alteração de credenciais, operação de hardware real nem migração destrutiva em produção.

### 0.2 Preparação obrigatória

Antes de editar, o agente deve:

1. ler todos os `AGENTS.md` e demais instruções locais aplicáveis, se presentes, em toda a hierarquia dos arquivos que tocar;
2. ler os ADRs e cânones citados neste plano, especialmente ADR-012, ADR-014, ADR-017, ADR-018, `backstage-design-system.md`, `unfold_admin_page_playbook.md` e `unfold_canonical_policy.md`;
3. inspecionar `git status` e preservar toda alteração preexistente, inclusive arquivos não rastreados;
4. reproduzir o baseline da seção 2 no ambiente oficial do projeto;
5. verificar cada achado contra o código atual. O resultado exigido pelo plano permanece normativo, mas linha, arquivo ou implementação podem ter mudado desde a auditoria;
6. criar um log exclusivo da sessão em `docs/plans/production-irrepressible-excellence-execution/<task-ou-branch-id>.md`; nunca compartilhar o mesmo arquivo com outro agente. Um índice consolidado, se necessário, é responsabilidade do integrador.

### 0.3 Ciclo obrigatório por pacote de trabalho

Executar P0 → P1 → P2 na ordem de dependências da seção 4. Para cada WP:

1. **Reproduzir:** criar ou identificar teste que demonstra o risco/comportamento atual.
2. **Contratar:** fechar schema, invariantes, capacidades, estados de UX e compatibilidade antes da implementação visual.
3. **Implementar verticalmente:** domínio/transação → projeção/action contract → API → cliente gerado → apresentação → telemetria → documentação.
4. **Migrar com segurança:** toda mudança de dados deve ser backward-compatible, idempotente, possuir dry-run quando aplicável e plano de rollback.
5. **Provar:** executar os testes focados e gates do WP, depois as suítes afetadas; registrar comandos, resultados e evidências.
6. **Revisar adversarialmente:** testar payload forjado, concorrência, retry, falha parcial, sessão/permissão revogada, acessibilidade, textos longos e viewport relevante.
7. **Registrar:** no execution log, anotar status, decisões, arquivos, migrações, testes, métricas antes/depois, riscos restantes e próximo WP desbloqueado.

Não considerar WP concluído porque o código compila ou o happy path passa. Todos os seus critérios de aceite, casos negativos e observabilidade precisam estar demonstrados.

### 0.4 Regras de autonomia

O agente deve avançar sem pedir confirmação para inspeção, implementação e validação seguras que estejam claramente dentro deste plano. Deve fazer a menor mudança coerente com a arquitetura, reutilizar padrões já maduros do projeto e não ampliar o domínio por conveniência técnica.

Quando um achado descrito já estiver corrigido, o agente deve provar isso com teste atual, registrar `já satisfeito` e seguir; não reescrever código saudável. Quando descobrir risco novo dentro da mesma cadeia, deve adicioná-lo ao execution log, classificá-lo e corrigi-lo no WP apropriado se não exigir expansão material de escopo.

Não criar um segundo writer, uma segunda superfície, um fallback que relaxe autorização ou uma compatibilidade que preserve comportamento sabidamente incorreto. Não editar arquivo gerado manualmente. Commits locais coesos são permitidos para isolar e preservar o trabalho; não fazer merge, push, abrir PR, fazer deploy ou alterar produção a menos que a instrução externa autorize expressamente essas ações.

### 0.5 Gates que exigem decisão ou coordenação humana

O agente pode preparar alternativas, contratos, testes e uma recomendação, mas não deve inventar estas decisões:

| Gate | Decisão necessária | Trabalho seguro que pode antecedê-la |
|---|---|---|
| D1 — matriz de autoridade | Capacidades finais de Cozinha, Líder/Gerente, Relatórios e Administrador; quais exigem aprovação | Infraestrutura de capabilities, testes de negação e matriz proposta |
| D2 — estação confiável | Quais mutações exigem dispositivo provisionado além de operador autenticado | Projetar device posture e enforcement configurável |
| D3 — perda total | Nome/semântica contábil e operacional do novo desfecho se exigir mudança de ADR/lifecycle | Provar a lacuna, invariantes e proposta backward-compatible |
| D4 — menuboard físico | Mapeamento das TVs para board refs e janela de troca | Remover contrato público, preparar redirect/config e validar renderer canônico |
| D5 — pesagem | Processo real, tolerâncias, lotes, política advisory/bloqueante e hardware | Sessão/eventos, simulador e fluxo manual atrás de flag |
| D6 — capacidade | Recurso escasso real: forno, lastro, masseira, bancada ou pessoa | Discovery, instrumentação e projeção de conflito sem scheduler genérico |
| D7 — omotenashi medido | Baseline de turno e metas finais de esforço/confiança | Instrumentação, roteiro de observação e budgets provisórios da seção 8.6 |
| D8 — piloto/rollout | Estação, equipe, janela, owner e critérios de abortar | Build candidato, runbook, flags, dashboards e rollback ensaiado |

Ao atingir um gate, o agente deve apresentar: fatos observados, alternativas, recomendação, impacto, reversibilidade e escolha exata necessária. Deve continuar em outros WPs independentes seguros; só para integralmente se o gate bloquear o próximo caminho crítico.

### 0.6 Estados de conclusão permitidos

- **Implementação técnica concluída:** código, migrações, testes, documentação e observabilidade estão prontos; ainda pode faltar piloto.
- **Pronto para piloto:** build e dados de teste passaram, runbook/rollback estão ensaiados e apenas D8 separa o trabalho da operação controlada.
- **Rollout concluído:** piloto, expansão e observação pós-release da seção 11 foram executados com autorização e evidência.
- **Plano concluído:** somente quando toda a seção 14 estiver satisfeita. Não usar esta expressão para um subconjunto de WPs.

Se credencial, decisão, equipamento ou autorização impedir avanço, o agente registra precisamente o bloqueio e entrega o máximo estado de conclusão verdadeiro; nunca simula o gate nem reduz silenciosamente o aceite.

### 0.7 Protocolo obrigatório de convivência multiagente

Este repositório recebe agentes e sessões em paralelo. Preservar o trabalho alheio é um requisito de correção, não uma cortesia.

#### Isolamento antes da primeira escrita

1. Executar `git status --short`, identificar raiz, branch, HEAD e `git worktree list --porcelain`.
2. Se a sessão já estiver em worktree exclusivo fornecido pelo ambiente, permanecer nele.
3. Se estiver no checkout compartilhado, criar um worktree exclusivo a partir do HEAD conhecido, com branch local de prefixo `codex/` e sufixo único da tarefa. Não mover, reutilizar nem apagar worktree de outra sessão.
4. Se este próprio plano ainda não estiver rastreado no SHA-base, levá-lo como o único input não commitado para o novo worktree, conferir hash/conteúdo idêntico e registrá-lo no primeiro commit local. Não transportar junto outros arquivos sujos.
5. Se o trabalho depender de qualquer outra alteração não commitada existente no checkout compartilhado, não copiá-la nem assumi-la silenciosamente. Identificar arquivos/dependência e pedir ao responsável uma base commitada ou autorização de integração.
6. Registrar no execution log: path do worktree, branch, SHA-base, data e escopo inicialmente assumido.

Não iniciar uma implementação longa no checkout principal sujo. Uma branch diferente no mesmo diretório não é isolamento; o requisito é worktree/diretório separado ou um ambiente equivalente fornecido pelo orquestrador.

#### Disciplina durante cada edição

1. Antes de modificar um arquivo, reler seu conteúdo e executar `git diff -- <arquivo>` no worktree atual. Não confiar em conteúdo lido horas antes.
2. Aplicar patches pequenos e com contexto estreito. Se o contexto falhar ou o arquivo mudar inesperadamente, parar naquele arquivo, reler e reconciliar semanticamente.
3. Nunca usar `git reset --hard`, `git clean`, `git restore`, `git checkout --`, stash abrangente ou qualquer comando que descarte/oculte mudanças alheias.
4. Não executar formatter, codemod, gerador ou substituição massiva sobre o repositório inteiro. Limitar ao conjunto assumido e revisar o diff resultante.
5. Não usar `git add -A` nem `git add .`. Se fizer commit local, adicionar paths explícitos e conferir `git diff --cached` para impedir captura de trabalho alheio.
6. Não alterar, mover ou apagar arquivo não rastreado que a sessão não criou.
7. Não “resolver” conflito aceitando o arquivo inteiro de um lado. Mesclar intenção por intenção e executar os testes de ambos os lados.
8. Se detectar outra sessão editando o mesmo arquivo/worktree, suspender escrita nesse hotspot, registrar a colisão e continuar somente em arquivos independentes até haver coordenação.

#### Hotspots que exigem serialização explícita

- novas migrations e grafo/numeração de migrations;
- `app/generated/productionContract.ts` e seu schema gerador;
- `package-lock.json` e dependências do `operator-kit`;
- contratos compartilhados, permissões e URLs centrais;
- este plano e eventual índice consolidado de execução; logs individuais usam nomes exclusivos;
- snapshots visuais, fixtures globais e arquivos de configuração de CI/deploy.

Antes de tocar um hotspot, atualizar a visão da branch-base e conferir alterações recentes. Migrations devem receber dependência/nome sem colisão; schemas e lockfiles devem ser regenerados depois de integrar mudanças predecessoras, nunca mesclados manualmente como texto se puderem ser reproduzidos.

#### Commits e handoff

1. Produzir commits locais pequenos por slice vertical ou invariante, com testes verdes e sem arquivos não relacionados.
2. Registrar no execution log o hash, arquivos, testes e dependências de cada commit.
3. Antes do handoff, comparar a branch com o SHA-base e com a branch-alvo atual; apontar conflitos prováveis, migrations paralelas e artefatos que precisarão ser regenerados.
4. Não integrar automaticamente na branch compartilhada. Entregar branch/worktree, hashes, ordem de aplicação, testes e instruções de integração ao responsável.
5. O integrador deve incorporar a branch mais recente no worktree isolado, resolver conflitos semanticamente, regenerar hotspots e repetir os gates antes de merge autorizado.

Se worktree isolado não puder ser criado, isso é um gate operacional: o agente pode continuar a análise somente leitura, mas não deve editar o checkout compartilhado sem coordenação explícita de arquivos e janela de escrita.

## 1. Resultado que este plano deve produzir

Ao final, um operador deve conseguir planejar, preparar, pesar, iniciar, acompanhar, controlar o forno, classificar a qualidade, concluir, rastrear e auditar uma fornada sem:

- enxergar ou executar ações acima de sua função;
- criar duas ordens por causa de um duplo toque, retry ou resposta perdida;
- sobrescrever silenciosamente o trabalho de outro tablet;
- converter perda em produto vendável, ou estorno em perda, por falta de um desfecho de domínio verdadeiro;
- depender de dados planejados quando já existe quantidade real iniciada;
- operar sobre projeção obsoleta, sessão vencida ou rede caída;
- escolher implicitamente “a primeira” ordem quando há mais de uma fornada no mesmo produto;
- perder rastreabilidade entre receita congelada, insumos, pesagem, forno, qualidade, lote, estoque e pedidos;
- enfrentar controles pequenos, foco perdido, informação truncada ou telas que se comportam de modo diferente dos outros apps Nuxt do Shopman.

O estado de excelência exige ainda:

1. um único contrato operacional canônico, no qual o backend resolve ações, capacidades, impedimentos e recuperação;
2. uma única implementação canônica de menuboard;
3. configuração e auditoria administrativa canônicas no Django Unfold, sem reconstruir operação no Admin;
4. estados visuais completos e testados em tablet, desktop, TV, impressão e acessibilidade;
5. telemetria suficiente para provar que o sistema é correto sob concorrência e falha parcial.

### 1.1 O significado obrigatório de “uau”

Neste plano, “uau” **não é uma camada cosmética, uma animação ou um acabamento visual**. É omotenashi para quem opera: antecipar a necessidade antes de ela virar pergunta, remover trabalho mental e manual, apresentar a próxima decisão com o contexto certo, impedir erros recuperáveis, preservar o que já foi digitado, explicar exceções sem culpar o operador e fazer cada tarefa exigir o mínimo de toques, memória e coordenação externa.

Essa régua atravessa P0, P1 e P2. Segurança e integridade também são experiência: o operador não deve descobrir conflito depois de trabalhar, refazer uma fornada por retry, procurar o gerente sem saber por quê, lembrar números de outra tela nem conferir em papel se o sistema cumpriu o que prometeu. Acabamento visual só entra quando melhora leitura, confiança, velocidade ou tranquilidade.

Alertar também significa ajudar a resolver. Sempre que o domínio conhecer uma resposta pertinente, o alerta deve oferecer a ação no próprio contexto, já preenchida e autorizada, em vez de apenas anunciar o problema. Aviso sem providência possível deve ser deliberadamente classificado como estado, confirmação ou histórico; não disputar atenção no mesmo canal dos itens acionáveis.

Para cada fluxo, o agente executor deve responder e medir:

- O que o sistema já sabe e ainda está obrigando o operador a lembrar, redigitar ou procurar?
- Qual problema previsível pode ser evitado antes do toque?
- Qual é a próxima ação provável, por que ela é necessária e o que acontecerá depois?
- Como preservar contexto e progresso se houver interrupção, troca de turno, erro ou rede ruim?
- Quantos toques, mudanças de tela, esperas e consultas externas existem hoje e quantos restarão?
- A mensagem permite agir imediatamente ou apenas descreve o problema?
- Se a mensagem pede providência, as ações pertinentes estão ali, ordenadas, contextualizadas e prontas para uso?
- O operador termina o fluxo com certeza de que estoque, pedidos, qualidade e auditoria foram atualizados?

## 2. Baseline comprovado antes da execução

O agente executor deve preservar o que já funciona. A auditoria encontrou uma base tecnicamente forte no núcleo: `Craftsman` já oferece trava pessimista, revisão otimista e idempotência; o bridge de conclusão/estoque já possui recuperação; o BFF compartilhado já protege CSRF/origem; login possui limitação e mensagem genérica; estação confiável é um conceito existente; receita congelada e resultados de qualidade já existem.

Validações executadas nesta revisão:

- frontend unitário: 20 arquivos, 110 testes aprovados;
- frontend typecheck e lint: aprovados;
- backend focado em produção: 105 testes aprovados no ambiente virtual do projeto;
- Playwright atual: 5 testes aprovados, mas um deles cristaliza como requisito o menuboard público que este plano manda aposentar;
- inspeção somente leitura em `https://prod.boulangerie.com.br/`, desktop e mobile;
- inspeção de cabeçalhos HTTP e respostas anônimas dos endpoints de produção.

Esses testes provam estabilidade do contrato atual, não suficiência. Cada item abaixo só pode ser encerrado quando novos testes demonstrarem o comportamento pretendido.

## 3. Decisões que não podem ser reabertas implicitamente

### 3.1 Corte de superfícies

- A operação diária permanece no Nuxt de Produção.
- Cadastro, política, configuração, catálogo de qualidade e passaporte/auditoria ficam no Django Admin com componentes oficiais do Unfold.
- É proibido recriar Planejamento, Produção, Expedição ou Pesagem como console administrativo artesanal.
- É proibido criar uma terceira superfície para resolver lacunas desta.

### 3.2 Fonte de verdade

- Projeção do domínio: fatos, capacidades, ações, impedimentos, códigos semânticos, revisões e recuperação.
- Camada de apresentação Nuxt: composição visual, texto contextual que não seja política, tokens e comportamento responsivo.
- O frontend não infere se pode iniciar, concluir, forçar, estornar, reconhecer ou escolher lote.
- Toda mutação irreversível precisa de `expected_rev` e chave idempotente estável por tentativa.
- Modo offline é leitura somente. Não haverá fila local para ações irreversíveis.

### 3.3 Menuboard

- O menuboard canônico é interno, identificado por `ref`, protegido por credencial de dispositivo, alimentado por projeção própria e atualizado por SSE com fallback.
- A rota “demo” pública de Produção não pode permanecer como segundo produto concorrente.
- Se o visual Solari for preservado, ele vira um renderer do contrato canônico; não continua lendo o menu público da loja.

### 3.4 Cânone visual

- Produção continua light-first.
- Componentes, conectividade, sessão, rail, filtros e utilitários compartilháveis pertencem ao `operator-kit`.
- Raio padrão é o token `rounded-md`; exceções devem ser poucas, nomeadas e registradas.
- Seleção usa fundo/borda/ícone/check; `ring` fica reservado a foco.
- Alvo tocável mínimo: 44 × 44 px; ação primária no chão de fábrica: 48–56 px.
- Não adicionar cor, sombra, raio, espaçamento ou breakpoint arbitrário se já houver token compartilhado.

## 4. Sequência de entrega e portões

```text
P0.0 baseline e contratos
  ├─ P0.1 autorização por capacidade
  ├─ P0.2 concorrência, idempotência e transações
  ├─ P0.3 verdade de QC/perda/quantidades
  └─ P0.4 superfície e cabeçalhos seguros
         ↓
P1.1 projeções rápidas e frescas
  ├─ P1.2 Planejamento/Produção
  ├─ P1.3 Expedição/QC/Forno
  ├─ P1.4 Preparação/Pesagem
  ├─ P1.5 Relatórios/Alertas
  └─ P1.6 Unfold configuração/auditoria
         ↓
P2.1 pesagem executada e rastreável
P2.2 capacidade de forno e passos estruturados
P2.3 assistência operacional avançada
         ↓
Hardening, piloto por estação, rollout e prova pós-release
```

Nenhum pacote P1 pode liberar mutações enquanto P0.1–P0.3 estiverem abertos. P2 não pode começar a substituir fluxo de fábrica antes de o pacote correspondente P1 passar pelo piloto. Omotenashi não espera P2: cada pacote deve reduzir carga cognitiva, retrabalho e incerteza como parte de seu próprio aceite.

## 5. P0 — eliminar riscos de autorização, contrato e integridade

### WP-P0.0 — Congelar o contrato observado e criar o placar de risco

**Objetivo:** impedir que a refatoração perca comportamentos corretos ou esconda achados.

**Execução**

1. Registrar fixtures reais anonimizadas para: produto sem receita, uma e múltiplas WOs, ordem vinculada, estoque suficiente/insuficiente/zero legítimo, WO atrasada, passos parcialmente cumpridos, QC mista, perda total e corrida entre tablets.
2. Capturar contagem de queries, tempo de projeção e payload para board, KDS, QC, mise en place, pesagem, relatórios e alertas.
3. Criar uma matriz rastreável `achado → teste vermelho → mudança → teste verde → observabilidade`.
4. Marcar todos os contratos manuais e campos sem consumidor; nenhum campo será removido sem busca no repositório e teste de compatibilidade.
5. Tratar relatórios históricos como hipóteses: só transportar um achado se um teste atual o reproduzir.

**Arquivos centrais:** `shopman/backstage/tests/test_api_production_surface.py`, `test_production_operational.py`, `test_production_service.py`, `test_qc_kiosk.py`, `test_oven_runs.py`, testes Nuxt e fixtures E2E.

**Aceite:** baseline versionada, números de query/latência registrados e nenhum teste existente perdido sem justificativa no commit.

### WP-P0.1 — Substituir permissão grossa por capacidade efetiva

**Risco atacado:** hoje toda mutação herda `backstage.operate_production`, enquanto permissões finas existem, mas não governam a superfície Nuxt. Projeções são construídas com acesso total e ações sensíveis chegam à Cozinha e ao Gerente da mesma maneira.

**Contrato alvo**

Cada projeção operacional deve trazer:

```json
{
  "access": {
    "can_view_plan": true,
    "can_edit_plan": false,
    "can_start": true,
    "can_advance_step": true,
    "can_close_qc": false,
    "can_quick_finish": false,
    "can_override_shortage": false,
    "can_void": false,
    "can_record_oven_fact": true,
    "can_view_reports": false,
    "can_reveal_blind_map": false
  },
  "actions": []
}
```

Cada ação deve conter `ref`, `kind`, `label`, `priority`, `enabled`, `reason`, `method`, `href`, `payload_schema`, `expected_rev`, `idempotency`, `confirmation` e, quando necessário, `approval_requirement`. Quando nascer de um alerta, deve ainda carregar `source_alert_ref` e o efeito esperado sobre seu ciclo de vida (`keeps_open`, `acknowledges` ou `resolves`), sem deixar essa decisão para o componente.

**Execução**

1. Definir, com negócio, matriz mínima para Cozinha, Líder/Gerente, Relatórios e Administrador; separar ver de executar.
2. Fazer `resolve_production_access()` receber usuário, estação e contexto de data; eliminar `_full_access()` das APIs reais.
3. Aplicar capacidade tanto à visibilidade de linhas/agregados quanto a cada ação. Contagens não podem vazar itens filtrados.
4. Validar a mesma capacidade no endpoint; ação oculta nunca é controle de segurança.
5. Exigir capacidade separada, justificativa e identidade elevada para forçar falta, estornar, perda excepcional e conclusão rápida.
6. Decidir quais ações de alto risco exigem estação confiável além de usuário; projetar o impedimento, não apenas responder 403.
7. Não reutilizar o PIN de outra pessoa sem registrar o aprovador como ator distinto do executor.
8. Escopar alertas a `audience=production` e capacidades; impedir reconhecimento de alertas financeiros/pedidos por persona sem autorização.
9. Projetar as ações de cada alerta com as mesmas capacidades do objeto de origem; abrir o sino não pode conceder um atalho de autorização.

**Arquivos:** `shopman/backstage/permissions.py`, `api/permissions.py`, `api/operations.py`, `api/alerts.py`, `projections/production.py`, `services/production.py`, `station_trust.py`, `services/alerts.py`, `admin/navigation.py`, `surfaces/production-nuxt/app/app.vue`, `ProductionStageGrid.vue`, `expedite.vue`, `QcCloseScreen.vue`, `AlertsBell.vue` e composables.

**Testes obrigatórios**

- tabela positiva e negativa por persona, ação, linha e estação;
- acesso direto por URL e payload forjado;
- contagens/agregados não revelam linhas proibidas;
- aprovação registra executor, aprovador, razão e horário;
- permissão retirada durante sessão passa a valer no refresh/action seguinte;
- alertas são filtrados e cada ação contextual, reconhecimento e resolução é autorizada individualmente.

### WP-P0.2 — Tornar o contrato tipado, revisável e idempotente

**Risco atacado:** o backend expõe booleanos e dados; o Nuxt inventa endpoints, payloads e seleção de WO. `rev` do núcleo não atravessa a borda. Resultados de mutação e alertas ainda são tipos manuais.

**Execução**

1. Criar schema canônico de projeção + ações no backend, coerente com ADR-012 e ADR-014.
2. Expor `rev` por WO/agregado, `generated_at`, `source_revision`, `fresh_until` e `contract_version`.
3. Gerar tipos e cliente de leitura/mutação a partir do schema; incluir requests, sucessos, conflitos, shortages e validação.
4. Falhar o CI quando `export_production_schema` gerar diff não commitado.
5. Padronizar erros:
   - `validation_error`: `field`, `code`, `message`;
   - `conflict`: revisão enviada/atual, projeção mínima atual e ação de recarregar;
   - `shortage`: déficits, WO alvo, tentativa idempotente e possibilidades autorizadas;
   - `forbidden`: capacidade faltante e recuperação possível;
   - `stale_projection`: idade, revisão e refresh recomendado.
6. Rejeitar datas inválidas com 400; não converter silenciosamente para hoje.
7. Rejeitar intervalo invertido, período acima do máximo e filtros desconhecidos; não corrigir silenciosamente a intenção do usuário.
8. Trocar coerções Python como `bool("false")` por serializers DRF tipados.
9. Remover classes Tailwind de projeções (`status_color`, `timer_class`); emitir `status_code`, `tone` e fatos. Mapear aparência em `app/presentation`.
10. Substituir `table: dict` da pesagem por tipos fechados e versionados.
11. Dar a cada tentativa de mutação uma chave idempotente gerada antes do primeiro POST e reutilizada em retry/reconciliação.

**Arquivos:** `shopman/backstage/contracts.py`, `api/operations.py`, `api/_production_filters.py`, `projections/production.py`, `services/production.py`, comando `export_production_schema.py`, `app/generated/productionContract.ts`, `app/types/production.ts`, `app/utils/api.ts` e todos os composables.

**Aceite:** não há endpoint/payload de produção escrito à mão no componente; conflito nunca termina em “last write wins”; datas ruins não viram hoje; classes de renderer não atravessam Django → Nuxt.

### WP-P0.3 — Fechar corridas, duplo envio e mutações parciais

**Risco atacado:** garantias já existentes no Craftsman não são propagadas. Há mutações JSON sem trava, checagem de pedido fail-open e um caminho de conclusão rápida que pode deixar uma WO órfã e criar outra no retry forçado.

**Execução**

1. Passar `expected_rev` ao Craftsman em start/finish/void e equivalentes; traduzir conflito para o envelope padrão.
2. Refatorar `apply_advance_step` para transação, `select_for_update`, revisão e evento append-only; metadado material não pode ser a única trilha.
3. Colocar cobertura de pedidos vinculados e ajuste de quantidade na mesma transação/trava. Exceção inesperada deve falhar fechada no caminho estrito.
4. Implementar override explícito com capacidade, razão obrigatória, snapshot do impacto e evento de auditoria.
5. Serializar/conter concorrência no planejamento por célula receita/data/posição; evitar criação ou consolidação duplicada.
6. Redesenhar `quick_finish` como orquestração atômica ou saga idempotente:
   - uma tentativa cria no máximo uma WO;
   - shortage devolve a referência exata criada;
   - confirmação forçada continua essa mesma tentativa/WO;
   - falha final compensa ou deixa estado recuperável explícito;
   - resposta perdida e retry não criam nova WO.
7. Trancar e idempotentizar `oven_arm` e `oven_conclude`; POST repetido não abandona corrida nem cria forno fantasma.
8. Tornar `apply_oven_fact` observável e reconciliável: a UI não conclui silenciosamente se o fato obrigatório falhou.
9. Eliminar escolha implícita de `planned_orders[0]`/`started_orders[0]`. A projeção resolve uma ação não ambígua ou a UI exige seleção de fornada.
10. Reconciliar links Order ↔ WO sob trava; revisar cancelamento, conclusão, estorno e referências órfãs. Adicionar verificador/reparador seguro antes de considerar um modelo relacional novo.

**Arquivos:** `shopman/backstage/services/production.py`, `api/operations.py`, `shopman/shop/services/production.py`, `handlers/production_order_sync.py`, `backstage/models/oven_run.py`, `packages/craftsman/.../scheduling.py`, `execution.py`, `models/work_order.py`, `models/work_order_event.py`, `surfaces/production-nuxt` composables e telas de ação.

**Testes obrigatórios:** `TransactionTestCase` com PostgreSQL e barreira de concorrência para dois tablets; duplo clique; timeout depois de commit; retry com mesma chave; retry com chave diferente; revisão obsoleta; duas edições da mesma célula; dois arms/concludes; falta seguida de force; falha do Stockman depois do commit; falha de alerta e de link de pedido.

### WP-P0.4 — Restaurar verdade de quantidade, qualidade e perda

**Risco atacado:** preparação e pesagem usam quantidade planejada ou receita atual em situações nas quais já existem quantidade iniciada e snapshot. O catálogo de qualidade aceita referências desconhecidas por fallback/descarte. Não há desfecho honesto para perda total.

**Execução**

1. Para WO `STARTED`, usar quantidade efetivamente iniciada em pesagem, mise en place, rendimento e cópia; para `PLANNED`, usar planejada.
2. Em WO existente, calcular itens e `batch_size` somente a partir do snapshot congelado. Receita ao vivo serve apenas para uma nova WO.
3. Pré-carregar eventos e expor `started_qty` sem N+1.
4. Rejeitar grade ou defeito inativo/desconhecido. Nunca cair em grade padrão nem ignorar defeito silenciosamente.
5. Definir uma fonte de verdade para quantidade total versus soma das partições. Backend valida precisão, unidade, limites, veto de descarte e desvio.
6. Transmitir confirmação de desvio no contrato com razão/ator; confirmação apenas no cliente não vale.
7. Criar desfecho canônico `record_total_loss` ou equivalente:
   - consome os insumos reais;
   - grava saída `WASTE`, grade/defeito e quantidade;
   - produz zero estoque vendável;
   - encerra com estado/evento auditável;
   - libera/explica pedidos afetados;
   - não usa `void`, pois estorno não significa produto perdido depois de produzido.
8. Calcular `can_submit` e ações depois de aplicar `forces_discard`; a UI não deve convidar um POST que o servidor necessariamente rejeitará.
9. Completar o passaporte da fornada: snapshot, insumos/lotes consumidos, pesagens, fatos de forno, resultados QC, lotes de saída, pedidos, atores e revisões.

**Arquivos:** `projections/production.py`, `services/production.py`, `shopman/shop/services/quality.py`, `production_lifecycle.py`, `packages/craftsman` models/services, handlers Stockman, `QcCloseScreen.vue`, `mise-en-place.vue`, `WeighingLabels.vue`, tipos e Admin de WorkOrder.

**Aceite:** propriedades e testes de fronteira garantem conservação de quantidade, nenhum item descartado entra em estoque vendável e perda total aparece no passaporte/ledger sem fingir estorno.

### WP-P0.5 — Fechar a borda HTTP e aposentar o menuboard paralelo

**Risco atacado:** documentos Nuxt vivos não apresentaram CSP, proteção contra frame, `nosniff`, política de referência ou HSTS. `/menuboard` é público, consome o menu do storefront uma vez e contradiz o menuboard interno canônico.

**Execução**

1. Centralizar no `operator-kit`/Nitro, e reforçar no edge:
   - CSP compatível com Nuxt, incluindo `frame-ancestors 'none'` e `object-src 'none'`;
   - `X-Frame-Options: DENY`;
   - `X-Content-Type-Options: nosniff`;
   - `Referrer-Policy` estrita;
   - `Permissions-Policy` mínima;
   - HSTS no edge HTTPS;
   - `Cache-Control: private, no-store` em sessão e conteúdo autenticado.
2. Verificar `Vary`, cookies, CSRF e cache intermediário do BFF em todas as respostas.
3. Fazer boot de produção falhar se URL Django ou ambiente forem ausentes, locais ou inseguros; remover fallbacks localhost em release.
4. Retirar a rota pública `/menuboard` do app Produção e o teste que a consagra. Preferência: redirect/launcher explícito para a URL canônica por `ref`; nunca adivinhar board.
5. Se o renderer Solari for desejado, movê-lo para trás da projeção/credencial/SSE canônicas e registrar um único owner. Preservar estado anterior em falha, mostrar reconexão e não buscar storefront.
6. Atualizar ADR/docs/robots/README para refletir o corte real.

**Arquivos:** `surfaces/operator-kit/nuxt.config.ts`, novos utilitários de headers, `production-nuxt/nuxt.config.ts`, `server/api/v1/[...path].ts`, `app/app.vue`, `pages/menuboard.vue`, `SplitFlap.vue`, `tests/e2e/guards.spec.ts`, `shopman/shop/menuboard_*`, projeção/template/JS do menuboard canônico, deploy e release checks.

**Aceite:** scanner/teste de headers passa no host real; iframe é bloqueado; build sem ambiente falha; não existe endpoint público paralelo; TV confiável atualiza por SSE e recupera por poll sem piscar para vazio.

## 6. P1 — fazer a operação rápida, inequívoca e resiliente

### WP-P1.1 — Montar projeções em lote e tornar frescor explícito

1. Reescrever assemblers para carregar WOs, eventos, snapshots, usos de receita, pedidos e estoque em lotes; proibir `.get()` por cartão após montar a fila.
2. Substituir `any(balance > 0)` por presença real de leitura: zero é estoque conhecido, não ausência de telemetria.
3. Não transformar exceção da sugestão em lista vazia. Projetar `degraded`, causa segura, `last_success_at` e ação de retry.
4. Paginar/limitar relatórios e impor janela máxima; CSV grande vira export assíncrono ou streaming controlado.
5. Definir SLO depois do baseline, com alvo inicial de referência: p95 < 300 ms para board de 100 WOs e contagem de queries constante; ajustar somente com evidência.
6. Adotar SSE como invalidação, não como segunda fonte de verdade; fetch canônico continua reconciliando. Poll com jitter/backoff/visibilidade é fallback.
7. Corrigir `useAdaptivePoll`: flag de descarte após unmount, promises tratadas, jitter e backoff. Extrair para `operator-kit` se outros apps tiverem o mesmo problema.
8. Bloquear mutações quando `fresh_until` expirou, offline ou reconciliação está pendente; oferecer recarregar e preservar entrada do formulário.

### WP-P1.2 — Planejamento e grade de produção sem ambiguidade

**Fluxo alvo**

1. O operador abre a data e vê demanda, compromissos, estoque de insumos, capacidade, produção já coberta e confiança da sugestão.
2. “Por que esta sugestão?” abre decomposição curta e auditável, não um gráfico de BI.
3. Alterar quantidade mostra delta de insumos, pedidos cobertos e conflitos antes de confirmar.
4. Linha com múltiplas WOs expande fornadas; ação nunca seleciona a primeira silenciosamente.
5. Start pede quantidade/unidade adequadas e posição; quantidade decimal ou inteira deriva da unidade do produto.
6. Estorno mostra exatamente pedidos, estoque e alertas afetados, exige razão e, quando aplicável, aprovação.

**Mudanças**

- Sincronizar data, busca, posição, status e WO na URL; limpar query limpa estado local.
- Atualizar relógio de hoje/amanhã na virada do dia e exibir carryover não encerrado.
- Cabeçalho e primeira coluna sticky; scroll horizontal intencional; densidade compacta/confortável persistida.
- Estado busy por ação/WO, com spinner e texto; conflito recarrega e destaca o que mudou.
- Empty state oferece recuperação autorizada: limpar filtro, ir para hoje ou abrir cadastro canônico da receita.
- Não mostrar botão desabilitado sem razão acessível.

**Arquivos:** `ProductionStageGrid.vue`, `pages/index.vue`, `pages/plan.vue`, `useProductionBoard.ts`, `useProductionForecast.ts`, `useProductionManagement.ts`, `presentation/production.ts` e projeção board.

### WP-P1.3 — Expedição, forno e QC à prova de turno corrido

**Fluxo alvo**

- Cartão identifica produto, WO, posição, quantidade iniciada, hora, pedidos, passo atual, atraso, forno e próxima ação.
- Seleção por toque não usa `ring`; cartão inteiro é alvo sem elemento clicável aninhado inválido.
- Concluir abre revisão de QC com quantidade real, precisão correta, lotes previstos e destino de cada partição.
- Resumo antes de confirmar mostra vendável, markdown, descarte, validade e pedidos liberados/em risco.
- Voltar com formulário sujo pede confirmação.
- Perda total é ação de domínio própria.

**Forno**

1. Presets vêm de passo/receita/configuração, nunca de `15` hardcoded.
2. Timer local é apresentação dos fatos servidor-side; armazenamento inclui estação + WO + run ref.
3. Reentrada após suspensão calcula tempo pelo relógio absoluto.
4. Usar Wake Lock quando disponível; queda de suporte não impede operação.
5. Alarme persiste/escalona até reconhecimento e respeita preferências de acessibilidade; áudio só inicia após gesto permitido.
6. Fact arm/conclude tem idempotência, revisão, estado pending/error e reconciliação.
7. Não inventar pause/resume como fato se o domínio não o suporta; qualquer extensão exige ADR.

**Acessibilidade específica:** remover captura global de Tab/Enter; atalhos só no escopo certo, Space funciona em cartões, sheets prendem/restauram foco e leitores recebem uma mensagem por evento.

### WP-P1.4 — Preparação e etiquetas honestas antes da pesagem completa

1. Expandir seletor de data para custom range operacional e carryover, mantendo atalhos Hoje/Amanhã.
2. Se checklist continuar local na primeira fase, chavear por estação + data + hash/revisão da projeção; avisar e reconciliar quando o plano mudar. Rotular claramente como auxílio local, não como auditoria.
3. Se o negócio exige responsabilidade compartilhada, migrar checks para eventos servidor-side com ator/estação/hora; não sincronizar `localStorage` como se fosse fato.
4. Tornar a linha inteira de ingrediente tocável com controle ≥ 44 px.
5. Padronizar expiração de sessão em `useMiseEnPlace`, `useWeighing` e `useBlindMap` com o comportamento do kit.
6. Trocar `window.print` silencioso por fluxo de impressão com preview, impressora/status, confirmação, erro, retry e registro de reimpressão. Reusar o padrão do counter-agent/recibo quando a impressora térmica justificar.
7. Preservar códigos cegos; revelar mapa apenas com permissão, propósito e auditoria.

### WP-P1.5 — Relatórios e alertas operacionais, não caixas de dados

**Relatórios**

- Debounce + botão Aplicar; não buscar a cada tecla.
- Validar datas antes do request; explicar janela máxima.
- Reusar `FilterBar` e `ColumnPicker` do operator-kit.
- Paginação/cursor, sorting servidor-side, cabeçalho/colunas-chave sticky e export que respeita filtros.
- Deep-link de linha para passaporte da WO, pedido e receita autorizados.
- Tabelas responsivas por prioridade, não por encolhimento indiscriminado.
- Manter BI e gráficos analíticos na superfície de BI; relatório operacional responde “qual fornada e o que aconteceu”.

**Alertas**

- Filtrar audiência e capacidades no backend.
- Diferenciar visto, reconhecido e resolvido; registrar ator/hora. Reconhecer não pode apagar perigo ainda ativo.
- Classificar cada emissão como: alerta acionável, estado contextual, confirmação transitória ou evento de histórico. Somente o primeiro entra por padrão no sino e na contagem acionável.
- Projetar no backend as ações exatas de recuperação por tipo e ocorrência, não apenas um deep-link genérico.
- Oferecer uma ação primária recomendada e, no máximo, as alternativas realmente pertinentes; ordem e rótulos vêm da projeção.
- Pré-preencher WO, produto, data, posição, revisão, motivo e demais fatos já conhecidos. O operador não redigita contexto originado no alerta.
- Executar inline quando a ação for curta, segura e não ambígua; abrir o painel/fluxo exato quando precisar de revisão. Nunca despejar o operador numa página inicial para ele procurar o problema.
- Ação bloqueada continua visível quando isso ensina a recuperação, com motivo e providência concreta: atualizar, concluir pré-requisito ou pedir aprovação.
- Ação destrutiva mostra consequência e confirmação; autorização, revisão e idempotência seguem o mesmo contrato das ações iniciadas na tela de origem.
- Depois da ação, reconciliar objeto e alerta juntos. O alerta só some se a condição foi resolvida; caso contrário, atualiza texto, severidade e próximas ações.
- Deduplicar ocorrências da mesma causa, agregar quando isso reduz ruído e preservar a lista de objetos afetados. Alertas críticos persistem e escalam conforme política.
- Todo tipo sem ação possível precisa declarar por que é informacional e quem/o que poderá encerrá-lo; se não exige atenção, migrar para estado, confirmação ou histórico.
- Trocar dropdown artesanal por Popover/Sheet canônico, com Escape, foco e alvos ≥ 44 px.
- Buscar/realçar a WO exata; não apenas preencher uma string de busca.
- Contagem exibida precisa ser a contagem acionável para aquela persona.

**Contrato mínimo do alerta acionável**

```json
{
  "ref": "alert-ref",
  "kind": "production_late",
  "severity": "warning",
  "object": { "kind": "work_order", "ref": "wo-ref" },
  "summary": "Fornada passou do tempo esperado",
  "context": { "late_by_minutes": 12, "current_step": "Forno" },
  "actions": [
    {
      "ref": "open-qc",
      "label": "Revisar e concluir",
      "priority": "primary",
      "enabled": true,
      "href": "/expedite?work_order=wo-ref",
      "source_alert_ref": "alert-ref",
      "resolution_effect": "keeps_open"
    }
  ],
  "lifecycle": { "state": "open", "condition_still_active": true }
}
```

O exemplo é formato, não política fixa. Labels, ação recomendada, resolução e severidade devem resultar do tipo e dos fatos reais.

### WP-P1.6 — Completar configuração e passaporte no Unfold

Usar exclusivamente widgets, fieldsets, tabs, inlines e templates oficiais do Unfold conforme o playbook. Nenhum painel paralelo.

1. Expor no Admin de Shop todos os blocos de `ProductionConfig`: alertas, notificações/severidades, painel/TTL/tolerância e order matching, além do que já existe para sugestão/episódios.
2. Usar campos estruturados e validação `ProductionConfig`; nunca oferecer edição JSON crua.
3. Mostrar default herdado versus override da loja, unidade, faixa segura e efeito operacional.
4. Se passos estruturados forem aprovados, oferecer inline/form canônico para nome, duração, equipamento/posição, temperatura e checkpoint; migrar `steps_text` com compatibilidade.
5. Ampliar `WorkOrderAdmin` somente leitura com grade/defeito, batch refs, quantidades, fatos de forno, links de pedidos, atores, revisões e estado de reconciliação.
6. Criar passaporte de fornada no Admin por detalhe/tab canônico; ação operacional continua no Nuxt.
7. Adicionar checks de release: exatamente uma grade default, ao menos uma grade vendável sem markdown, referências ativas válidas e configurações coerentes.
8. Rodar `make admin`/checks canônicos e testes de widget/template antes do merge.

**Arquivos:** `shopman/shop/admin/shop.py`, `shopman/shop/admin/quality.py`, `shopman/shop/production_config.py`, `packages/craftsman/.../contrib/admin_unfold/admin.py`, testes Admin/canonicidade e migrações somente quando inevitáveis.

## 7. P2 — cobrir lacunas importantes do domínio

### WP-P2.1 — Pesagem executada e rastreável

O que existe hoje é uma ficha de pesos-alvo/impressão, não execução de pesagem. Implementar em duas etapas.

**Etapa manual assistida**

- sessão de pesagem por WO e estação;
- alvo versus peso real por ingrediente;
- tara, unidade, tolerância e estado dentro/fora;
- razão e aprovação para desvio fora da tolerância;
- ator, estação, timestamp, revisão e tentativa idempotente;
- seleção/registro do lote consumido ou delegação explícita ao FIFO do Stockman;
- etiqueta com estado de impressão, reimpressão e hash de conteúdo;
- requisito configurável para iniciar: advisory no piloto, bloqueante após provar processo.

**Etapa hardware**

- adapter de balança desacoplado do domínio;
- leitura estável, zero/tara, desconexão e fallback manual explícito;
- calibração, unidade e identificação do dispositivo;
- simulação e contrato de hardware testáveis sem balança real.

**Não fazer:** armazenar somente o último peso em JSON mutável; misturar leitura de balança com projeção; bloquear fábrica sem rollout advisory.

### WP-P2.2 — Passos estruturados e capacidade real de forno

1. Fazer discovery no chão de fábrica para saber se gargalo é forno, masseira, bancada ou pessoa.
2. Modelar recurso/posição/capacidade somente após confirmar necessidade; não criar scheduler genérico prematuramente.
3. Primeiro incremento: projeção servidor-side de sobreposição, posição ocupada e conflito por janela.
4. Segundo: reserva/planejamento com revisão e ação de resolver conflito.
5. Passos de receita estruturados alimentam presets, temperatura, equipamento e checkpoints.
6. Preservar snapshot dos passos na WO para não mudar uma fornada em andamento quando a receita for editada.

### WP-P2.3 — Assistência operacional avançada

P0 e P1 já devem produzir o “uau” fundamental: um trabalho ridiculamente fácil, seguro e previsível. Este pacote adiciona antecipação e assistência mais sofisticadas depois que os fatos de base estiverem estáveis; não é a etapa em que o omotenashi começa.

- **Próxima melhor ação:** rail/cartão destaca a ação mais urgente autorizada, com motivo e prazo; nunca oculta alternativas.
- **Sugestão explicável:** “12 unidades porque 8 estão em pedidos, 3 na previsão e 1 de segurança”, com disponibilidade e capacidade antes de aplicar.
- **Handoff de turno:** resumo gerado de WOs em risco, forno tocando, faltas, desvios e aprovações pendentes; cada item deep-linka ao fato.
- **Modo mãos ocupadas:** foco grande, atalhos deliberados e feedback sonoro/háptico compatível, sem depender só de cor/som.
- **Fechamento sem dúvida:** uma confirmação curta resume o que foi produzido, para onde foi, quais pedidos foram liberados e se ainda há pendência; nenhum efeito decorativo compete com o próximo trabalho.
- **Board Solari canônico:** animação apenas em TV, `prefers-reduced-motion` respeitado, atualização de linha sem glifos lidos por leitor de tela e nomes sem truncamento destrutivo.
- **Prevenção antes da correção:** alerta de atraso, conflito ou falta aparece no contexto da próxima decisão, não apenas no sino global, e oferece ali mesmo as ações pertinentes já preenchidas.

Cada item precisa de métrica: tempo até ação, toques por fornada, trocas de tela, redigitação, consultas fora do sistema, taxa de erro, reabertura, uso de force e satisfação dos operadores.

## 8. Especificação visual e de interação, pixel por pixel

Esta seção não transforma excelência em estética. Pixel, tipografia, movimento e hierarquia são ferramentas para reduzir tempo de leitura, erro, fadiga e hesitação. Uma tela visualmente impecável que ainda exige memória, redigitação, caça a contexto ou conferência paralela falha no plano.

### 8.1 Matriz de viewports suportados

| Contexto | Viewport de referência | Obrigatório | Critério |
|---|---:|---|---|
| Tablet de produção paisagem | 1024 × 768 | Primário | Todas as mutações sem zoom ou alvo sobreposto |
| Tablet retrato | 768 × 1024 | Primário | Rail colapsável, sheets e tabela utilizáveis |
| Gestor desktop | 1440 × 900 | Primário | Densidade confortável/compacta e múltiplas colunas |
| TV board | 1920 × 1080 e 1366 × 768 | Primário | Leitura a distância, sem interação necessária |
| Mobile gestor | 390 × 844 | Secundário | Login, consulta, alertas e relatórios essenciais; não fingir equivalência de chão de fábrica |
| Impressão térmica | 80 mm, área útil medida | Primário na preparação | Sem clipping; código e peso legíveis no papel real |

### 8.2 Tokens e geometria

- Gutter: 16 px no tablet/mobile e 24 px no desktop; respeitar safe areas.
- Ritmo: 4/8/12/16/24/32 px; exceção exige nome semântico.
- Alvo mínimo: 44 × 44 px; ação primária 48–56 px; distância mínima de 8 px entre ações destrutivas e comuns.
- Campos: mínimo 44 px; quantidade no chão de fábrica 52 px quando for entrada principal.
- Raio: `rounded-md` canônico; `rounded-full` somente chips/indicadores; hero/display deve documentar exceção.
- Focus ring visível com contraste ≥ 3:1; nunca usar a mesma ring como seleção.
- Texto normal e controles atendem WCAG AA; status não depende apenas de cor.
- Motion: transições funcionais 120–200 ms; sem movimento em `prefers-reduced-motion`; timers/alertas não piscam.
- Z-index: rail/header < popover < sheet/dialog < toast; mapa documentado no kit.
- Fonte: Instrument Sans na operação. O display Solari precisa declarar/carregar sua fonte intencional; hoje `Oswald` não está configurada e cai em fallback.

### 8.3 Especificação por rota

#### Login/gate global

- Não renderizar conteúdo protegido interativo antes de resolver identidade.
- Preferir página de autenticação real; se overlay, usar `role=dialog`, `aria-modal`, foco preso e fundo `inert`.
- Primeiro foco no usuário/código; erro ligado ao campo e anunciado uma vez.
- Submit ≥ 44 px, busy não muda largura, Enter seguro, sem dupla submissão.
- Estados: carregando sessão, login, credencial inválida, rate-limit com tempo, estação bloqueada, sessão expirada e backend indisponível.

#### `/plan` e `/`

- Header sticky, controles de data/busca/filtros em barra adaptável.
- Primeira coluna sticky e sombra discreta apenas quando houver overflow.
- Célula de ação ≥ 44 px; quantidade e unidade nunca separadas visualmente.
- Linha expande múltiplas WOs com ref, estado, quantidade, posição, pedidos e revisão.
- Estados: skeleton, vazio global, vazio filtrado, degraded suggestion, stale, offline, conflito, erro parcial de estoque, busy por linha e sucesso reconciliado.
- Longos: nome de produto em duas linhas antes de tooltip; ref não substitui nome; número não trunca.

#### `/mise-en-place`

- Navegação de data sticky; grupo de receita dobrável com subtotal.
- Ingrediente: checkbox/estado ≥ 44 px, nome, quantidade, unidade, produtos/fontes e tolerância quando houver.
- Alteração do plano mostra banner de revisão e diferencia itens novos, alterados e removidos.
- Área de etiquetas mostra preview 1:1 lógico, impressora, status e retry.
- Mapa cego nunca aparece por acidente em impressão, cache ou leitor de tela sem permissão.

#### `/expedite`

- Cartão inteiro ≥ 72 px; ação primária evidente; ref/posição/pedidos acessíveis.
- Timer com números tabulares, rótulo e estado; cor é redundante a ícone/texto.
- Cartões atrasados continuam legíveis, sem opacidade que derrube contraste.
- QC em Sheet no tablet e Dialog/side panel no desktop, mantendo contexto.
- Confirmação final exibe destino e quantidade de cada partição; botão destrutivo separado.

#### `/board`

- Renderer de TV, sem rail e sem controles minúsculos.
- Nome deve usar largura responsiva/linhas controladas; nunca cortar informação necessária por constante de caracteres.
- Uma atualização é uma unidade acessível; caracteres animados ficam `aria-hidden`.
- Leitor de tela recebe somente a linha assentada. `aria-live` não se repete por caractere.
- Indicador de conexão/última atualização discreto; conteúdo anterior permanece durante retry.
- `prefers-reduced-motion` troca split-flap por transição instantânea.

#### `/reports`

- FilterBar dobra em Sheet no mobile/tablet estreito.
- Tabela desktop com sticky header/colunas; mobile mostra cartões apenas para dimensões prioritárias.
- Loading preserva geometria; erro parcial identifica qual bloco falhou.
- Export exibe preparando, pronto, expirado, falhou e retry.
- Toda linha tem foco/ação acessível para passaporte.

#### `/menuboard`

- Removida da superfície Produção ou convertida em entrada explícita para o board canônico por ref.
- Nenhum critério visual poderá justificar permanência pública ou leitura do storefront.

### 8.4 Estados transversais que devem ter screenshot e teste

Para cada rota/componente aplicável: default, hover, focus-visible, pressed, selected, disabled com razão, busy, sucesso, validação, conflito, forbidden, vazio, erro parcial, erro total, stale, offline, sessão expirada, texto longo, número grande, zoom 200%, fonte maior, reduced motion, light/dark quando suportado e impressão. Produção é light-first; dark só é obrigatório onde o board/display o define.

### 8.5 Linguagem operacional

- Usar consistentemente: Planejamento, Preparação, Produção e Expedição.
- Distinguir `planejado`, `iniciado/enfornado`, `produzido`, `vendável` e `perda`.
- Em QC, trocar “previstos” por “enfornados” ou “entraram” quando a âncora for quantidade real iniciada.
- Botão declara resultado: “Iniciar 24 un.”, “Registrar 3 un. como perda”, “Concluir e criar 2 lotes”.
- Erro sempre contém ação de recuperação; “algo deu errado” sozinho é proibido.

### 8.6 Orçamentos de esforço e prova de omotenashi

Antes de redesenhar, observar ao menos um turno de Cozinha e um de Gerência, sem conduzir o operador, e registrar por tarefa: duração, toques, rolagens, mudanças de tela, digitação, consulta a papel/WhatsApp/colega, dúvidas, retornos, erros e sensação de certeza ao terminar. Dados sensíveis não entram na gravação.

Depois do protótipo e depois do piloto, repetir exatamente as mesmas tarefas. Os valores finais serão fixados pelo baseline, mas os seguintes limites de desenho já valem:

| Tarefa comum | Orçamento de experiência alvo |
|---|---|
| Entender o que fazer agora | Próxima ação e motivo visíveis sem navegar nem abrir o sino |
| Aplicar sugestão sem exceção | Uma revisão contextual e uma confirmação; nenhum número redigitado |
| Ajustar plano | Editar na linha, ver impacto antes de salvar e permanecer no mesmo contexto |
| Iniciar fornada comum | Produto/WO/quantidade/posição já preenchidos; no máximo uma decisão necessária |
| Avançar passo comum | Um toque com feedback imediato e reconciliação; sem modal ornamental |
| Armar timer | Preset correto já sugerido pela receita/passo; um toque para o caso comum |
| Concluir fornada sem desvio | Quantidade iniciada já presente; confirmar resultado e destino numa única superfície |
| Registrar exceção | Sistema apresenta opções válidas, impacto e autoridade requerida; nada de procurar regra fora |
| Resolver conflito | Preserva entrada, mostra exatamente o que mudou e permite reaplicar conscientemente |
| Retomar após interrupção | Volta à WO, passo e formulário corretos; não pede reconstrução mental |
| Handoff de turno | Pendências e riscos vêm prontos, ordenados e com deep-link; zero compilação manual |
| Confirmar sucesso | Mostra estoque, pedidos, lotes e pendências resultantes; nenhuma conferência paralela |

**Critérios transversais**

- Caso comum é curto; exceção recebe espaço e explicação, sem poluir o caso comum.
- Informação conhecida aparece pré-preenchida e bloqueada quando não deve ser redecidida.
- Unidade, precisão, posição, lote e WO acompanham o operador; nunca dependem de memória de outra tela.
- A próxima tela preserva produto, data, filtros e origem da navegação.
- Undo é oferecido para ações reversíveis; confirmação é reservada a consequências reais.
- Toda espera acima de 300 ms dá feedback; operações longas explicam se é seguro sair.
- Toast não é o único lugar de uma informação necessária para continuar.
- Interrupção, timeout ou sessão vencida preserva rascunho seguro e oferece retomada após autenticar.
- O piloto só aprova o fluxo se reduzir esforço observado e aumentar confiança, mesmo que a preferência visual seja alta.

## 9. Observabilidade, auditoria e SLO

Instrumentar sem registrar PIN, segredo, conteúdo sensível ou payload integral desnecessário.

**Backend**

- duração e queries por projeção;
- ação por tipo, resultado, latência, conflito, retry e chave idempotente hashada;
- override/force por executor, aprovador e razão categorizada;
- falhas/reconciliação do Stockman e links de pedido;
- cobertura de fatos de forno;
- idade de projeção no momento da ação;
- perda, markdown, variação de rendimento e pesagem fora da tolerância;
- tempo alerta → ação → resolução, taxa de uso da ação sugerida, alertas sem ação e reincidência após ação.

**Frontend**

- route/action/WO ref segura, versão do contrato e estação;
- offline/stale/session-expired;
- falha de impressão/balança/áudio/wake lock;
- Web Vitals relevantes e long tasks em tablet de referência;
- erro reportado pelo plugin compartilhado com correlação do request;
- duração, toques, trocas de rota, abandono e recuperação dos fluxos críticos, em telemetria agregada e sem conteúdo sensível.

**SLOs a ratificar pelo baseline**

- nenhuma duplicação de WO/lote por retry;
- 100% das mutações irreversíveis com ator, revisão e idempotência;
- 100% dos overrides com justificativa e aprovador quando exigido;
- p95 da projeção principal dentro do orçamento acordado;
- stale detectado antes de permitir ação;
- alerta crítico não desaparece apenas por “ack”;
- 100% dos tipos de alerta acionável expõem ao menos uma providência pertinente ou uma recuperação explicitamente bloqueada com motivo.

Criar dashboards e alertas apenas para sinais acionáveis. O detalhamento analítico permanece no BI.

## 10. Estratégia de testes e prova de excelência

### 10.1 Backend

- serializers: tipos, booleanos, decimais, datas, filtros e mensagens;
- matriz RBAC/estação com testes negativos;
- transações concorrentes reais em PostgreSQL;
- invariantes de quantidade/partição com casos gerados e limites;
- snapshot da receita e `batch_size` após edição da receita;
- desconhecido/inativo em catálogo de qualidade;
- perda total e zero entrada vendável;
- links de pedido em cancelar/concluir/estornar/retry;
- idempotência e falha parcial de stock/alerta/forno;
- budgets de query com 1, 10 e 100 WOs;
- schema export e compatibilidade.
- catálogo de alertas: cada tipo prova classificação, audiência, ações, autorização, deduplicação e transição após agir.

### 10.2 Frontend unitário/integração

- toda action projection renderizada e desabilitada com razão correta;
- conflitos preservam input e reconciliam revisão;
- nenhuma escolha automática em múltiplas WOs;
- virada de meia-noite sem reload;
- polling desmonta sem ressuscitar, aplica jitter e trata promise;
- timer sobre suspensão, reload, estação diferente e expiração;
- QC teclado/foco/dirty state/força de descarte;
- agregação de compromissos soma refs repetidas;
- sessão expirada uniforme em todos os composables;
- reduced motion e anúncio único no SplitFlap;
- alerta renderiza ação recomendada, preserva contexto, explica bloqueio e reconcilia o lifecycle após sucesso/conflito/erro.

### 10.3 Browser ponta a ponta

Substituir o mock-only atual por dois níveis: mock determinístico para estados visuais e Django semeado para contrato real.

Projetos Playwright:

- Chromium tablet 1024 × 768;
- Chromium tablet retrato 768 × 1024;
- Chromium desktop 1440 × 900;
- TV 1920 × 1080;
- mobile gestor 390 × 844;
- ao menos WebKit/Firefox no smoke de login/consulta, se suportados em operação.

Fluxos: login/lock, cada persona, planejar, editar, iniciar, avançar, timer, QC misto, perda total, shortage/override, estorno, duas WOs, relatório/passaporte, alerta → ação inline/fluxo exato → resolução, ação de alerta bloqueada, deduplicação, offline/reconnect, sessão vencida, conflito entre contexts, resposta perdida, dia virando e rota inexistente.

### 10.4 Acessibilidade e visual

- axe automatizado em todas as rotas/estados críticos;
- jornada 100% teclado e switch;
- VoiceOver/NVDA para login, rail, tabela, cartões, sheets, timer, alertas e board;
- zoom 200%, texto aumentado, alto contraste e reduced motion;
- snapshots nos viewports da seção 8 com tolerância pequena e revisão humana;
- teste de cópia longa, português, número de quatro/cinco dígitos e unidade decimal.

### 10.5 Hardware e caos

- impressão real em papel 80 mm: margens, densidade, código, reimpressão e papel ausente;
- balança real/simulador quando WP-P2.1 entrar;
- tablet suspenso, Wi-Fi intermitente, restart do deploy, SSE interrompido;
- timeout antes e depois do commit;
- API version mismatch;
- falha de downstream depois da conclusão de domínio;
- estação revogada durante turno.

## 11. Rollout, migração e rollback

1. **Feature flags servidor-side:** action contract, total loss, novo QC, checklist compartilhado, pesagem e capacidade. Flags não podem relaxar segurança.
2. **Dual-read, nunca dual-write:** durante migração, comparar projeção antiga/nova em telemetria; somente um writer.
3. **Backfill auditável:** snapshots/revisões/pesagens/passaportes precisam de dry-run, contagens antes/depois e comando idempotente.
4. **Piloto:** uma estação e uma equipe; modo advisory para pesagem/capacidade; observar um ciclo completo e uma troca de turno.
5. **Expansão:** 10% → 50% → 100% das estações com gate por métricas, não por calendário.
6. **Rollback:** desligar UI nova e voltar ao reader anterior sem reverter eventos já gravados. Migração de dados é backward-compatible durante toda a janela.
7. **Menuboard:** provisionar refs/credenciais e validar TVs antes de remover redirect; não restaurar a rota pública como rollback.
8. **Pós-release:** checar headers no host, erros, conflitos, duplicações, p95, reconciliações, perdas e feedback do turno por pelo menos sete dias operacionais.

## 12. Manifesto de cobertura de código

O executor deve abrir, classificar e registrar decisão para cada arquivo abaixo: **alterar**, **preservar com teste**, **mover/consolidar** ou **aposentar**. “Sem mudança” precisa de justificativa. Arquivo gerado é alterado somente pelo gerador.

### 12.1 Produção Nuxt — shell e infraestrutura

| Arquivo | Plano de cobertura |
|---|---|
| `surfaces/production-nuxt/nuxt.config.ts` | headers, fonte display, env fail-fast, route policy |
| `app/app.vue` | gate real/inert, probes por rota, menuboard retirement |
| `server/api/v1/[...path].ts` | cache/security/version/error contract |
| `app/assets/css/tailwind.css` | tokens, radius, touch, reduced motion, print |
| `package.json` / lock | scripts CI e dependências somente se necessárias |
| `playwright.config.ts` | matriz tablet/desktop/TV/mobile e server real |
| `vitest.config.ts`, `eslint.config.mjs`, `tsconfig.json`, `ui-thing.config.ts` | gates e aliases; preservar disciplina |
| `README.md`, `tests/e2e/README.md`, `public/robots.txt` | arquitetura, autenticação, rotas e execução corretas |
| `public/favicon.ico`, `.gitignore` | revisar branding/artefatos; não alterar sem necessidade |

### 12.2 Rotas

| Arquivo | Plano de cobertura |
|---|---|
| `app/pages/index.vue` | grade operacional canônica e contexto de data |
| `app/pages/plan.vue` | composição de planejamento, sem wrapper opaco |
| `app/pages/mise-en-place.vue` | checklist revisionado, pesagem/print e datas |
| `app/pages/expedite.vue` | múltiplas WOs, oven facts, timer e entrada QC |
| `app/pages/board.vue` | TV acessível, responsiva, realtime e estação |
| `app/pages/reports.vue` | filtros compartilhados, paginação e drilldown |
| `app/pages/menuboard.vue` | aposentar ou mover renderer ao menuboard canônico |

### 12.3 Componentes de domínio

| Arquivo | Plano de cobertura |
|---|---|
| `OperatorLogin.vue` | foco, rate limit, busy, erros e modal/page semantics |
| `ProductionHeader.vue` | rail/nav responsivo, 44 px, rota/capacidade |
| `ProductionStageGrid.vue` | actions, rev, múltiplas WOs, filtros, tabela e estados |
| `QcCloseScreen.vue` | verdade de partição/perda, preview, foco e precisão |
| `ShortageDialog.vue` | impacto, aprovação/razão e tentativa estável |
| `AlertsBell.vue` | audiência, ack/resolução, popover/sheet e deep-link |
| `SplitFlap.vue` | a11y, reduced motion, overflow e fonte |
| `WeighingLabels.vue` | conteúdo versionado, geometria e status de impressão |

### 12.4 UI local

Auditar `app/components/Ui/Alert/**`, `Card/**`, `Dialog/**`, `Popover/**`, `Sheet/**`, `Tooltip/**`, `Badge.vue`, `Button.vue`, `Input.vue`, `Separator.vue`, `Sonner.vue` e `Textarea.vue`. Comparar com o kit e com os outros Nuxt. Consolidar componentes realmente genéricos no `operator-kit`; remover wrappers divergentes; preservar primitivos gerados quando corretos. Testar tamanho, foco, Escape, portal, scroll lock, descrição, disabled e contraste.

### 12.5 Composables, apresentação e tipos

| Arquivo | Plano de cobertura |
|---|---|
| `useAdaptivePoll.ts` | unmount, jitter, backoff, visibilidade; possível extração |
| `useAlerts.ts` | escopo, ações e sessão |
| `useBlindMap.ts` | permissão, auditoria e sessão |
| `useBoardPages.ts` | paginação/overflow do display |
| `useFlapClack.ts` | áudio permitido, reduced motion e cleanup |
| `useMiseEnPlace.ts` | rev/freshness, sessão e checklist |
| `useOvenFacts.ts` | idempotência, erro e reconciliação |
| `useOvenTimers.ts` | estação/run ref, suspensão, wake lock e alarme |
| `useProductionBoard.ts` | cliente gerado, rev, action contract |
| `useProductionForecast.ts` | degraded/explicabilidade/frescor |
| `useProductionKds.ts` | cliente gerado, ação resolvida, conflict |
| `useProductionManagement.ts` | capacidade/approval e cliente gerado |
| `useProductionReports.ts` | filtros, cursor, export e cancelamento |
| `useQcKiosk.ts` | action contract, partições e total loss |
| `useReportsAccess.ts` | eliminar probe global/duplicado |
| `useWeighing.ts` | contrato tipado e futura sessão de pesagem |
| `app/presentation/production.ts` | tons/tokens, agregação correta e nenhuma política |
| `app/presentation/qc.ts` | linguagem, unidade e estados derivados de fatos |
| `app/presentation/reports.ts` | colunas/datas e deep-links |
| `app/types/production.ts` | eliminar duplicatas manuais |
| `app/generated/productionContract.ts` | gerar; nunca editar à mão |
| `app/utils/api.ts` | envelope, conflict, retry seguro e correlation |
| `app/utils/operatorSession.ts` | convergir com operator-kit |

### 12.6 Testes Nuxt

Todo arquivo atual em `tests/*.test.ts`, `tests/components/**` e `tests/composables/**` deve receber classificação. Manter teste comportamental útil; reescrever assertions que fixam contrato errado; criar coverage para todos os estados da seção 8. Os E2E `guards.spec.ts`, `resilience.spec.ts` e `mockBackend.mjs` devem deixar de tratar menuboard público como sucesso e cobrir o contrato Django real.

### 12.7 Backend Django/Craftsman/Stockman/Orderman

| Área/arquivo | Plano de cobertura |
|---|---|
| `shopman/backstage/api/operations.py` | serializers, autorização, actions, rev/idempotência e erros |
| `api/_production_filters.py` | validação estrita de filtros/datas |
| `api/alerts.py`, `services/alerts.py`, `models/alerts.py` | audiência, ack/resolução e auditoria |
| `backstage/permissions.py`, `api/permissions.py`, `station_trust.py` | matriz efetiva usuário + estação |
| `projections/production.py` | assembler em lote, actions, sem classes UI, cálculo correto |
| `services/production.py` | transações, quick finish, step events, overrides |
| `models/oven_run.py`, `sweep_stale_oven_runs.py` | revisão/idempotência e recuperação |
| `contracts.py`, `export_production_schema.py` | schema completo e geração CI |
| `shopman/shop/services/production.py` | lifecycle, snapshot, bridge e expected_rev |
| `services/quality.py`, `models/quality.py` | catálogo estrito, partições e perda total |
| `production_config.py`, `production_lifecycle.py` | configuração, estados/eventos necessários |
| `handlers/production_order_sync.py`, `services/operator_orders.py` e serviços de pedido | invariantes e reconciliação de vínculos |
| handlers/services Stockman | consumo/saída exatamente uma vez e batch refs |
| `packages/craftsman/.../scheduling.py`, `execution.py` | propagar garantias existentes |
| `models/work_order.py`, `work_order_event.py`, `work_order_item.py` | rev/eventos/qualidade/passaporte/query behavior |
| `packages/craftsman/.../contrib/admin_unfold/admin.py` | Admin canônico de receita/WO |
| `shopman/shop/admin/shop.py`, `admin/quality.py` | config/catálogos canônicos |
| menuboard projection/view/template/JS/access/urls/tests | única TV canônica, trust e SSE |

### 12.8 Operator kit, infraestrutura e documentação

- Revisar/reusar `OperatorRail`, `FilterBar`, `ColumnPicker`, `OfflineBanner`, `useConnectivity`, `useOperatorSession`, `useStation*`, `retryBackoff`, `httpError`, `eventStream`, `djangoProxy`, `djangoBaseUrl` e `errorReporter`.
- Se headers forem compartilhados, adicionar utilitário e testes no kit, consumido por todos os Nuxt operacionais.
- Revisar `.env.example`, `config/settings.py`, `config/urls.py`, deploy DigitalOcean, `scripts/check_release_readiness.py`, checks de deploy e URLs de navegação.
- Atualizar `docs/decisions/adr-012`, ADR-014, ADR-017, ADR-018 apenas se o contrato mudar; adicionar ADR para novos fatos/estado de produção.
- Atualizar `docs/engineering/backstage-design-system.md`, `docs/guides/backstage-accessibility.md`, realtime, RBAC, comandos, settings, status e README. Remover referências a console aposentado ou rota pública inexistente.
- Preservar o cânone Unfold e executar `scripts/check_unfold_canonical.py`/gate equivalente.

## 13. Backlog priorizado de defeitos/decisões

| ID | Prioridade | Resultado exigido |
|---|---|---|
| PROD-001 | P0 | Actions/RBAC finos governam projeção e endpoint |
| PROD-002 | P0 | Toda mutação usa rev + idempotência |
| PROD-003 | P0 | Quick finish nunca duplica/deixa WO órfã |
| PROD-004 | P0 | Step e oven facts transacionais/auditáveis |
| PROD-005 | P0 | Forçar requer capacidade, razão e aprovação definida |
| PROD-006 | P0 | Perda total é resultado real, não void |
| PROD-007 | P0 | Snapshot/started qty alimentam mise/pesagem/QC |
| PROD-008 | P0 | Referência de qualidade inválida é rejeitada |
| PROD-009 | P0 | Menuboard paralelo público é removido/convergido |
| PROD-010 | P0 | Headers/cache/env de produção são seguros |
| PROD-011 | P1 | Projeções têm query budget e freshness |
| PROD-012 | P1 | Múltiplas WOs nunca são escolhidas implicitamente |
| PROD-013 | P1 | Stale/offline bloqueia writes e oferece recuperação |
| PROD-014 | P1 | Alertas são escopados, acionáveis no contexto e ack ≠ resolve |
| PROD-015 | P1 | Relatórios validam, paginam e drilldown |
| PROD-016 | P1 | Checklist e impressão declaram sua verdade/estado |
| PROD-017 | P1 | Gate, teclado, foco, touch e motion passam AA |
| PROD-018 | P1 | Configuração completa e passaporte usam Unfold |
| PROD-019 | P2 | Pesagem real, tolerância, lote e impressão auditada |
| PROD-020 | P2 | Passos/presets/capacidade refletem a fábrica real |
| PROD-021 | P2 | Próxima ação, handoff e sugestão explicável entregam “uau” mensurável |

## 14. Definition of Done — excelência irreprimível

O programa só termina quando:

- os 21 itens do backlog têm teste e evidência ou decisão explícita de não fazer;
- nenhum endpoint de produção aceita ação não projetada/autorizada;
- nenhuma mutação irreversível opera sem revisão, idempotência e ator;
- invariantes sobrevivem a concorrência, timeout, retry e falha parcial;
- quantidades, perdas, grades, lotes e vínculos fecham no ledger/passaporte;
- não há dois menuboards nem rota pública acidental;
- headers e cache seguros são verificados no host implantado;
- query budget e SLO passam com dataset representativo;
- tablet, desktop, TV, mobile secundário e impressão passam pela matriz visual;
- teclado, leitor de tela, zoom, contraste e reduced motion passam;
- todas as configurações administrativas usam Unfold canônico e `make admin` passa;
- documentação, schema gerado, release checks e runbooks descrevem o sistema real;
- um piloto de turno completo fecha sem duplicação, ambiguidade ou workaround externo;
- os fluxos críticos demonstram redução mensurável de toques, mudanças de tela, redigitação e consultas externas em relação ao baseline;
- operadores retomam interrupções e resolvem exceções sem reconstruir contexto nem perguntar qual é o próximo passo;
- nenhum alerta acionável termina em informação passiva ou navegação genérica: oferece a providência pertinente, preserva contexto e só encerra quando a causa for resolvida;
- operadores conseguem explicar o que ocorreu em qualquer fornada a partir de um único passaporte.

Esse é o portão final: não apenas uma interface bonita, mas uma superfície cuja autorização, fatos, estoque, qualidade, experiência e auditoria contam a mesma história sob pressão.
