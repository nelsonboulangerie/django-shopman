# Tabela de retenção e descarte de dados

**Estado:** política operacional inicial aprovada em 12/09/2026 para
implementação e testes fora de produção. Descarte do legado e ativação de jobs
em produção permanecem bloqueados até dry-run revisado e gate humano separado.
**Responsável operacional:** Pablo Valentini. **Suplente:** Laís Kohatsu Kataoka.

Prazo de negócio não é prazo geral da LGPD. Cada regra define finalidade,
marco e destino; obrigação legal específica e `legal hold` documentado
prevalecem. Backup não cria um segundo prazo: uma restauração precisa reaplicar
os descartes ocorridos desde a cópia.

## Matriz aprovada

| ID | Categoria | Marco e prazo inicial | Destino aprovado | Estado técnico atual |
|---|---|---|---|---|
| R01 | Pedido, pagamento, cancelamento, estorno e documento fiscal | emissão/transação ou encerramento; 5 anos ou prazo legal maior | retirar PII não exigida e eliminar ao fim da obrigação, salvo `legal hold` | dry-run usa `completed_at`, `cancelled_at` ou `returned_at` conforme o estado terminal; obrigação efetiva ainda exige validação fiscal/contratual |
| R02 | Incidente de segurança | registro; mínimo de 5 anos | eliminar ou anonimizar, salvo obrigação adicional | prazo/modelo existem; dry-run conta vencidos |
| R03 | Consentimento e revogação | último evento; 5 anos | eliminar, preservando somente tombstone R04 quando necessário | inventário conta eventos, mas expõe zero candidatos: evento antigo ainda pode ser a prova vigente |
| R04 | Bloqueio de contato/opt-out mínimo | remoção/última revogação; enquanto o contato existir e 5 anos depois | eliminar | inventário conta bloqueios, mas expõe zero candidatos até existir marco canônico de remoção do contato |
| R05 | Vínculo pessoal de destino de Marketing | `settled`, `cancelled` ou `expired`; 90 dias, `unknown` até 180 | remover FK/vínculo; manter agregado não reversível | inventário conta vínculos cujo prazo materializado venceu, mas expõe zero candidatos: o relógio atual nasce antes do encerramento e o marco canônico ainda será contratado |
| R06 | ID do provedor e recibo detalhado | encerramento/reconciliação; 180 dias | remover ID/PII; manter resultado técnico agregado | dry-run usa 180 dias e cobre Marketing, Avise-me e concierge; não altera recibos |
| R07 | Inscrição “Avise-me” | pausa/cancelamento; ativa até lá, depois 90 dias operacionais e 5 anos de prova mínima | remover capacidade/contato e depois prova | dry-run conta inativas sem entrega pendente; contração ainda bloqueada |
| R08 | Conversa/transcrição do concierge | fechamento canônico; 90 dias | eliminar transcrição, vínculos e IDs, salvo `legal hold` | 0056 já dá prazo e limpeza própria às observações passivas; legado não tem `closed_at`, e o dry-run não inventa `updated_at` como marco |
| R09 | Conta, endereço, preferências, favoritos, tags e perfil | exclusão/fim da finalidade | apagar; pedido segue R01 pseudonimizado | inventário conta contas inativas, mas expõe zero candidatos: inatividade não prova exclusão nem fim da finalidade |
| R10 | Código, link de acesso e aparelho confiável | expiração + 7 dias | eliminar | dry-run apenas inventaria; nenhum job novo é criado aqui |
| R11 | IP bruto auxiliar de consentimento | coleta; máximo 90 dias | redigir IP, preservando prova sem IP | dry-run apenas conta; `purge_consent_ip` não integra esta entrega nem o worker |
| R12 | Logs e payloads técnicos potencialmente identificáveis | criação; prazo depende de classificação | eliminar ou anonimizar | 0055 adicionou `CatalogSnapshot.raw_json`; o dry-run só conta snapshots, com zero candidatos até classificação/prazo aprovados |
| R13 | Perfil analítico individual/RFM | exclusão/fim da finalidade | eliminar; agregado não reidentificável pode permanecer | inventário conta perfis ligados a conta inativa, mas expõe zero candidatos até haver marco canônico de exclusão/fim da finalidade |
| R14 | Cópias públicas versionadas de termos/privacidade | publicação | permanente; não apagar nem sobrescrever | dry-run inventaria arquivos sem tratá-los como candidatos; superfície legal segue em entrega separada |
| R15 | Backups transacionais | criação; 7 dias na infraestrutura declarada | expiração e reaplicação de descartes após restore | evidência externa de retenção/restore continua pendente |

## Ordem já autorizada fora de produção

1. Dry-run único R01–R15, somente contagens, `pii=false`, `mutations=0`.
2. R10 e R12 em entregas isoladas, sem agendamento.
3. Expansão de schema apenas sobre a folha real `shop.0056`, portanto a próxima
   numeração disponível é `0057`; nenhuma migration faz parte desta etapa.
4. Engine R05–R08 apenas com dados sintéticos e inacessível ao worker.
5. Dry-run revisado; depois, gates separados para expurgo produtivo e para cada
   job de produção.

`python manage.py data_retention --json` é sempre não destrutivo. `--apply`
recusa antes de iniciar o inventário. Esta etapa não altera
`MAINTENANCE_COMMANDS`, não adiciona migration e não chama a limpeza passiva já
existente desde 0056.

Os recibos sem PII de exportação e exclusão carregam `retention_until`: 90
dias para falhas e, inicialmente, 5 anos para conclusões. Esse marco é um
horizonte de **elegibilidade para revisão de risco**, não uma afirmação de
prazo legal automático. O dry-run os conta dentro de R09, mas mantém
`candidates=0`; qualquer descarte depende de checagem de `legal hold`, dry-run
revisado e gate humano separado. Não há rotina destrutiva ou job ativo.

## Decisão humana registrada

> Aprovo R01–R15 como política operacional inicial e autorizo implementação e
> testes fora de produção. Descarte do legado produtivo e ativação dos jobs em
> produção exigem gate separado, com dry-run e contagens.

Fontes normativas primárias: [LGPD, arts. 15–16](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm),
[FAQ da ANPD, item 5.5](https://www.gov.br/anpd/pt-br/acesso-a-informacao/perguntas-frequentes/perguntas-frequentes)
e [Resolução CD/ANPD nº 15/2024](https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd/documentos/rcis___anonimizado_final_ocultado_2_parte3.pdf).
