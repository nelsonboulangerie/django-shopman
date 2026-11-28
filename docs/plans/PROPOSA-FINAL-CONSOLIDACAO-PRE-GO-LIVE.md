# Proposta FINAL — consolidação pré go-live do Django Shopman
> 2026-11-10 · Sucede a [auditoria do reset arquitetural](../reports/2026-11-10-auditoria-reset-arquitetural.md) · Incorpora decisões do dono (workstation, promise_for_sku, camada de integrações, fronteira de superfície)

## 0. Decisões vinculantes (o que já está decidido)

1. **Onde:** limpar no lugar (recomendado). Se o peso do histórico bloquear, refundação com kernels importados como estão. **Veto único: não reconstruir os kernels.**
2. **"Limpo" é verificável, não subjetivo.** Gates de CI (seção 5) definem pronto.
3. **Nomenclatura:** *workstation* (não *post*); *promise_for_sku* (não *promise_decision_for_sku*).
4. **Integrações** viram camada própria (seção 4), agrupadas por provedor, selecionadas por settings.
5. **Superfícies não importam kernel** (fronteira violada hoje — ver §3).

## 1. O envelope de fato operacional

Value object *OperationalContext* em *refs* (ou *utils*), 7 campos:

- *actor_ref* — quem agiu (pessoa, sistema, papel)
- *device_ref* — de qual dispositivo
- *workstation_ref* — em qual estação física (balcão 1, forno, caixa 2, expedição)
- *sector_ref* — em qual setor organizacional (produção, salão, cozinha, admin)
- *business_date* — dia operacional (calendário do negócio, não UTC)
- *correlation_id* — com o quê se correlaciona
- *causation_ref* — por causa de quê

**workstation + sector são ambos necessários, mas com hierarquia:** *workstation* é o fato atômico (onde o ator estava); *sector* é o rollup organizacional (o que RH/Taskman/BI agregam). Uma *workstation* pertence a exatamente um *sector* num instante, logo *sector* é **derivável** de *workstation* (mapeamento workstation→sector com fonte única), nunca duas verdades que possam divergir. Captura-se *workstation_ref*; *sector_ref* deriva. Isso é a própria lei da autoridade única aplicada ao envelope.

Adoção mínima: lançamentos do Cashman, *Directive* do Orderman, *WorkOrder* do Craftsman. Não é fact-store, não é kernel.

## 2. Endurecimento dos kernels "aparentemente fortes" (não negociável)

- **Stockman:** concentrar a SPEC num módulo; *promise_for_sku* como autoridade única; matar a cópia no orquestrador (dual-run); *is_tracked* + *available_qty: Decimal|None* (sem sentinela 999999); *Quant.batch* → FK.
- **Offerman:** fechar contratos públicos; preço com autoridade única (*PricingBackend*); apagar caminho morto de preço.
- **Doorman:** *link_verified_identifier* para a bridge (adapters/customers.py) e parar de engolir exceção; desacoplar OTP de reuso interno de AccessLink.

Critério de aceite (CI): (a) autoridade única por decisão (busca de símbolo); (b) gate AST de import; (c) SPEC concentrada; (d) contract tests dos verbos públicos.

## 3. Fronteira de superfície — violação confirmada a corrigir

Fato medido em *origin/main* (057fe9105): *backstage* e *storefront/concierge* importam **models/services de kernel diretamente** e **internals do shop**, contornando o contrato Projection/Action (ADR-012/014, [cláusula C8 da Constituição](../constitution.md#c8-superfícies-são-headless-e-não-decidem), lida aqui como "Superfície não importa kernel"; ver a correção no RUNBOOK).

Exemplos concretos: *backstage/api/operations.py* importa WorkOrder, Recipe, Order, Entry, Terminal, PinCredential, CashError, InvalidTransition de 5 kernels; *backstage/admin/dashboard.py* importa Product/Shift/Order/PaymentIntent; *storefront/concierge/tools.py* importa Order, Session, Product, AccessLink de orderman/offerman/doorman; *backstage/admin/* importa *shopman.shop.services.remote_mutations*, *shopman.shop.adapters.sku_validator*, *shopman.shop.handlers._sse_emitters* (internals protegidos).

O gate atual (*test_import_boundaries.py*) cobre "kernel não importa host" e "kernel não importa kernel", mas **não cobre "superfície não importa kernel"**. Correção: adicionar esse gate + refazer as superfícies para consumir projections/services públicos do shop (a camada de módulos), não models de kernel. Workstream W4.

## 4. Camada de integrações (o "pluggável" bem entendido)

Hoje os provedores estão espalhados: iFood em *services/* (17 arquivos) + *handlers/* + *webhooks/* + *adapters/*; Efí/Stripe em *adapters/* + *webhooks/*. Isso é o "espalhado" que você sente.

Alvo — um diretório por provedor, cada um implementando UM capability port, selecionado por settings, import lazy:

- *integrations/efi/* — payment_efi + webhook pix + reconcile
- *integrations/stripe/* — payment_stripe + dispute webhook
- *integrations/focusnfe/* — fiscal_focusnfe + glue de emissão
- *integrations/ifood/* — auth, orders, catalog, events, merchant, webhook (TUDO aqui)
- *integrations/manychat/* — notification + otp + glue do concierge
- *integrations/twilio/* / *comtele/* — otp/sms
- *integrations/machine/* — courier
- *integrations/mock/* — payment_mock, courier_mock, notification_console

*handlers/* permanece (directive handlers FINOS que delegam ao módulo; não são código de integração). *webhooks/* é absorvido por *integrations/<provider>/webhook.py*.

**"Pluggável" aqui significa:** módulo coeso + seleção por settings + import lazy + implementa um port. **Não** significa plugin framework (sem entry points, sem discovery dinâmico, sem pacote pip por integração). É exatamente a doutrina da Q6: substitui-se o provedor do efeito externo, nunca o dono do invariante.

## 5. Gates de CI (a definição verificável de "limpo")

1. *make test* verde (~6,5k).
2. gate de import estendido: kernel↔kernel só em bridge; módulo↔módulo sem interno; **superfície não importa kernel**; kernel nunca importa host.
3. gate de autoridade: falha se decisão canônica tiver segunda implementação.
4. gate de legado: falha se *cash_register*/*CashShift*/*resolve* (morto) reaparecer.
5. gate de migrations: sem *multiple leaf nodes*; baseline único por app.
6. gate de superfícies/versões (existente).

## 6. Workstreams (ordem, saída verde antes da próxima)

- **W0 · Fundação (dias).** SHA; ADR de substituibilidade (Q6); ADR do envelope; squash de migrations; versionamento + CHANGELOG.
- **W1 · Encerrar dupla autoridade (1 semana).** *promise_for_sku* (extrair→dual-run→cutover→apagar); preço morto apagado; fiscal *delivery* no Protocol + contract test; *CostBackend* consumido (ADR-023/024).
- **W2 · Endurecer os 3 kernels (1–2 semanas).** Stockman/Offerman/Doorman conforme §2.
- **W3 · Envelope operacional (1 semana).** *OperationalContext* + adoção em 3 lugares + contract test.
- **W4 · Módulos + fronteira de superfície (2–4 semanas).** 178 services → 8 módulos; handlers finos; **superfícies deixam de importar kernel**; apagar gêmeo legado e caminhos mortos; gate de import completo ligado.
- **W5 · Integrações (1–2 semanas).** consolidar provedores em *integrations/* + contract tests por port (semântica, idempotência, concorrência, reversão, rastreabilidade, performance).
- **W6 · Recebimento + go-live readiness.** bridge buyman→stockman emitindo *Move.Kind.BUY*; deploy checks (resolver fiscal, cross-check caixa×payman).

## 7. O que NÃO fazer

Não criar *priceman*; não criar kernel de workflow/operations/checklist; não criar ports para estoque/fulfillment; não reconstruir cashman/payman/fiscalman; não transformar envelope em kernel; não fazer plugin framework para integrações.

## 8. Estrutura alvo

```
django-shopman/
├── packages/                  # KERNELS — intocáveis
├── shopman/
│   ├── shop/
│   │   ├── core/              # protocols, lifecycle, config, rules, models, notifications
│   │   ├── modules/           # sales, orders, fulfillment, production, procurement, fiscal, delivery, cash
│   │   ├── integrations/      # efi, stripe, focusnfe, ifood, manychat, twilio, comtele, machine, mock
│   │   ├── handlers/          # directive handlers FINOS
│   │   ├── projections/       # read models
│   │   ├── management/commands/
│   │   └── tests/
│   ├── storefront/            # headless cliente (menos import direto de kernel)
│   └── backstage/             # headless operador (menos gêmeo legado + import direto de kernel)
├── surfaces/                  # Nuxt (inalterado)
├── config/                    # project wrapper + seed
└── docs/                      # Constituição, ADRs, guias, relatórios
```

Quatro regras de fronteira (viram gate): (1) kernel é dono da decisão e não importa outro kernel (só bridge); (2) módulo é a única camada que importa 2+ kernels; (3) capability port vive na borda, provider em *integrations/*; (4) projection é read-only e superfície não importa kernel.
