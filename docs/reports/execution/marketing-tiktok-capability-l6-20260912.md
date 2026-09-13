# Evidência MKT-CAP-01 + TikTok — L6 e R01–R15

Data: 2026-09-12. Ambiente: worktree/branch isolados, banco efêmero de teste,
adapters simulados e nenhuma escrita externa. Autorização humana: exercício L6 e
matriz R01–R15 aprovados; descarte do legado e ativação de jobs em produção ficaram
explicitamente fora do escopo e conservam gates próprios.

## Resultado executivo

O núcleo agora persiste a identidade canônica
`{platform, delivery_kind, format}` do artefato ao outbox e ao ledger. Um catálogo
único alimenta validação, defaults e a projeção do formulário. O schema novo é
fechado; registros históricos continuam legíveis sem serem reescritos durante a
leitura.

O adapter TikTok Direct Post para foto foi implementado atrás de uma flag falsa por
padrão e fora do catálogo selecionável. Portanto, ele pode ser testado hermeticamente,
mas ainda não pode criar uma consequência TikTok pelo cockpit nem alcançar a rede em
configuração normal. Isso preserva a decisão “sem novas consequências durante a
migração”. OAuth, revisão do app, auditoria Direct Post e canário público são gates
posteriores.

## Exercício L6 — ciclo da migração com legado vivo

O cenário cria, no estado anterior à migração, um artefato Instagram histórico cujo
formato explícito é `feed`, seu outbox e seu destino. Em seguida:

1. aplica `0053_marketing_delivery_identity`;
2. comprova `publication/feed` no outbox e no destino, sem cair no default `story`;
3. valida as constraints novas;
4. retorna ao estado anterior e reaplica até a folha atual do grafo.

Aceite: nenhum erro de migração, formato histórico preservado e árvore de migrations
restaurada. O teste executável é
`test_delivery_identity_migration_reverses_and_reapplies_cleanly`.

## Matriz R01–R15 executada fora de produção

| Risco | Prova/controle | Resultado |
|---|---|---|
| R01 — plataforma desconhecida criar efeito | catálogo fechado e validação de identidade | aprovado |
| R02 — modalidade inferida incorretamente | `delivery_kind` obrigatório para escrita nova | aprovado |
| R03 — formato silenciosamente trocado | formato selado; `feed` legado preservado no L6 | aprovado |
| R04 — opção sem efeito chegar ao provider | schema de `provider_fields` fechado | aprovado |
| R05 — hash histórico mudar na leitura | identidade omitida em payloads schema 1–3 | aprovado |
| R06 — colisão entre formatos no outbox | unicidade inclui plataforma, modalidade e formato | aprovado |
| R07 — colisão no destino/ledger | fingerprint e unicidade incluem a identidade completa | aprovado |
| R08 — mensagem virar publicação | worker e ledger ramificam por modalidade canônica | aprovado |
| R09 — publicação virar mensagem por fallback | ausência/incompatibilidade falha fechada | aprovado |
| R10 — target divergir do outbox | validação cruzada antes de chamada de provider | aprovado |
| R11 — retry duplicar post após resposta perdida | TikTok retorna `unknown`; não repete cegamente | aprovado |
| R12 — credencial ligar canal sozinha | flag, catálogo, adapter, consumidores e gate independentes | aprovado |
| R13 — teste local escapar para a rede | saída externa em DEBUG requer opt-in separado | aprovado |
| R14 — escolhas obrigatórias do TikTok serem inventadas | privacidade, comentários, música, disclosure e consentimento explícitos | aprovado |
| R15 — segredo/conteúdo vazar em erro HTTP | bearer fora da URL e corpo de erro descartado | aprovado |

## Budgets operacionais e omotenashi

- Fonte de decisão de plataforma/modalidade/formato: **1 catálogo**, não quatro
  allowlists e defaults independentes.
- Redigitação da modalidade e do default pelo operador: **0**; a UI recebe a projeção
  do servidor.
- Escolhas TikTok inventadas pelo sistema: **0**; toda escolha exigida precisa estar
  explícita no artefato.
- Novos efeitos externos habilitados por esta etapa: **0**.
- Chamadas reais a TikTok durante os testes: **0**.
- Ações humanas neste pacote: **0 adicionais** além do gate já confirmado.

## Gates remanescentes

1. **TikTok App/OAuth:** empresa e conta corretas, redirect URI, políticas públicas,
   Content Posting API e escopo `video.upload` ou `video.publish` aprovados.
2. **Elegibilidade Direct Post:** resposta/revisão do TikTok; um backoffice de conta
   própria tem risco material de não passar na auditoria pública.
3. **Canário:** conta exata, mídia, texto, disclosure e consequência mostrados ao
   humano antes de uma única publicação.
4. **Dry-run de produção:** concluído em modo somente leitura em 2026-09-13;
   resultado e protocolo abaixo.
5. **Ativação:** descarte da compatibilidade histórica e jobs de produção somente em
   gate separado, como determinado.

TikTok Shop permanece um projeto separado. O catálogo fresco/perecível da padaria não
é elegível segundo a política brasileira pesquisada; somente uma allowlist de itens
pré-embalados, não perecíveis e previamente qualificados justificaria um piloto.

Pesquisa e fontes: [relatório TikTok completo](../../research/TIKTOK-INTEGRATION-DEEP-RESEARCH-2026-09-12.md).

## Dry-run de produção — 2026-09-13

Autorização limitada a leitura. Foram consultados o deployment ativo e o PostgreSQL
gerenciado; nenhuma migration, job, deploy ou chamada a provider foi executada. O
console foi encerrado após as consultas. Nenhum segredo, conteúdo de mensagem ou
identificador de cliente foi capturado na evidência.

Snapshot às 06:41 BRT:

| Verificação | Resultado |
|---|---|
| Runtime | PostgreSQL 16.15; deployment ativo |
| Migração atual | `shop.0052`; `0053` ainda não aplicada |
| Outbox | 1 registro; 192 KiB incluindo índices |
| Ledger de destinos | 1 registro; 192 KiB incluindo índices |
| Identidade inferida | 1 × `instagram/publication/story`, artefato schema 3 |
| Plataformas desconhecidas | 0 no outbox; 0 no ledger |
| Colisões nas novas chaves | 0 no outbox; 0 no ledger |
| Divergências alvo/outbox | 0 |
| Locks aguardando | 0 |
| Outras sessões não ociosas | 0 |
| Timeouts do banco | `lock_timeout=0`; `statement_timeout=0` |

### Análise de execução

A `0053` adiciona quatro colunas, retropreenche o único par outbox/destino e troca
duas constraints de unicidade por versões que incluem modalidade e formato. As
tabelas são minúsculas e os dados atuais satisfazem o schema novo; não há trabalho
de rede nem ativação do TikTok na migration. A operação ainda exige locks DDL, mesmo
com uma linha.

O timeout ilimitado observado em produção poderia deixar o release esperando por
um lock. A candidata passou a definir, somente durante a transação PostgreSQL da
migration, `lock_timeout=5s` e `statement_timeout=30s`. Em contenção, o deploy falha
fechado e o PostgreSQL desfaz toda a transação; não permanece schema parcial. SQLite
continua sem essa operação.

### Protocolo proposto para o gate separado de deploy

1. confirmar CI verde no head final e ausência de outro deploy/migration;
2. obter snapshot/backup gerenciado vigente e registrar seu horário;
3. implantar em janela tranquila, sem ativar consumidores ou flag TikTok;
4. acompanhar a release; espera de lock acima de 5 segundos ou instrução SQL acima
   de 30 segundos falha fechada e implica parar, sem repetição automática;
5. conferir `0053` aplicada, 1/1 registros com identidade completa, zero colisões e
   saúde HTTP; nenhuma publicação externa faz parte desse gate;
6. em falha antes do commit, usar rollback transacional automático; depois do
   commit, preferir rollback de código mantendo o schema expandido. Não executar
   reverse migration após novas escritas schema 4 sem novo dry-run e autorização.

Conclusão do dry-run: **compatível e de baixo volume**, com o risco de espera
ilimitada corrigido na candidata. Merge/deploy, OAuth/revisão TikTok, canário real,
ativação de jobs e descarte do legado permanecem gates humanos separados.

Validação posterior ao endurecimento: 10 testes focados passaram em SQLite; o ciclo
reversível `0052 → 0053 → folha` passou também em PostgreSQL 16.14 local e isolado;
Ruff e `makemigrations --check --dry-run` passaram. O banco local descartável foi
removido ao final.
