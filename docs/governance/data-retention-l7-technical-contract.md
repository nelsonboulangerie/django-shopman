# Contrato técnico L7 — retenção e descarte

**Estado:** desenho de implementação baseado exclusivamente na matriz R01–R15
aprovada. Não cria política, não autoriza mutação e não antecipa dependências de
migração ainda inexistentes.

## Invariantes obrigatórios

- O modo padrão é dry-run, sem PII e com zero mutações.
- Uma entrega pendente, reservada, retryable ou `unknown` não perde destino,
  recibo ou prova necessários à reconciliação.
- O relógio de R05 nasce em `settled`, `cancelled` ou `expired`; `available_at`
  não substitui encerramento.
- O detalhe R06 pode sair em 180 dias sem apagar o registro técnico de cinco
  anos; estado, horário e resultado agregado permanecem.
- Inscrição Avise-me ativa não expira. Depois de pausa/cancelamento, dado
  operacional sai em 90 dias e prova mínima segue por cinco anos. Retomar após
  contração exige novo opt-in/destino válido.
- R08 só usa um fechamento canônico. `updated_at` não prova encerramento; nova
  entrada reabre ou invalida o marcador de retenção.
- Legal hold precisa existir antes de qualquer `apply`: regra, recurso/escopo,
  razão e autoridade codificadas, responsável, início, revisão, liberação e
  auditoria append-only, com no máximo um hold ativo por regra/recurso.
- A saída de comando, métrica e alerta nunca contém contato, provider ID, erro
  bruto, texto da conversa ou outro dado pessoal.

## Ordem de bloqueio e contração

Cada lote deve usar transação curta, ordenação determinística por chave e
`select_for_update(skip_locked=True)` em PostgreSQL. A ordem evita órfãos e
conflito com workers ativos:

1. reaplicar supressões/tombstones restaurados e retirar do lote, preservando,
   qualquer recurso sob legal hold;
2. travar o registro raiz e revalidar prazo/estado dentro da transação;
3. R05: anular `DeliveryTarget.member`; apagar `AudienceSnapshotMember` apenas
   quando nenhum destino ainda o referencia;
4. R06: redigir provider ID/erro/recibo detalhado, mantendo resultado agregado;
5. R07: remover capacidade operacional e contato; preservar prova mínima e
   tornar impossível reativação silenciosa;
6. R08: eliminar `OutboundAttempt`, depois `ConversationMessage`,
   `ConversationBinding` e por último `Conversation`, desde que não exista
   claim, diretiva ou entrega em curso;
7. gravar somente contagens e marcador técnico do lote.

Falha de um lote não confirma os demais. Reexecução deve convergir para zero sem
efeito colateral e um novo evento/inbound válido precisa cancelar a elegibilidade
antiga antes da próxima varredura.

## Sequência de schema coordenada

- `shop.0053`: identidade de entrega do Marketing (PR #634).
- `shop.0054`: reservada à integração de catálogo/iFood; ainda deve ser recebida
  como migração real antes de declarar dependência.
- `shop.0055`: reservada ao trabalho conversacional; ainda deve ser recebida e
  revisada antes de definir o fechamento canônico de R08.
- `shop.0056`: futura expansão L7. Só pode ser gerada sobre 0054/0055 reais e
  revisáveis; dependência nominal ou migração vazia é proibida.

A expansão deve primeiro adicionar marcadores/indexes/hold sem remover colunas.
A contração destrutiva e o agendamento produtivo ficam em uma etapa posterior,
após dry-run, evidência PostgreSQL, restauração e gate humano específico.

## Evidências exigidas antes de `apply`

- testes de limite temporal (antes, exatamente no marco e depois);
- multi-destino, snapshot órfão e `unknown` preservado;
- pausa/cancelamento/re-opt-in de Avise-me;
- encerramento, reabertura e ordem de exclusão da conversa;
- legal hold ativo, revisão e liberação auditável;
- dois workers concorrentes em PostgreSQL sem dupla mutação;
- lote interrompido e reexecução idempotente;
- restore de backup seguido de reaplicação de tombstones;
- dry-run revisado com contagens por R01–R15 e nenhuma PII.

Até essas provas existirem, `data_retention --apply` deve continuar recusando a
operação e nenhum job novo pode ser ativado em produção.
