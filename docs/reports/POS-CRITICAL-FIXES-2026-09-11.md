# Correções pontuais PDV — 11/09/2026

Base: `origin/main` em `7faf0259a`. Integração isolada em `codex/pos-critical-fixes-20260911`, sem alterações no checkout compartilhado. Três agentes trabalharam em worktrees independentes; sessões Storefront e Conversacional foram consultadas para evitar sobreposição. Nenhum deploy ou alteração de dados reais foi realizado.

## Resultado por solicitação

| Solicitação | Resultado |
| --- | --- |
| Pedido de troco | A troca de cédulas no PDV cria alerta `cash_change_requested` na fila canônica de operações, visível no Gestor/Admin, com terminal, operador, valor e denominações. Atendimento/cancelamento resolve o alerta na mesma transação e dispara atualização SSE. Não é suprimento nem movimentação de saldo. |
| Relogins Admin | `bootstrap_admin` e `ensure_dev_superuser` refaziam o hash mesmo quando a senha era igual. Isso invalida sessões Django. Agora preservam o hash; senha realmente alterada ainda revoga sessões. PIN, permissões e duração permanecem iguais. Documentação histórica liga bootstrap ao deploy; não foi auditada a configuração viva do job nem provado que esta era a única causa percebida no dispositivo. |
| Retirada hoje | Data explicitamente combinada, mesmo hoje, ou janela de horário exige identificação no backend e na tela. Nome, telefone ou ref do cadastro satisfazem a regra existente. Venda imediata sem agendamento pode continuar anônima. Entrega também exige identificação. |
| Cliente / recebimento / data | O chip começa com “Entrega ou retirada?”. Escolher cliente/data não confirma recebimento. O operador escolhe uma opção; fechamento tem guarda no composable e ação de recuperação no checkout. Refresh que muda a opção disponível invalida a confirmação. A agenda distingue “Sem agendamento” de “Hoje · horário a combinar”; selecionar hoje grava a data, e “Sem agendamento · levar agora” limpa o combinado. |
| Filipeta delivery | Endereço e referência vêm antes dos itens. A cobrança na entrega mostra parcelas por método, “Troco para”, “Levar de troco” ou necessidade de confirmar. Pedido já pago não recebe orientação de cobrança. |
| PIX Storefront | Não houve alteração: `.do/app.alpha-subdomains.yaml` mantém `SHOPMAN_EXPOSE_MOCK_CAPTURE=true` e `SHOPMAN_MOCK_PIX_AUTO_CONFIRM=false`. A sessão Storefront confirmou a configuração de pré-go-live: mock exige “Simular pagamento”; a confirmação Efí real é por webhook. Não se deve confundir confirmação do pedido com confirmação do pagamento. |
| Contato já cadastrado | Cadastro com nome e contato existente, sem ref selecionado, não reutiliza nem altera silenciosamente o registro. O modal mostra o dono, permite corrigir e exige confirmação para usar o cadastro. A proteção também roda no fechamento direto. Conflito concorrente no resolve retorna erro legível. Lookup puro por identificador e seleção explícita continuam disponíveis. |

## Validação integrada

- Backend: **178 testes passaram**, cobrindo agendamento, identidade de cliente, bootstrap, contrato de superfície PDV, pedido de troco, filipeta e SSE.
- Frontend: **410 testes unitários passaram** e **145 testes de componente/composable passaram** (checkout, cadastro, fechamento, identidade e refresh de recebimento).
- Typecheck Nuxt, Ruff nos módulos alterados e `git diff --check` aprovados.
- `makemigrations --check --dry-run`: sem drift; sem colisão nova para `0063`. Há prefixos históricos repetidos (`0036` e `0058`); o grafo atual foi aceito pelo Django.
- A revisão independente achou e motivou a correção da troca automática de recebimento. A revisão de cadastro não encontrou seleção silenciosa por digitação/blur.

Não houve ensaio em impressora física, sessão real do operador nem validação visual em navegador de produção. Os testes usam ambiente local e adaptadores de teste. Avisos de lifecycle Vue em harness e depreciação Node não impediram as suítes. O comando de drift usa banco local vazio e registrou avisos de tabela/configuração ainda não inicializada; concluiu com exit 0 e “No changes detected”.

## Publicação e rollback

A migração `backstage.0063_cash_change_request_alert` acrescenta uma choice de alerta; não reescreve dados nem cria coluna. Front e backend devem ser publicados juntos para refletir a regra de retirada combinada hoje. Não requer reseed, credencial ou variável nova.

Pedidos antigos de troco sem `alert_id` continuam legíveis e atendíveis, sem backfill automático. A escolha explícita de recebimento é estado da tela, não um novo campo de pedido; uma comanda reaberta para revisão solicita nova escolha, enquanto recarga da mesma comanda no checkout preserva a confirmação se o tipo continuar igual.

Rollback por reversão dos commits desta branch; não apagar eventos de caixa nem alertas já gravados. Reverter a aplicação não exige apagar o histórico ou reconciliar pagamentos.
