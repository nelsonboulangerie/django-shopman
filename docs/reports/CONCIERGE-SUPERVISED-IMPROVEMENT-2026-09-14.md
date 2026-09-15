# Concierge — melhoria supervisionada por conversas

**Base inicial:** `196219038f53a0dabcac8ffdec07e6be1a3dee51`. **Main revalidada:**
`ae52f96b72cbbffbc5541b61f4c560e880474586`. **Base de composição do schema:**
`13326bee3a4b11b202859e39a6817ee729001cc5`, que contém a cadeia reservada
`0053_marketing_delivery_identity → 0054_disable_remote_auto_confirmation →
0055_catalog_snapshot_binding`, em worktree e branch exclusivos
`codex/concierge-conversation-learning-20260914`. O checkout principal e mudanças
de terceiros não foram alterados.

**Estado:** implementação local testada; homologação ManyChat, captura de clientes
reais, piloto e rollout não executados. A configuração de produção e o flow
publicado não foram modificados por esta fatia.

## Decisão

“Aprender” significa construir um ciclo auditável de melhoria supervisionada:
observar casos, identificar padrões, propor respostas, revisar contra fatos
canônicos e publicar manualmente. Não significa treinar um modelo com transcrição
bruta, copiar a resposta mais frequente nem alterar o prompt sozinho.

O corpus bruto continua em `ConversationMessage`. O conhecimento aprovado
continua em `FAQEntry`; `is_published=false` é o default e o histórico existente
preserva a autoria editorial. Não foram criados inbox, fila, regra comercial,
dataset permanente ou base de conhecimento paralelos.

## Execução por WP

| WP | Alteração/evidência desta fatia | Estado |
|---|---|---|
| WP00 | SHA, owners, limitações ManyChat e matriz abaixo revalidados no código atual | concluído para esta fatia |
| WP01 | Mesmo endpoint/adapter autenticado; modo de servidor exclusivo `observe`/`assist`; body não escolhe modo/autor | testado localmente |
| WP02 | `automation_eligible=false` persistente exclui observações de claim, replay, recovery e contexto | testado localmente |
| WP03 | Observação cancela inclusive reply/ACK já preparado, sem envio nem alerta ao operador | testado localmente; provider não homologado |
| WP04–WP06 | Nenhuma ferramenta comercial, sacola, pedido, pagamento ou projection ganha novo writer | preservado por desenho; sem nova capacidade |
| WP07 | Observação não altera posse/handoff nem relógios de recovery; resposta manual ManyChat permanece fora do corpus automático | parcial; evento oficial da equipe é gate G02 |
| WP08 | Escopo continua provider+account+channel+subject; redação pré-insert, envelope mínimo e acesso dedicado | mecanismos testados; G04 pendente |
| WP09 | 316 regressões de Concierge verdes; avaliação humana/Unread/latência não medida | técnico parcial; G06 pendente |
| WP10 | Migração expand-only `0056` encadeada à `0055`; rollback por modo/switch; limpeza automática por prazo e pontual por subject | grafo vazio e compatibilidade local verdes; deploy pendente G07 |

## Achados atualizados

| Tipo | Achado | Estado/prova |
|---|---|---|
| defeito comprovado | `allowed_subjects` rejeitava clientes comuns antes de persistir; não havia observação passiva | corrigido pelo caminho `observe`, sem ampliar a allowlist de atendimento |
| risco comprovado | inbound passivo com `consumed_by=NULL` poderia acordar após mudança de coorte | eliminado por `automation_eligible=false` e filtros de history/recovery |
| risco comprovado | fase de observação coexistia com atendimento ativo por omissão do header | modo `observe` bloqueia server-side fila, modelo e saída mesmo com chave/switch ativos |
| risco comprovado | replay do mesmo ID observado poderia virar atendimento após troca de fase | conflito persistente impede enqueue; regressão cobre observe→assist |
| risco comprovado | observação alterava `last_inbound_at` e prioridade de recovery | captura não toca relógios operacionais; tempo observado vem da mensagem |
| lacuna comprovada | transcrição não tinha prazo de retenção nem rotina de descarte | captura nova recebe prazo; worker periódico remove texto, binding e conversa vazios |
| risco comprovado | perfil e IDs eram duplicados no envelope observado | perfil, subject, event, correlation e payload bruto não são copiados; `external_id` guarda apenas o digest de um ID verificado |
| risco comprovado | permissão ampla de conversa expunha observações | papel comum não vê conversa observada nem linha observada em conversa mista; permissão dedicada libera curadoria |
| risco comprovado | texto bruto era duplicado em `text` e `content` | redação local ocorre antes do insert; `content=[]`; boundary canônico de PII é reutilizado |
| risco comprovado | observação podia existir sem prazo por writer futuro | constraint de banco exige `retention_until` quando `automation_eligible=false` |
| risco comprovado | ACK de handoff preparado ignorava o modo de observação | saída vira `observation_mode_cancelled`, sem provider/alerta e sem retry posterior |
| limite do fornecedor | API pública ManyChat não fornece evento de resposta manual nem histórico incremental | respostas da equipe não são prometidas; scraping/polling proibidos |
| defeito de hipótese | Rules desta conta não expõem Last Text Input/última interação como trigger de campo do sistema | inspeção UI: somente E-mail e Celular; alternativa por tag definida |
| hipótese de homologação | Action interna de tag + Rule silenciosa preservam Unread/Open/assignment | External Request isolado do Default Reply; exige ensaio com Pablo antes de habilitar |
| decisão humana | base legal, aviso, acesso, retenção final e coorte real | G04 pendente; gates fechados por default |
| decisão humana | resposta proposta merece FAQ e pode ser publicada | revisão editorial; toda FAQ nasce draft |

## Jornadas antes/depois

| Jornada | Antes no SHA base | Depois implementado | Prova ainda necessária |
|---|---|---|---|
| pergunta de cliente comum | não persistida pela Concierge | transcrição passiva com prazo, sem resposta/fila | trigger real e cobertura ManyChat |
| Pablo conversa durante observação | entrada e resposta ativas no modo de ensaio anterior | modo `observe` bloqueia a Concierge para Pablo e todos os demais | ensaio de zero resposta no aparelho |
| operador abre Inbox | fluxo atual | nenhum comando Open/Closed/Read/assignment criado | confirmar Unread no Inbox real |
| pergunta repetida vira melhoria | sem ciclo formal | evidência pode sugerir FAQ draft; fato canônico continua soberano | revisão de casos reais autorizados |
| cliente pede descarte | observação não existia | remoção por connection+subject sem export cru | procedimento/owner/SLA G04 |
| resposta manual da equipe | visível apenas no ManyChat | continua não ingerida por falta de evento oficial | contrato ManyChat privado ou provider direto |

## Migração e rollback

A migration local adiciona permissão de curadoria, dois campos e uma constraint:
`automation_eligible=true` para mensagens existentes e `retention_until=NULL`.
Workers antigos ignoram os campos; a capacidade de observação permanece desligada
até o novo código estar implantado. Não há backfill de identidade, autoria ou
retenção histórica.

O arquivo usa o número coordenado `0056` e depende de
`0055_catalog_snapshot_binding`. A composição-base contém os models
correspondentes à `0055`; a migration não foi copiada isoladamente. O PR #634,
com `0053_marketing_delivery_identity`, já integra `origin/main`; o PR #680 e a
`0055` ainda precisam integrar essa base antes desta branch. A publicação continua
dependendo dessa ordem real e de G07, sem folha irmã ou dependência presumida.

Rollback operacional:

1. definir `CONCIERGE_OPERATION_MODE=assist` e `CONCIERGE_OBSERVATION_ENABLED=false`;
2. desligar a Rule e remover as duas ações da tag técnica no ManyChat;
3. manter a rotina de limpeza até o prazo aprovado ou executar descarte por subject;
4. preservar mensagens ativas, receipts, pedidos e o flow de atendimento atual;
5. não replayar observações nem convertê-las em entradas ativas.

O downgrade de schema não é necessário para conter a capacidade. A remoção dos
campos só pode ocorrer depois do descarte aprovado e da janela G07.

## Gates pendentes

- **G02:** evento oficial para resposta humana e prova de cobertura/ACK do trigger.
- **G04:** responsável de dados, base legal, aviso/versionamento, concessão do papel
  de curadoria, retenção, auditoria de consulta, backups/restores, prevenção de
  reingestão, descarte e tratamento de solicitações do titular. A redação por
  padrões reduz exposição, mas não certifica ausência universal de PII livre.
- **G06:** ensaio com Pablo de zero resposta, Unread/Open/assignment, falha e
  latência; depois amostra humana autorizada.
- **G07:** release SHA, alvo, numeração integrada da migration/backup,
  janela e rollback.

Sem esses gates, observar todos os clientes continua desativado. O ensaio já
publicado para Pablo permanece no caminho `assist`; esta fatia não o alterou nem
autoriza coleta geral.

## Evidência executada

```text
pytest test_concierge_observation.py
25 passed in 12.61s

todos os módulos test_concierge*.py
316 passed, 25 skipped in 31.35s

test_maintenance_worker.py
14 passed in 13.90s

make admin (settings, venv e PYTHONPATH isolados)
Unfold canonical gate passed; 270 passed in 53.10s

ruff (arquivos alterados)
All checks passed

makemigrations --check --dry-run
No changes detected

make test-migrations (SQLite exclusivo desde o bootstrap)
3 passed; 2 skips pré-go-live esperados
```

Os testes usam banco e adapters isolados, sem credencial ou provider externo. Não
há caso de concorrência nesta fatia; por isso SQLite não é apresentado como prova
de lock ou throughput. A homologação ManyChat não é substituída por mock. Duas
invocações intermediárias do gate foram descartadas: uma durante a troca de nome,
sem o parent final, e outra reutilizou a conexão SQLite local já materializada. A
prova registrada acima inicializa o settings exclusivo antes do Django e constrói
o grafo final do zero.
