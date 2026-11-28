# Decisão semântica sobre 15 rescues e quatro snapshots

Seguimento da #2046, base `7288b44624d195d5cbf37431184fe49ee71a43e0`. [Heads e decisão de cada candidato](../EVIDENCE/20261029-rescue-semantic.json). A classificação combina patch equivalence, comparação de comportamento/arquivos e comentários de fechamento com destino explícito. Não se presume que merge conflitante prove novidade nem que título igual prove equivalência.

| Ref remota (prefixo origin omitido) | Decisão | Evidência e destino |
|---|---|---|
| `rescue/admin-ingress-staging-probe-20260914-uncommitted` | OBSOLETO | Sonda de ingresso temporária para a #671. A própria #671 foi encerrada após a solução de IP autenticado via BFF (#763/#768). Ajustes de nome de app e sender da sonda não são funcionalidade de produto. Evidência: PR #671, comentário de encerramento. |
| `rescue/admin-login-ip-contract-20260914` | REJEITADO | Trava por IP e observação temporária pertencem à proposta #655/#828 recusada tecnicamente. Não reintroduzir XFF sem contrato, nem bloquear todos por REMOTE_ADDR compartilhado. Evidência: PR #828, encerramento; solução #763/#768. |
| `rescue/ci638-visual-repro-20260915` | ENTREGUE | O único patch não merge é equivalente ao main por git cherry: zero +, um -. O título aparece em aafd1362f. Baseline antiga não deve substituir a matriz atual. Evidência: git cherry origin/main <ref>; aafd1362f. |
| `rescue/go-live-638-baseline-uncommitted` | ENTREGUE | O teste test_pos_gateway_handoff_boundary.py está no main. A versão atual acrescenta expected_total_q, PosCommittedSaleError e a regra fiscal posterior da retirada. A cópia antiga removeria essas garantias. Evidência: Comparação do arquivo entre ref e main. |
| `rescue/go-live-638-integration-validation-20260913` | SUPERADO | 16 patches equivalentes por git cherry. Os demais combinam a stack de readiness/maps/fiscal do bundle #686 com a trava Admin rejeitada. Correções de locks guestman, recuperação POS e pausa de catálogo têm sucessores no main. Não há motivo para carregar a stack inteira. Evidência: Fechamentos #613/#651–#657 e #828; commits main 7d92d47d7, 459e251ff, f55cafbaa. |
| `rescue/golive-rebase-integration-probe-20260914` | SUPERADO | Stack de ensaio de composição: cinco patches equivalentes; readiness/certificados/alertas/Maps absorvidos no #686 e telefone no #650. A peça Admin restante foi rejeitada. Os merges de composição não são uma feature autônoma. Evidência: Fechamentos #650–#657/#828, bundle #686. |
| `rescue/google-maps-credential-split-20260911` | ENTREGUE | A separação de credencial server/browser pertence à cadeia #613 → #656 → #657, absorvida com patch cumulativo equivalente no #686. Não trocar settings atuais pelo snapshot. Evidência: Comentário de fechamento da #613, patch-id 3e28651488eb6e591ef142a8a6cda47e3d50a3a0. |
| `rescue/marketing-final-l7-probe-20260914` | SUPERADO | Composição do #614 com retenção/telemetria de L7. A #614 registra portabilidade em #1045/#1046/#1047 e contratos mais novos; a #742 foi substituída pela #830, preservando a rota do erro em vez de reduzir URL à origem. As propostas não aceitas permanecem históricas. Evidência: Matriz de fechamento #614 e comentário #742. |
| `rescue/marketing-r10-r12-replay-20260915` | SUPERADO | Mesmo núcleo legal/privacy acima e inventário antigo de capacidade. A oportunidade documental de evitar deploy por teste já foi tratada na política posterior de paths (#871). Não usar conclusões operacionais de setembro como prontidão atual. Evidência: Matriz #614, sucessor #830, fechamento #870 em favor de #871. |
| `rescue/orders-audit-base-5a3383c9-uncommitted` | FERRAMENTA_HISTORICA | Apenas run_orders_lab.py, sete linhas: monta sys.path dos packages e chama pytest. Não contém regra de produto nem teste novo; o contrato atual de teste é Makefile com PYTHON/PYTHONPATH explícitos. Mantido como referência, sem promover runner paralelo. Evidência: 4ced7839d; leitura integral do arquivo. |
| `rescue/pdv-execution-20260910-a1` | INSUMO_UX | Contratos de venda desconhecida/locks já têm sucessores. A execução de interação da lista tem ideias não equivalentes ao desenho atual: explicitar navegação/seleção e compactar rodapé. Encaminhada ao briefing da frente UX reservada pelo dono, sem implementação paralela. Evidência: docs/reports/execution/pdv-20260910-a1-accordion-display.md na ref; briefing abaixo. |
| `rescue/pdv-execution-20260910-a1-uncommitted` | INSUMO_UX | Contém a mesma stack anterior e OperatorKbd.vue local. Esse componente é idêntico byte a byte ao OperatorKbd.vue atual no kit; o delta útil potencial é o mesmo estudo de interação, não outro componente a instalar. Evidência: efe302cc7; comparação de blobs; briefing abaixo. |
| `rescue/pr614-pr634-composition-20260914` | SUPERADO | Composição de cancelamento com legal/privacy. Cancelamento entregue #629; partes funcionais portadas #1045/#1046/#1047 e retenção/exportação já no main. A matriz da #614 lista explicitamente descartes de produto e confirma que a stack não deve mergear. Evidência: Fechamento #614: tabela parte → destino. |
| `rescue/print-layouts-20260912` | DECISAO_VISUAL_EXISTENTE | DANFE/XML funcional foi recuperado semanticamente na #1227. Tipografia, monograma e redesign de tickets foram deixados BLOCKED_HUMAN na #1120. Não há autorização nova de layout inferida da recuperação técnica. Evidência: Fechamento #1120, inventário dos nove commits. |
| `rescue/print-layouts-20260912-uncommitted` | DECISAO_VISUAL_EXISTENTE | Mesma stack de impressão, mais inventário histórico de layouts. O conteúdo único é relatório; a intenção funcional segue #1227 e a proposta visual permanece preservada para decisão própria. Evidência: d2f6ff326; fechamento #1120. |
| `snapshot/operador-nuxtui-onda0-conjunto-minimo-20261011` | INSUMO_UX | Snapshot de catálogo visual e antigos UiButton/UiNativeSelect. Tema mínimo entrou pelo pouso #1555; os adapters foram depois aposentados. O showroom específico pode informar a nova auditoria, mas não deve reintroduzir componentes removidos nem alterar o tema atual. Evidência: 7e7508ef4; fechamento #1543: entrou pelo #1555. |
| `snapshot/operator-kitchen-sink-20261011` | INSUMO_UX | A feature kitchen sink foi entregue #1512 e evoluiu no app interno atual. Snapshot acrescenta .look.cjs local com porta fixa e versões antigas de tema/showroom. São referência de demonstração; não há correção de domínio inédita. Evidência: 6292fbc73; #1512; leitura integral de .look.cjs. |
| `snapshot/orders-canonical-recovery-20261011` | INSUMO_UX | Pilha de UI/harness antiga com 110 arquivos desde a base. A migração canônica seguiu #1518 por decisão do dono, encerrando #1516. Inventário funcional e laudo preservados são briefing útil; capturas antigas não são baseline CI autorizada. Evidência: e5e3c13d1, 26b1a8fe4, 452bed2e7; fechamento #1516. |
| `snapshot/select-chevron-and-controls-audit-20261011` | OBSOLETO | Delta de bg-none no select nativo e comentário do chevron. O WP de higiene já comprovou supersessão semântica; a superfície atual usa controles canônicos e o CSS de UiNativeSelect foi aposentado. Evidência: ed052e5f6; WP-REPOSITORY-WORKTREE-BRANCH-HYGIENE §3.4. |

## Resultado para o go-live

Não foi identificado defeito funcional inédito nestas 19 fontes que justifique transplantar sua stack para main. Há material de interação potencialmente útil que não é declarado entregue: fica explicitamente reservado à nova frente UX solicitada pelo dono. As propostas de impressão já têm uma decisão visual pendente registrada, distinta de recuperação de código. Nenhuma permissão, comportamento, baseline ou UI foi alterada nesta triagem.

Os comentários de fechamento de setembro são evidência do destino daqueles diffs, não normas atuais. Exemplos de políticas de produto e rotas mencionados nesses comentários devem ser confrontados com a decisão vigente; esta triagem não restaura a política antiga.

## Briefing de UX: material preservado e comparação atual

**A frente nova ainda não tinha sessão identificada nesta conferência.** Este material aguarda o agente que o dono designar; não foi despachado para outra sessão nem convertido em PR de UI concorrente.

### PDV: lista, seleção e rodapé

Fonte: `origin/rescue/pdv-execution-20260910-a1`, relatório `docs/reports/execution/pdv-20260910-a1-accordion-display.md` e arquivos `surfaces/pos-nuxt/app/components/PosCartPanel.vue`, `PosShortcutsHelp.vue`.

- `17d60552e`: separar seleção da linha e expansão de detalhes.
- `d603c3180`: lista compacta e seleção por teclado.
- `781760fae`: preservar total e esconder ações gerais durante seleção.
- `1219dbfaa`: rodapé compacto também durante navegação de itens.
- `fd4f89ae2`: concentrar atalhos na ajuda.

O main atual já tem navegação por setas, seleção, detalhe e ajuda em `surfaces/pos-nuxt/app/presentation/shortcuts.ts`. Usa **Alt+S**, enquanto o estudo usa **Alt+I**; não trocar atalhos por recuperação mecânica. A contagem atual determina seleção múltipla (`selection.count >= 2`), enquanto o estudo propõe modo explícito mesmo antes de marcar duas linhas. A composição atual é posterior (lista + total + Pagamento) e deve ser o ponto de partida. Avaliar se o benefício de espaço e previsibilidade do estudo ainda existe com a tela de hoje, em 3/10/20 itens e teclado/toque. Não restaurar a página inteira do rescue.

O componente local `OperatorKbd.vue` do commit `efe302cc7` é byte a byte igual ao componente do kit atual; não há peça perdida a duplicar. As proteções de venda com resultado desconhecido, revisão de total e locks são mais novas no main e ficam preservadas.

### Gestor e kit: inventários e showroom

- `origin/snapshot/orders-canonical-recovery-20261011`: consultar `docs/plans/suite-ux-v2/orders/inventario-funcional.md` e `laudo-orders-board.md` para comparar cobertura de fluxos. A UI e as capturas da pilha antiga não são fonte de verdade do tema atual.
- `origin/snapshot/operador-nuxtui-onda0-conjunto-minimo-20261011`: `OperatorKitchenSinkMinimalSet.vue` é uma demonstração histórica do conjunto mínimo. Avaliar somente lacunas do showroom atual; não reintroduzir UiButton/UiNativeSelect.
- `origin/snapshot/operator-kitchen-sink-20261011`: alterações de demonstração e o script local `.look.cjs` preservam a intenção do estudo. O app interno atual e seus gates prevalecem.

## Verificação e estado

Leitura de todas as 19 decisões, comparação dos arquivos específicos e consulta aos fechamentos citados. `git cherry` foi usado como evidência auxiliar; falta de patch equivalente não foi confundida com necessidade de reaplicação. Governança documental e diff check executados antes da publicação. Sem testes de produto repetidos porque não há alteração de código. PR #2047 publicada para registrar as decisões e o briefing, sem apagar nenhum original ou branch.
