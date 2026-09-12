# Janela do portão ManyChat existente — 2026-09-12

Base: ed9a0d6dc0b34fb1377de950167eb8eb45448ac9, worktree/branch exclusivos codex/concierge-whatsapp-window-20260912. Complemento C01/C03/WP01/WP03/G02 da publicação técnica anterior.

O operador confirmou que provider_timestamp é o campo dinâmico da última interação do usuário no WhatsApp; fuso da conta (UTC-03:00) Brasilia Standard Time — Sao Paulo. Amostra:2026-09-11 11:29:01.391392 →2026-09-11T14:29:01.391392Z. Não é ID de evento nem prova de confirmação comercial.

Antes: quatro campos são aceitos para leitura/humano, porém não comprovam janela. Depois: opt-in CONCIERGE_WHATSAPP_INTERACTION_TIMEZONE=America/Sao_Paulo aceita a quinta propriedade, somente em ingresso autenticado da conta/WA configurados. Armazena prova normalizada no envelope Message canônico; preserva last_inbound_at, ID vazio e legacy_unverified. O check canônico de saída consulta a prova e revalida idade/escopo/gates; retry não renova instante e out-of-order não regride a janela. Datas inválidas/futuras/idade≥24h ficam contidas. Nenhuma rede adicional no ACK.

Opt-in ausente ou revogado contém essa fonte de janela, inclusive após preparar a resposta. Nenhum backfill de mensagens anteriores; necessário novo recebimento com o campo dinâmico. Mantidos read_onlytrue, coorte, API key, flow, bloqueios de compra/identidade/transferência/retry/retorno humano. Não há migration, fila ou superfície nova. Fonte normalizada não entra na autoridade de confirmação.

Referência reconsultada: [ManyChat messaging windows](https://help.manychat.com/hc/en-us/articles/23358636027932-Understanding-messaging-windows), atualizada27/08/2026: janela API WhatsApp24h e revalidação antes da resposta. A confirmação de origem/fuso do campo é do operador nesta conversa; entrega no aparelho continua dependendo da homologação.

Validação: primeiro ensaio SQLite35passed; revisão independente levou a revalidar também legacy_read_handoff_enabled no check canônico. Primeira invocaçãoPG abortou por nome de arquivo incorreto, corrigido. Cluster privado inicial nasceu SQL_ASCII e81casos falharam no setup/migration Unicode; reinicializado em diretório distinto UTF8, sem tocar serviços compartilhados. Resultados finais e publicação serão acrescentados.

Rollback: retirar CONCIERGE_WHATSAPP_INTERACTION_TIMEZONE (ou desligar legado). Mantém mensagens/receipts e histórico; não reenviar unknown nem alterar timestamps. Sem migração ou efeitos comerciais a reverter. Publicação e homologação são etapas distintas.

Validação final:95passed/13,48s em PostgreSQL16 privadoUTF8 porta56439, sem skips/warnings, externos fake; Ruff integral/diffcheck aprovados. Novo módulo incluído no runnerPG estrito existente. Evidência: evidence/conversational/whatsapp-window/postgresql.txt. Nenhuma entrega real foi exercitada.
