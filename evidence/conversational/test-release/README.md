# Publicação controlada para teste — Concierge

Autorização: operador solicitou “Pode publicar pra eu testar?”. Alvo confirmado staging `shopman-nelson`, app `40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f`, endpoint ManyChat existente. Não amplia a coorte; preserva chaves, flow e demais superfícies. Não é piloto/rollout comercial.

Candidato vem de `7e8f3f48d`, integrado a `origin/main` `7100e4380` pelo merge `d346b9a20`. Foram conciliados cart/checkout: mantém expected_revision e recuperação de conveniências do main, total completo/locks/Decimal do Concierge. A regressão de revogação passou ao StockAlertDelivery canônico do main, sem mudar produto.

## Preflight

- `integration-final.txt`: **478 passed/52,83s**, PostgreSQL privado 56429 e Redis56430, zero skips/warnings. Inclui seleção anterior e API de intenções/checkout concorrente do main.
- `integration.txt`: diagnóstico anterior 475passed/1failed; teste obsoleto chamava função removida no main. Corrigido para comprovar locks nos boundaries atuais de claim e envio, sem enfraquecer consentimento.
- `read-only-tests.txt`:16passed/1,70s; fake de fornecedor/modelo, não entrega real.
- `migrations.json`:3passed/2skipped. SQLite descartável valida schema; PostgreSQL usado na integrada. Skips são baseline real pós-go-live e política expand/contract que depende do marco de go-live, não prova substituída.
- Marketing docs: sem drift de rotas/probes. Ruff e diffcheck passaram.
- `managed-backups.json`: inventário read-only; backup mais recente observado 2026-09-12T00:13:28Z,0,239GB. Migrations0048/0049 expandem dados de conversa, sem replay/backfill de autoridade. Rollback de código preserva colunas e receipts; não desfazer migrations nem restaurar banco automaticamente.
- Leitura remota pré-deploy confirmou staging, schema shop0047,1Conversation legada e subject do operador na coorte. getInfo do ManyChat confirmou subject, mas só expôs timestamps FB/IG antigos; não usar esses timestamps como janela WhatsApp.

## Configuração e contenção

`env-plan.json` descreve8 adições a partir do spec vivo, todas RUN_TIME. Spec original e proposto ficam em diretório privado0700, arquivos0600, fora do repo; nenhum token é impresso. Proposta aceita pela API `apps propose --app`. O spec versionado é só referência e não será aplicado.

`CONCIERGE_READ_ONLY=true` impede mutações também quando um event_id chega ou o objeto é recarregado. `LEGACY_READ_HANDOFF_ENABLED=true` permite o recebimento dos4campos para leitura/humano. Account verificada e contract_version2. Identidade, retornohumano, retry e transferência continuam false. As demais envs/componentes/hosts/coorte são idênticos ao snapshot vivo.

O corpo atual sozinho NÃO comprova janela WhatsApp: sem evidência válida, resposta fica not_applied/window_closed. Nenhum timestamp é preenchido manualmente e getInfo não substitui texto/evento. Não prometer teste de compra, resposta no aparelho ou benefício humano apenas com deployverde. Este release permite testar ingresso e inspeção do contexto; resposta exige resolver a prova da janela no mesmo flow.

## Execução

Estado deste registro: preflight local concluído; PR/CI, deploy por imagens e atualização restrita de envs ainda pendentes. Merge main dispara workflow canônico Deploy Images. Só depois de deploymentACTIVE e releasejob/migrations saudáveis aplicar envs a partir de snapshot vivo revalidado. Registrar SHA/imagem/deployment e probes finais antes de declarar publicado.

Rollback funcional: manter read_onlytrue e desligar LEGACY_READ_HANDOFF_ENABLED ou contract_version0, sem apagar registros/filas. Antes de rollback de imagem, conter ingresso novo e manter schemas expansivos; não reenviar unknown. Configurações de terceiros nunca são revertidas por snapshot inteiro sem comparar alterações posteriores.
