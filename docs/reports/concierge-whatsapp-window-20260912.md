# Janela do portão ManyChat existente — 2026-09-12

> **Registro histórico.** As seções até “Validação final” documentam o
> experimento v2 e o SHA citado, inclusive nomes de flags e estados que existiam
> naquela implementação. Elas não descrevem o runtime final. A seção
> “Atualização para o contrato v3” registra a decisão que a substituiu sem apagar
> a evidência anterior.

Base: ed9a0d6dc0b34fb1377de950167eb8eb45448ac9, worktree/branch exclusivos codex/concierge-whatsapp-window-20260912. Complemento C01/C03/WP01/WP03/G02 da publicação técnica anterior.

O operador confirmou que provider_timestamp é o campo dinâmico da última interação do usuário no WhatsApp; fuso da conta (UTC-03:00) Brasilia Standard Time — Sao Paulo. Amostra:2026-09-11 11:29:01.391392 →2026-09-11T14:29:01.391392Z. Não é ID de evento nem prova de confirmação comercial.

Revisão perspicaz do recibo: a composição contato+timestamp foi implementada apenas em árvore de trabalho e descartada antes de commit/publicação. Ela reconheceria o retry comum, mas também poderia apagar uma repetição legítima indistinguível; por isso não atende a régua de ausência de erro. O desenho mantido registra receipt local sem `external_id`, assume ingresso at-least-once, agrupa pendências no worker e deixa a idempotência comercial no `quote_token` e no receipt de mutação já canônicos. Nenhuma regressão sintética foi incorporada.

Antes: quatro campos são aceitos para leitura/humano, porém não comprovam janela. Depois: opt-in CONCIERGE_WHATSAPP_INTERACTION_TIMEZONE=America/Sao_Paulo aceita a quinta propriedade, somente em ingresso autenticado da conta/WA configurados. Armazena prova normalizada no envelope Message canônico; preserva last_inbound_at, ID vazio e legacy_unverified. O check canônico de saída consulta a prova e revalida idade/escopo/gates; retry não renova instante e out-of-order não regride a janela. Datas inválidas/futuras/idade≥24h ficam contidas. Nenhuma rede adicional no ACK.

Opt-in ausente ou revogado contém essa fonte de janela, inclusive após preparar a resposta. Nenhum backfill de mensagens anteriores; necessário novo recebimento com o campo dinâmico. Mantidos read_onlytrue, coorte, API key, flow, bloqueios de compra/identidade/transferência/retry/retorno humano. Não há migration, fila ou superfície nova. Fonte normalizada não entra na autoridade de confirmação.

Referência reconsultada: [ManyChat messaging windows](https://help.manychat.com/hc/en-us/articles/23358636027932-Understanding-messaging-windows), atualizada27/08/2026: janela API WhatsApp24h e revalidação antes da resposta. A confirmação de origem/fuso do campo é do operador nesta conversa; entrega no aparelho continua dependendo da homologação.

Validação: primeiro ensaio SQLite35passed; revisão independente levou a revalidar também legacy_read_handoff_enabled no check canônico. Primeira invocaçãoPG abortou por nome de arquivo incorreto, corrigido. Cluster privado inicial nasceu SQL_ASCII e81casos falharam no setup/migration Unicode; reinicializado em diretório distinto UTF8, sem tocar serviços compartilhados. Resultados finais e publicação serão acrescentados.

Rollback: retirar CONCIERGE_WHATSAPP_INTERACTION_TIMEZONE (ou desligar legado). Mantém mensagens/receipts e histórico; não reenviar unknown nem alterar timestamps. Sem migração ou efeitos comerciais a reverter. Publicação e homologação são etapas distintas.

Validação final:95passed/13,48s em PostgreSQL16 privadoUTF8 porta56439, sem skips/warnings, externos fake; Ruff integral/diffcheck aprovados. Novo módulo incluído no runnerPG estrito existente. Evidência: evidence/conversational/whatsapp-window/postgresql.txt. Nenhuma entrega real foi exercitada.

## Atualização para o contrato v3 — 12/09/2026

A prova de janela foi preservada, mas agora pertence ao adapter da connection
`manychat-whatsapp-primary`. A entrada canônica é
`POST /api/webhooks/concierge/manychat-whatsapp-primary/events/`. A rota escolhe
connection, provider, conta e canal; o corpo de cinco campos não controla esse
escopo.

`provider_timestamp` continua significando somente a última interação do usuário
no WhatsApp. O adapter o converte em `WindowEvidence` com source, policy,
`observed_at`, `valid_until` e assurance. Ele não preenche `occurred_at`, não vira
ID de evento e não participa da autoridade da confirmação comercial.

O ingresso sem ID oficial agora é um caso de primeira classe do contrato:
`event_identity_assurance=unavailable` e `input_assurance=at_least_once`. Cada
POST autenticado recebe um recibo local. O turno correspondente fica somente
leitura por assurance; não existe caminho runtime ou flag de “legado”. Hash de
contato + timestamp continua descartado porque poderia apagar uma repetição
legítima indistinguível de retry.

A conversa lógica foi separada do transporte. O endereço ManyChat/WhatsApp vive
em `ConversationBinding`, e cada saída conserva tentativas append-only em
`OutboundAttempt`. Outros providers/canais, inclusive TikTok, usam outro adapter
e outra connection sob o mesmo contrato; nenhuma regra de janela do WhatsApp é
extrapolada automaticamente.

A validação de 95 testes acima permanece evidência do experimento isolado da
janela. A integração v3 foi depois validada no SHA
`7dba54a6ac81866bd0708033d683ac47dcade30c` por 293 testes do Concierge em
PostgreSQL/Redis e pelo Storefront integral de 1729 testes em SQLite. Isso não
certifica homologação no flow real, entrega no aparelho, piloto ou rollout. A
migração v3 reverte apenas enquanto houver um binding por conversa; rollback operacional contém a connection/switches,
preserva bindings, mensagens, attempts e receipts e corrige adiante, sem
downgrade de schema ou reenvio de estado `unknown`.
