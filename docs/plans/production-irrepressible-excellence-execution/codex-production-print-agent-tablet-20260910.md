# Execução — impressão térmica de Produção por PC e tablet

- Sessão: `codex-production-print-agent-tablet-20260910`
- Data: 10 de setembro de 2026, `America/Sao_Paulo`
- Worktree exclusivo: `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-production-integration-20260909`
- Branch: `codex/production-print-agent-tablet-20260910`
- SHA-base inicial: `0d9a700261639c3f83ed82a5d9fb22742c0a96b7` (cabeça validada do PR #585); integração final rebaseada sobre `9787bbcdf` (`origin/main`, inclusive PR #586).
- Plano normativo: `docs/plans/PRODUCTION-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md`, WP-P1.4 item 6 e PROD-016.
- Estado: implementação e validação local concluídas; CI/merge em preparação. Nenhum aceite físico de hardware será presumido.

## Contrato fechado com o usuário

1. O mecanismo térmico do PDV deve ser reaproveitado: o servidor compõe os bytes e um serviço no dispositivo entrega ao spooler.
2. O PDV roda tipicamente no PC conectado à impressora; os demais apps rodam sobretudo em tablets. Essa diferença não pode aparecer como configuração manual para o operador.
3. O agente permanece restrito à loopback. O cliente de transporte é compartilhado pelo `operator-kit` e o instalador autoriza explicitamente todas as origens operacionais configuradas; isso não publica a rota. Tablet não chama IP/porta do PC na LAN e não recebe segredo do agente.
4. No PC da impressora, o caminho local continua direto. No tablet, o Django mantém um trabalho durável e o agente da estação o busca por conexão HTTPS de saída.
5. Impressora e gaveta são capacidades ortogonais. Impressão não pode depender de `canKick`.
6. Aceite pelo spooler significa “enviado à fila”, nunca prova de que o papel saiu. Confirmação, erro, retry e reimpressão precisam ser honestos e auditados.
7. O caminho feliz deve deduzir estação/impressora e exigir o mínimo de decisões do operador. Se houver um único destino adequado, não existe seletor.
8. `window.print`/AirPrint é contingência explícita depois do preview congelado, nunca fallback automático após um resultado ambíguo.

## Protocolo multiagente

Auditorias somente leitura, com ownership separado, antes da implementação:

- `loss_inventory_audit`: transporte, segurança, loopback, idempotência e spooler;
- `loss_customer_audit`: modelo persistente, contrato HTTP, auditoria e concorrência;
- `loss_ux_audit`: fluxo desktop/tablet/AirPrint, linguagem, acessibilidade e critérios de aceite.

O agente raiz conservou ownership de migrations, contrato integrado, reconciliação e gates. Depois das auditorias, a implementação foi distribuída com fronteiras de arquivo explícitas: `loss_customer_audit` no backend/job durável, `loss_inventory_audit` no agente local e `loss_ux_audit` na superfície Nuxt. O integrador revisou o conjunto compartilhado, regenerou o contrato e repetiu os gates integrados.

## Achados confirmados antes da implementação

- O agente atual recebe bytes já compostos pelo servidor e os envia crus ao CUPS/Windows spooler; essa separação é correta e reutilizável.
- `useCounterAgent.print()` está acoplado à configuração da gaveta e retorna `printed` quando a fila apenas aceitou o job.
- O agente documenta e exige loopback; expô-lo na LAN criaria superfície para `/print` e `/kick` e ainda enfrentaria HTTPS/PNA nos tablets.
- A tela de Preparação ainda usa `window.print()` e não possui job persistente, destino/status, idempotência, retry nem reimpressão registrada.
- O recibo do PDV e a etiqueta são mídias distintas. A etiqueta adesiva padrão é 60×40 mm, com 52 mm úteis, configurável no Admin; continua exigindo validação no papel real.

## Decisão de precisão da balança

- A fonte canônica é `CRAFTSMAN["SCALE_PRECISION_G"]`, com padrão de `2 g`; precisão é propriedade do equipamento, não da receita nem do dado de seed.
- Para cada insumo mássico, o backend preserva o valor teórico e publica como alvo operacional o primeiro múltiplo da precisão que seja maior ou igual ao teórico. Ex.: `323 g → 324 g`, `102 g → 102 g`; nunca arredonda para baixo.
- A projeção conserva, separadamente, `theoretical_g`, `target_g`, `rounding_delta_g`, `accepted_min_g` e `accepted_max_g`. A tela e o papel mostram somente o alvo, em gramas, evitando cálculo ou decisão pelo operador.
- A faixa derivada para futura leitura de balança é `[alvo, alvo + precisão]`; ela não é apresentada como captura real enquanto o adapter de balança do WP-P2.1 não existir.
- O peso total de cada preparo soma os alvos operacionais, portanto fecha exatamente com as etiquetas individuais.
- Evidência local em 10/09/2026, precisão `2 g`: Açúcar `323 → 324 g`; Levain `2779,5 → 2780 g`; Azeite `422,484 → 424 g`.

## Implementação integrada

- `PrintJob`, `PrintAttempt` e `PrintAgentCredential` persistem documento, hashes, destino, tentativas, leases, ACK e confirmação física.
- O servidor congela e sanitiza o documento antes de compor ESC/POS. A etiqueta cega não contém receita/produto; reimpressões preservam o documento e recebem número de via.
- O agente busca trabalhos por HTTPS de saída. Tokens e endereço local nunca são projetados ao tablet. Retry só reabre falha comprovada anterior ao spool; resultado incerto exige conciliação/decisão explícita.
- No navegador, o preview e o DOM físico migram para o `print_document` congelado assim que o job existe; alterações na projeção viva não contaminam o papel.
- O seed completa configuração de impressora ausente sem sobrescrever medições/configuração já ajustadas no terminal.

## Validação local — 10/09/2026

- Backend focal: `104 passed` (jobs, blind prep, mise-en-place, margem, seed e drift do contrato).
- Agente local: `128 passed, 1 skipped`; Ruff e compilação aprovados.
- Production Nuxt: `274 passed`; typecheck, ESLint e build de produção aprovados.
- Admin/Unfold: verificador canônico aprovado; `249 passed` em integração/smoke.
- Django: `check` sem erros (somente W001/W003 já conhecidos); `makemigrations --check --dry-run` sem deriva; plano contém apenas `backstage.0058`.
- Migração `backstage.0058` aplicada no banco local; seed não destrutivo concluído e dados sensíveis à data atualizados.
- Browser QA local: `/mise-en-place` abriu por `Por preparo`, exibiu todos os alvos em gramas pares, nota de precisão, nomes + SKU, peso total, botão individual de 44 px e preview configurável 60×40 mm. `/admin`, auditoria de trabalhos e configuração do terminal renderizaram no cânone Unfold.

## Gates e evidências

- [ ] modelo/migração e concorrência em PostgreSQL — testes locais passaram; aguarda o job PostgreSQL do CI;
- [x] credencial de agente separada e nunca projetada ao tablet;
- [x] composição canônica 60×40 mm configurável, hash e documento congelado;
- [x] claim/lease/ack idempotentes e redelivery sem impressão duplicada;
- [x] fluxo PC local e fluxo tablet delegado;
- [x] preview, status, confirmação, erro, retry e reimpressão auditada;
- [x] Admin/Unfold canônico para configuração da impressora/agente;
- [x] testes Backend, Production Nuxt, counter-agent, contrato, a11y e duplo toque;
- [x] `make admin`, gates de migrations/runtime/surfaces e Browser QA;
- [x] validação visual local;
- [ ] hardware adesivo 60×40 mm real — gate humano, não substituível por preview, PDF ou mock.
