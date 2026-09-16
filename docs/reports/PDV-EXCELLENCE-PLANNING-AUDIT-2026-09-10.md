# PDV — evidências da sessão de planejamento

**Data:** 2026-09-10.

**Entrega:** [plano](../plans/PDV-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-10.md) e [prompt](../plans/PDV-IRREPRESSIBLE-EXCELLENCE-PROMPT-2026-09-10.md).

**Natureza:** auditoria dirigida de código e testes para formular plano; implementação de produto não iniciada.

## 1. Proveniência e isolamento

Checkout recebido: `/Users/pablovalentini/Dev/Claude/django-shopman`, branch `codex/shopman-backstage-marketing-hardening`, HEAD `b589e22c5c6963e79c4bf735b79eaf928b9ae6f7`. Havia `.alpha-tmp/`, planos/relatórios e `output/` não rastreados de outras sessões; preservados integralmente.

Os dois inputs foram lidos integralmente, em blocos para evitar truncamento:

| Documento | Linhas | SHA-256 do conteúdo consultado |
|---|---:|---|
| `MARKETING-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md` | 1.743 | `de59ffaea5228aea38588fc3471049989cc86c06787640674837104ef1b94da4` |
| `PRODUCTION-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md` | 1.005 | `f435f49347391b7d1bdb0e9de29a3278d14d17897bb93022b2880679014ac68d` |

Uma primeira worktree de planejamento foi criada a partir do checkout recebido. A comparação das refs mostrou `main` local em `e0740f8a7452471140ee28fc251caf2684b2efa2` e `origin/main` local em `696f541055f396a16fb1c080c7bea69243df720d`, este último contendo a integração recente de Produção. O PDV diferia materialmente do checkout inicial. Nenhum fetch foi feito; não se afirma que essa era a versão mais recente disponível no servidor remoto.

A primeira worktree ficou sem alterações e foi removida ao final, sem force. A análise principal e todos os testes relatados abaixo foram feitos sobre **696f541055f396a16fb1c080c7bea69243df720d**, em:

```text
branch:   codex/pdv-excellence-plan-current-20260910
worktree: /Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-pdv-plan-current-20260910
```

Não houve merge/cherry-pick, uso de mudança não commitada de terceiros, atualização de ref remota nem escrita no checkout compartilhado. Nenhum `AGENTS.md` foi encontrado nas buscas aplicáveis desta sessão. Foi lida a skill `unfold-admin-canonical` para delimitar a parte administrativa do plano; nenhum Admin foi editado.

## 2. Escopo efetivamente inspecionado

- Planos Marketing/Produção completos e relatórios/planos anteriores de POS/Caixa/hardware como hipóteses.
- Ref local recente versus checkout recebido; branches/worktrees de PDV e Produção apenas por status/log/diff em leitura.
- Serviços POS/intent, review/close/claims/save/fire, Cashman, KDS, terminal trust, API e projections pertinentes.
- Nuxt: shell, runtime, Action transport, intent, checkout, pagamentos, customer search, print/agent/display, caixa/dia, tipos/gerador, configuração e suites.
- ADRs e contratos relevantes, especialmente offline, Cashman, Projection + Actions e corte de apresentação; inventário de testes atuais.

**Limites:** não é leitura linha a linha de todo o repositório. Não houve acesso ao app vivo, observação de operador, análise de registros reais, benchmark representativo, prova de concorrência PostgreSQL, teste completo de segurança, E2E integrado de turno, validação de hardware, gateway ou SEFAZ. O plano diferencia defeitos observados, riscos de fronteira e decisões/discovery.

## 3. Baseline executada

### Runtimes e preparação

- Node `v22.23.1`, npm `10.9.8`, selecionados com `PATH=/opt/homebrew/opt/node@22/bin:$PATH`. O Node default da máquina era 26, fora do engine 22 do projeto; não foi usado para os gates npm.
- Python `3.12.5` do executável já disponível em `/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python`.
- Para testes Python: cwd da worktree auditada, `sys.path` explicitamente priorizando raiz e cada pacote em `packages/` dessa worktree, `DJANGO_SETTINGS_MODULE=config.settings_test`, `DATABASE_URL=''` e `REDIS_URL=''`. Não foi transportado `.env` de terceiro; banco de teste SQLite e adapters herméticos. O ambiente virtual não foi alterado.
- `npm ci --no-audit --no-fund` em `surfaces/pos-nuxt`: 887 pacotes, passou. Depois, mesmo comando em `surfaces/operator-kit`: 659 pacotes, passou. Warning de `glob@10.5.0` deprecated não foi corrigido por atualização oportunista.

### Resultados

| Comando/escopo | Resultado observado | Interpretação |
|---|---|---|
| PDV `npm test -- --reporter=dot` | **48 arquivos, 833 testes passaram; 13,19 s** | muitos warnings Vue de lifecycle/props/stubs/atributos; não prova fluxo integrado |
| PDV `npm run lint` | **exit 1: 4 errors, 25 warnings** | dívida preexistente, sem mudança desta auditoria |
| PDV `npm run typecheck`, apenas deps do PDV | falhou, import de Vue/@vueuse/ufo no kit e erros derivados | setup incompleto do layer, não classificado como bug de negócio |
| PDV `npm run typecheck`, após `npm ci` também no kit | **passou, exit 0** | preparação de consumers/layer importa para reprodutibilidade |
| Sete módulos backend/agente listados abaixo | **182 passaram, 1 skip; 34,55 s** | SQLite; skip exige Linux; sem efeito físico |
| Quatro módulos adicionais de correções recentes | **44 passaram; 12,23 s** | prova de regressões já implementadas; não exaure multi-terminal |
| PDV `npm run build` | **passou, exit 0** | Nuxt 4.5.2 / Nitro 2.13.4 / Vue 3.5.41; warnings de plugin timings e sourcemap Tailwind |

Quatro erros de lint:

1. `app/components/PosDisplayPublisher.vue:35`: `vue/valid-template-root`.
2. `app/pages/session/index.vue:252`: `settleCustomer` não usado.
3. `tests/components/PosDrawerLockDialog.test.ts:13`: `vi` não usado.
4. `tests/composables/useDrawerIdleWatch.test.ts:8`: `ref` não usado.

Os 25 warnings são ordem de atributos em `app/pages/index.vue`. Não foram corrigidos porque esta entrega é planejamento; WP-00/WP-11 devem tratar a baseline sem reformatar trabalho alheio.

Sete módulos da primeira rodada:

```text
shopman/backstage/tests/test_pos_cash_service.py
shopman/backstage/tests/test_pos_fire.py
shopman/backstage/tests/test_pos_move_lines.py
shopman/backstage/tests/test_pos_commercial_completion.py
shopman/backstage/tests/test_pos_headless_surface_contract.py
shopman/shop/tests/test_pos_schema_export.py
tools/pos-counter-agent/test_counter_agent.py
```

O skip vem de `tools/pos-counter-agent/test_counter_agent.py`, checagem de serviço que roda somente no Linux. Os testes do agente usam mocks/fakes e servidor loopback de teste; nenhum periférico foi acionado.

Quatro módulos adicionais:

```text
shopman/backstage/tests/test_onda2_dinheiro_e_terminal.py
shopman/backstage/tests/test_terminal_ambiguo.py
shopman/backstage/tests/test_pos_cash_idempotencia.py
shopman/backstage/tests/test_pos_conflito_com_saida.py
```

Forma exata da execução Python, com a lista acima usada em cada rodada:

```python
from pathlib import Path
import os, sys
root = Path.cwd()
sys.path[:0] = [str(root), *[
    str(p) for p in sorted((root / 'packages').iterdir()) if p.is_dir()
]]
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_test'
import pytest
# pytest.main(['-q', ...paths explícitos de uma das rodadas acima...])
```

Executado via heredoc no Python indicado, com `DATABASE_URL='' REDIS_URL=''` no ambiente. Para a execução de produto, criar venv próprio e confirmar origens importadas dos packages; para concorrência, configurar PostgreSQL/Redis isolados e executar as suites sem skips pertinentes.

## 4. Reproduções mínimas de funções atuais

Foram extraídas via AST as funções `_terminal_do_pedido` e `_open_cash_shift_for_request` de `api/operations.py`, sem modificar arquivo. As dependências foram substituídas por funções fake: estação confiável `B`, turno default `shift-of-default-A`, corpo `{terminal_ref: 'A'}`.

Resultados:

```text
Estação confiável B, payload A → terminal da mutação: A
Estação confiável B → turno injetado na venda: shift-of-default-A
```

Isso prova a seleção feita pelos helpers atuais, não um lançamento financeiro real. A venda em duas estações com fixtures completas deve ser reproduzida na execução.

O TypeScript atual de `app/utils/posIntent.ts` foi transpilado em memória por `typescript.transpileModule`, executado em VM Node com stub somente do import do enum/versão. Foram chamadas as funções exportadas reais:

```text
resolvePayment([{method:'pix', amount_q:500, collection:'terminal'}], 1000)
→ {"paymentMethod":"pix","paymentTenders":[],"tenderedQ":null}

actionHref([], 'close_sale', '/api/v1/backstage/pos/sale/close/')
→ /api/v1/backstage/pos/sale/close/
```

A primeira prova perda do valor do tender no mapping; não é alegação de captura real indevida de PIX. A segunda prova fallback de transporte; não afirma que a API deixa de autorizar. O plano exige testes integrados antes de afirmar consequências adicionais.

## 5. Âncoras de código no SHA auditado

| Local | Evidência |
|---|---|
| `shopman/backstage/api/operations.py:521` | helper de runtime da venda chama `current_shift()` sem terminal |
| mesmo arquivo, `:599` | POSView já passa estação a `build_pos`; não repetir diagnóstico antigo |
| mesmo arquivo, `:2928` | idempotência Cash já existe; key ausente executa; escopo por ação |
| mesmo arquivo, `:3391` | body tem precedência sobre station ref |
| mesmo arquivo, `:4202` e `:4240` | review/close usam helper de runtime da venda |
| `shopman/shop/services/pos.py:289` e `:472` | venda e claim únicos já existem; fingerprint/obrigatoriedade incompletos |
| mesmo arquivo, `:1066` | save monta operações antes de sua transação, sem expected revision no contrato |
| mesmo arquivo, `:1385` | fire usa ledger KDS e atualiza metadata depois; composição concorrente exige prova |
| mesmo arquivo, `:1986` | desafio de desconto já delega à aprovação comum PIN/crachá |
| `shopman/shop/services/remote_mutations.py::run_idempotent_mutation/_acquire` | claim/execute/save de resposta em fronteiras separadas; crash de dinheiro a reproduzir |
| `surfaces/pos-nuxt/app/utils/posIntent.ts:63`, `:84`, `:188` | tender único, fallback e serialization somente mixed |
| `surfaces/pos-nuxt/app/composables/usePosSale.ts:1639`, `:1822`, `:2020` | busca falha→vazio, review sem epoch e mensagem absoluta após erro |
| `surfaces/pos-nuxt/app/composables/useCustomerDisplay.ts:10` | BroadcastChannel global sem terminal/publisher no contrato |
| `shopman/shop/management/commands/export_pos_schema.py` | gera versão e enums; não schema completo das Actions |
| `surfaces/pos-nuxt/playwright.config.ts` e `tests/e2e/README.md` | mock backend/desktop guards; README stale sobre páginas/router |

Linhas são âncoras históricas, não instrução de patch. Reabrir função pelo símbolo no HEAD da execução.

Correções já presentes que evitam retrabalho: negativo na abertura; strict resolver em diversas mutações; cash idempotency; line ids estáveis; KDS lock/dedupe; aprovação unificada; sensor/agente/ESC-POS/comprovante; fluxos de identidade/contato e agenda; tickets; evolução de fechamento de dia/Produção. O novo plano inclui testes para preservá-las.

## 6. Verificação documental e entrega

Esta sessão cria somente três documentos: plano, prompt e este relatório. Instalações geraram caches/dependências locais ignorados; não alteraram manifestos/lockfiles ou código de produto. Não foram copiados os planos de terceiros para o novo checkout.

Build final: Nuxt 4.5.2, Nitro 2.13.4, Vite 8.2.2, Vue 3.5.41; artefato local total de 7,03 MB (1,75 MB gzip), `Build complete`. Houve aviso de tempo concentrado em plugin hooks e três avisos `SOURCEMAP_BROKEN` do Tailwind; não se afirma build sem warnings. Não foi iniciado servidor para smoke vivo ou E2E.

Verificação documental: links relativos dos três documentos resolvem, fences Markdown estão balanceados, plano contém 13 WPs e 36 IDs únicos de backlog, com 19 achados classificados. `git diff --check` e revisão dos paths próprios fazem parte do handoff; nenhuma alteração de produto foi staged.

Resultado agregado de testes Python: **226 passaram e 1 skip** nas duas rodadas distintas. Somados aos 833 frontend, esses números descrevem apenas as suites executadas, sem cobertura total implícita. Gates humanos continuam pendentes; não foi alegada implementação técnica concluída.
