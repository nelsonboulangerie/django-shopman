# ACCEPTED-STATUS-RENAME-PLAN — `confirmed` vira `accepted` no núcleo

**Status:** ✅ EXECUTADO (2026-08-01, `3b973a98` — `confirmed` vira `accepted`
no núcleo, zero residuals). Header corrigido na faxina de 2026-08-13; dizia
"não executado" com o rename já no main.
**Decisão do Pablo:** fazer **logo**, enquanto só existe seed para atualizar e
nada externo depende dos valores atuais.

## Por que agora, e não depois

A UI já mudou: o operador **aceita** ou **recusa** o pedido, e o cliente lê
"Pedido aceito" (commit `84546470`). O banco continua dizendo `confirmed`. Essa
divisão entre o que a tela fala e o que o dado guarda é a semente de bug de
leitura — alguém vai ler `confirmed` e achar que é pagamento confirmado, que foi
exatamente o susto que originou a mudança.

A janela é agora:

- **Pré-go-live.** Não existe a tag `go-live-v1`, então o ADR-015 (expand-contract,
  aliases com prazo) ainda não vale — a regra em vigor é a de zero resíduo, com
  rename total.
- **Sem consumidor externo.** iFood/Stripe/Efi não leem o status interno; eles
  falam pelos próprios contratos, traduzidos nos adapters.
- **Dados descartáveis.** Hoje o banco local tem 7 pedidos em `confirmed` (213 no
  total). Depois do go-live isso vira migração de dados de verdade, com janela
  de manutenção.

Depois do corte, o mesmo rename custa: migração de dados + alias temporário +
sprint de depreciação. Antes, custa um `sed` cuidadoso e uma migração de enum.

## Escopo medido (2026-07-31)

Ocorrências de `"confirmed"` / `Status.CONFIRMED` fora de testes:

| área | ocorrências |
|---|---|
| `packages/` (Core: orderman e vizinhos) | 31 |
| `shopman/shop/` (orquestrador) | 55 |
| `shopman/backstage/` | 9 |
| `config/` (seed) | 20 |
| `surfaces/` (Nuxt) | 6 |
| `shopman/storefront/` | 2 |
| **testes** | **166** |

Total ~289 pontos. A maioria é mecânica; o cuidado está nos três itens abaixo.

## Onde mora o risco

1. **O enum e a máquina de transições** — `packages/orderman/.../models/order.py`:
   `Status.CONFIRMED = "confirmed"`, o alias `STATUS_CONFIRMED` e o mapa
   `ALLOWED_TRANSITIONS`. É Core: mexer aqui exige migração e reler os testes de
   transição antes de tocar em qualquer outra coisa.
2. **Dados já gravados** — migração de dados reescrevendo `Order.status`
   (`confirmed` → `accepted`) e qualquer histórico/log que guarde o literal.
   Conferir também `Directive.payload` e `Session.data`, que carregam status em
   JSON (ver `docs/reference/data-schemas.md`).
3. **Strings soltas em JSON e config** — `ChannelConfig` e `RuleConfig` guardam
   status como texto em JSONField. Um `sed` no Python não alcança o que está no
   banco: precisa de passo de migração/reseed.

## Decisão pendente: até onde vai o rename

`confirmed` é um estado do PEDIDO. Mas a mesma raiz aparece em outros lugares
com sentido próprio, e não necessariamente devem mudar juntos:

- `ChannelConfig.confirmation` (aspecto de config: `mode="auto_confirm"`,
  janela de confirmação otimista) — aqui "confirmação" é a **política**, não o
  estado. Provável manter, ou renomear para `acceptance` numa segunda passada.
- Directive `confirmation.timeout` — topic persistido; renomear exige varrer
  diretivas pendentes.
- `payment_confirmed`, `has_sufficient_captured_payment` — pagamento, não
  pedido. **Não mexer**: é justamente a distinção que queremos preservar.

Recomendação: **primeira passada só no estado do pedido** (`Status.CONFIRMED` e
seus literais). Config e directive numa segunda, se valer.

## Ordem sugerida

1. Enum + transições no Core, com migração de schema.
2. Migração de dados (`confirmed` → `accepted`), incluindo JSONFields.
3. Orquestrador (`shopman/shop/`), depois backstage e storefront.
4. Superfícies Nuxt (6 pontos) e tipos-espelho.
5. Seed (`config/management/commands/seed.py`).
6. Testes (166) — por último, porque são eles que provam o resto.
7. `make test` completo (~5.000) + `make admin` + `make lint`.

## O que NÃO muda

A copy visível já está certa e não depende disto: o operador vê "Aceitar" /
"Recusar", o cliente vê "Pedido aceito" e "Aguardando a loja". Este plano é só
para o dado parar de contradizer a tela.
