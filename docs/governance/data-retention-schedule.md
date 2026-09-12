# Tabela de retenção e descarte de dados

**Estado:** política operacional inicial aprovada em 2026-09-12 para
implementação e testes fora de produção. Descarte do legado e ativação de jobs
em produção permanecem bloqueados até dry-run e gate humano separado.
**Responsável operacional:** Pablo Valentini. **Suplente:** Laís Kohatsu Kataoka.  
**Revisão mínima:** anual e sempre que mudar finalidade, fornecedor, país,
categoria de dado ou obrigação legal.

## Regra de leitura

Prazo de negócio não é prazo geral da LGPD. A LGPD manda encerrar o tratamento
quando a finalidade termina e eliminar o dado, ressalvadas as hipóteses de
conservação do art. 16. Por isso cada linha define o marco inicial e o destino.
O prazo de cinco anos usado em provas de consentimento é uma escolha documentada
de gestão de risco e defesa de direitos; não é apresentado como prazo universal
da LGPD.

`Legal hold` significa uma exceção registrada antes do vencimento, com motivo,
responsável, escopo, data de revisão e acesso restrito. Não existe prorrogação
silenciosa. Backup não cria um segundo prazo: restauração exige reaplicar os
descartes ocorridos desde a cópia.

## Matriz aprovada

| ID | Categoria e finalidade | Marco inicial | Prazo proposto | Destino no vencimento | Estado técnico |
|---|---|---|---|---|---|
| R01 | Pedido, pagamento, cancelamento, estorno e documento fiscal | emissão/transação ou encerramento do pedido, conforme a obrigação aplicável | 5 anos, ou prazo legal específico maior | retirar PII não exigida; eliminar ao fim da obrigação, salvo legal hold | pedido já é pseudonimizado na exclusão da conta; expurgo temporal final ainda não implementado |
| R02 | Registro de incidente de segurança | data do registro | mínimo de 5 anos | eliminar ou anonimizar, salvo obrigação adicional | prazo e runbook documentados; exercício e rotina de arquivo pendentes |
| R03 | Evento de consentimento e revogação | último evento da finalidade/canal | 5 anos | eliminar; preservar apenas tombstone R04 quando necessário | evento existe; IP bruto já é removido em até 90 dias |
| R04 | Bloqueio de contato/opt-out mínimo | remoção do contato ou última revogação | enquanto o contato existir e 5 anos depois | eliminar | modelo deve conservar só identificador protegido, finalidade e prova mínima; implementação pendente |
| R05 | Membro de público e vínculo pessoal de destino de Marketing | `settled`, `cancelled` ou `expired` | 90 dias; `unknown` até 180 dias | apagar FK/vínculo pessoal; manter apenas contagens, estado, horários e hashes não reversíveis | política já proposta; job pendente |
| R06 | ID do provedor e recibo detalhado de entrega | encerramento/reconciliação | 180 dias | remover ID/PII; manter resultado técnico agregado | job pendente; `unknown` sem solução aos 180 dias exige legal hold ou anonimização |
| R07 | Inscrição “Avise-me” | pausa ou cancelamento pelo cliente | ativa até pausa/cancelamento; depois 90 dias para dado operacional e 5 anos para prova mínima | apagar contato/capacidade operacional aos 90 dias; apagar prova ao fim de 5 anos | vigência ativa implementada; contração pós-cancelamento pendente |
| R08 | Conversa e transcrição do concierge | encerramento; conversa sem atividade encerra após 30 dias | 90 dias após encerramento | eliminar transcrição, vínculos e IDs; exceção somente para disputa/incident legal hold | exclusão de conta já apaga a árvore completa; fechamento e expurgo temporal pendentes |
| R09 | Conta, endereços, preferências, favoritos, tags e perfil de compra | exclusão da conta ou fim da finalidade | enquanto a conta estiver ativa | apagar imediatamente; pedidos seguem R01 já pseudonimizados | autoatendimento abrangente implementado, com alerta se houver falha parcial |
| R10 | Código de verificação, link de acesso e aparelho confiável | expiração individual | expiração + 7 dias | eliminar | `auth_cleanup` já implementado; falta comprovar agendamento e alerta de falha |
| R11 | IP bruto auxiliar de consentimento | coleta | máximo 90 dias | redigir o IP, preservando a prova sem IP | `purge_consent_ip` implementado; falta comprovar agendamento e alerta de falha |
| R12 | Logs técnicos com identificador pessoal que não viraram incidente | criação | 180 dias | eliminar ou anonimizar | inventário e job unificado pendentes; logs sem PII podem seguir política operacional própria |
| R13 | Perfil analítico individual/RFM | exclusão da conta ou fim da finalidade | enquanto necessário à conta ativa | eliminar; métricas realmente agregadas e não reidentificáveis podem permanecer | exclusão de conta já remove o perfil individual |
| R14 | Cópias públicas de termos e privacidade | publicação da versão | permanente | não apagar nem sobrescrever | arquivo append-only, URL e SHA-256 implementados; não contém PII de cliente |
| R15 | Backups transacionais | criação do backup | 7 dias na infraestrutura atual | expiração automática; restore reaplica descartes posteriores | retenção documentada; prova periódica de backup/restore continua operacional |

## Ordem de implementação autorizada fora de produção

1. Entregar primeiro um comando único em `--dry-run`, com contagens por linha da
   matriz e zero PII na saída.
2. Implementar R05–R08 por contração: apagar vínculo/ID antes de apagar os
   registros agregados e nunca tocar em entrega ainda não reconciliada.
3. Integrar R10 e R11 ao worker de manutenção com alerta em falha ou atraso; o
   comando existente não prova que alguém o executa.
4. Inventariar R12 por modelo/campo antes de qualquer exclusão genérica.
5. Aplicar em staging com dados sintéticos, verificar idempotência, concorrência,
   legal hold e restauração de backup; produção exige gate próprio.

## Decisão humana registrada em 2026-09-12

> Aprovo R01–R15 da tabela de retenção como política operacional inicial,
> reconhecendo que os prazos de prova são decisões de gestão de risco e que
> obrigações legais específicas e legal hold documentado prevalecem. Autorizo
> implementação e testes fora de produção; descarte do legado produtivo e
> ativação dos jobs em produção exigem um gate separado com dry-run e contagens.

O responsável confirmou o exercício L6 e aprovou a matriz R01–R15 com testes
fora de produção. Esta decisão **não** autoriza descarte de dados legados nem
agendamento/ativação de jobs em produção; ambos exigem evidência do dry-run e
uma nova confirmação humana específica.

## Fontes normativas primárias

- [LGPD, arts. 15 e 16](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm): término do tratamento, eliminação e hipóteses de conservação.
- [Perguntas frequentes da ANPD, item 5.5](https://www.gov.br/anpd/pt-br/acesso-a-informacao/perguntas-frequentes/perguntas-frequentes): a LGPD não estabelece um prazo único; prazo depende da finalidade e circunstância.
- [Resolução CD/ANPD nº 15/2024](https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd/documentos/rcis___anonimizado_final_ocultado_2_parte3.pdf): registro de incidente por no mínimo cinco anos.
- [Orientação oficial sobre notas fiscais](https://www.gov.br/empresas-e-negocios/pt-br/empreendedor/perguntas-frequentes/nota-fiscal-inscricao-estadual-e-ou-municipal/as-notas-fiscais-emitidas-e): referência pública de guarda por cinco anos, sujeita ao regime tributário efetivamente aplicável à empresa.
