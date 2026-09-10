# Continuação PDV — sincronização, caixa e autoria

Data: 2026-09-10. Branch `codex/pdv-execution-20260910-a1`; mesma worktree isolada e base do [registro inicial](pdv-20260910-a1.md). Este documento substitui as pendências de decisão da primeira parada, sem apagar o histórico. Não representa conclusão dos 36 itens do plano nem autorização de produção.

## Decisões autorizadas e implementação

O usuário aprovou execução autônoma de vínculo estrito dispositivo/terminal, valores explícitos, consulta antes de repetir uma venda incerta e atendimento compartilhado tablet/PC. Pediu também avaliação e implementação visualmente cuidadosa da autoria de linhas. Nenhuma outra pessoa foi contatada; sem agentes, merge, push, PR, deploy, credenciais reais ou hardware.

- A estação deve ter um único vínculo confiável e terminal ativo. Referência divergente no body é recusada; o servidor injeta turno e terminal e descarta IDs de caixa fornecidos pelo navegador. Duas estações continuam acessando a mesma comanda, cada qual com seu caixa na finalização.
- Comandos HTTP de comanda exigem revisão opaca, conferida sob lock. A revisão usa o `rev` que **já existia** e `updated_at`; corrige a afirmação equivocada do primeiro handoff. Cozinha e rename também avançam revisão. Transferência existente valida origem e destino. GET de comanda não reabre uma já encerrada.
- SSE anuncia alterações e a tela relê a comanda canônica. Reconexão relê imediatamente; falha de qualquer canal mantém polling de 15 segundos. Alteração remota atualiza tela limpa; edição local ou checkout em andamento recebem conflito explícito, preservando os dados até escolha do operador. Finalização concorrente não cria duas vendas da mesma comanda.
- Caixa exige chave de tentativa. Fingerprint e recibo compartilham transação com o efeito interno; mesmo conteúdo repete resposta, outro ator/terminal/conteúdo conflita. Recibos monetários não são removidos pela limpeza genérica, mesmo expirados. Histórico incompleto não recebe evidência inventada.
- Venda exige chave no HTTP, guarda contexto e total revisado, e oferece consulta GET após falha de resposta, inclusive com turno já fechado. A tela conserva somente a chave em sessionStorage e consulta antes de novo POST. Pedido registrado não é apresentado como prova de captura do pagamento.
- PIX/cartão preservam valor e referência explícitos. Dinheiro único permite troco; pagamento misto deve fechar exatamente o total. Isso **altera** a política anterior de troco em misto: testes antigos foram atualizados conscientemente, sem esconder a mudança como simples reparo de fixture.
- Autoria é escrita pelo servidor em `SessionItem.meta.pos_authorship`, com criador, último editor, nomes e horários. Save sem alteração preserva a autoria; dados enviados pelo browser não podem forjá-la. Linhas históricas não ganham criador presumido. Sem migration, tabela paralela ou consulta de usuário por linha.

## Tratamento visual

A linha prioriza quantidade, nome e total. Observações e cozinha permanecem visíveis. Último operador aparece discretamente; selecionar a linha revela criador quando diferente, horário e controles de quantidade/remoção. Só uma linha exibe controles por vez; a seleção múltipla mantém alvo de toque de 44 px.

Inspeção do componente real em Nuxt, com CSS real e dados sintéticos, em 320, 390, 768, 1024 e 1366 px: sem overflow horizontal; seleção por teclado e tema escuro conferidos. A primeira captura escura ocorreu durante a transição CSS; a captura final aguarda estabilização. Não foi necessário alterar o tema. Artefatos locais em `.artifacts/pdv-20260910-a1/cart-{mobile,tablet,dark}.png` e `visual-extra.log`. Isso não substitui ensaio humano com leitor, zoom 200% e telas operacionais completas.

## Evidência de validação

- Backend: **446 testes e 11 subtestes passando**, abrangendo todos os arquivos `test_pos_*.py` do Backstage, station trust, ambiguidade, remote mutations e exportação de schema.
- Frontend: 49 arquivos, **844 testes passando**, incluindo preservação de edição local, adoção explícita de conflito, recuperação por GET e autoria/controles de linha.
- Typecheck e ESLint passam. Ruff e `git diff --check` passam nos arquivos alterados.
- Build Nuxt e três E2E Chromium de login/offline passam usando portas isoladas e backend sintético. Permanecem warnings de sourcemap do Tailwind e NO_COLOR/FORCE_COLOR; não foram suprimidos.
- Dois contextos Chromium independentes acessam **Django e PostgreSQL reais** no teste `test_two_real_browser_contexts_share_edit_and_close_once`: save antigo recebe 409, outro operador edita, leitura encontra autoria, finalizações simultâneas geram um pedido e uma entrada de venda no caixa vencedor. Esse teste cobre API real em browser; não deve ser descrito como jornada completa de UI/BFF/SSE.
- Testes PostgreSQL também cobrem duas conexões concorrentes de caixa, rollback de efeito+recibo, recibo após fechamento, isolamento de ator/terminal, autoria não forjável, total alterado e retenção monetária. Exportação do contrato conferida por teste de drift.
- Logs completos ficam em `.artifacts/pdv-20260910-a1/`: `backend-all-final.log`, `frontend-final.log`, `typecheck-final.log`, `lint-final.log`, `e2e-final.log`. Os probes do primeiro handoff são evidência histórica de defeitos, não testes de aceitação da continuação.

## Limites e próximos itens do plano maior

Esta entrega implementa a fatia autorizada de runtime, CAS, valores explícitos, recibos e autoria. Ainda não encerra contrato gerado completo/remoção de fallbacks (PDV-011), fila de múltiplos PIX e reconciliação por efeito (012–015), drafts completos e política de retenção (019), display/agente/hardware, matriz operacional completa, SLO/carga e piloto (020–036). Recibo de venda comprova o pedido; recuperação do efeito externo permanece com o owner existente e deve ser consultada no gestor, sem redispatch automático. Retenção monetária exige futura política específica de reconciliação/arquivamento, não GC por idade.

Não há aceite de produção, equipamentos, tempos humanos, SLO ou piloto. Esses limites são materiais; passar testes locais não os substitui. Nenhuma migração foi aplicada a ambiente compartilhado. PostgreSQL, Redis e servidor visual desta execução são descartáveis e isolados.
