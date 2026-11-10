# Auditoria adversarial do reset arquitetural — Django Shopman
## Relatório v5 (independente) — 2026-11-10

> Lido e gravado por solicitação do dono. Auditado sobre *origin/main*, sem executar o reset.

## 0. Método, limitações e base auditada

- **SHA auditado de origin/main:** 057fe91059ba22ab62ec6638702ff7ebb03853b9 (merge PR #2259 "reset-review-decisions"). O working tree local (65b658d3) estava ~200 commits atrás; toda leitura foi via *git ls-tree / git show origin/main:...*.
- **Limitação de runtime — declarada, não simulada.** O runtime expõe um único provedor de modelo (DeepSeek). Não há Ultracode, nem modelos barato/capaz distintos, nem seleção de modelo por agente. Portanto não houve red team de segundo modelo: a passada adversarial foi feita como aço explícito contra o próprio veredito (seções 4 e 5), rotulada como tal.
- **Independência.** origin/main já continha o desfecho deste processo (Constituição reformulada em 2026-10-16, ADR-037, ADR-041, ledger DECISIONS.md). O relatório v4 não foi lido; o veredito foi derivado de código e das auditorias por app.
- **Marca de registro:** [F] fato medido; [I] inferência/julgamento; [D] dívida histórica já corrigida.

## 1. Veredito

> **APROVA COM REPAROS.**
> **Causa principal:** a hipótese está correta na direção e ~70% já está realizada — os kernels são o componente forte, e as capability ports reais (pagamento, fiscal, notificação, courier, marketing, OTP) já seguem Protocol/Adapter. O reset não é uma reescrita; é (a) encerrar a dupla autoridade em decisões de domínio, (b) dar nome e trava de import à camada de aplicação (hoje 178 services achatados), e (c) instalar o envelope de fato operacional que falta. O que derrubaria a proposta é tratá-la como mandato para generalizar capability ports e criar kernels/ports vazios para domínios futuros — a dívida do InventoryProtocol que a própria casa aposentou.

## 2. As 18 questões

**Q1 — colossal por falta de coesão ou responsabilidade legítima?** Ambos, com predominância de responsabilidade legítima, mas drift de coesão real. [F] shopman/shop tem 178 arquivos em services/, 54 em adapters/, 39 em handlers/, 7 em rules/, 23 em models/, 22 em projections/, 6 em webhooks/ (≈329 módulos Python). As cláusulas [C4](../constitution.md#c4-o-orquestrador-é-o-encontro-dos-domínios) e [C5](../constitution.md#c5-uma-decisão-tem-um-dono) da Constituição declaram essa densidade deliberada. O problema é ausência de fronteira nomeada: ifood_* (17), campaign_* (5), marketing_delivery_* (8 adapters) convivem num plano único com a política cross-domain.

**Q2 — módulos reduzem acoplamento ou só movem pasta?** Só movem pasta se a mudança for apenas de caminho. O acoplamento cai quando a decisão canônica fica exclusivamente no kernel e o módulo consome o resultado, e quando o módulo depende do port, não do provider. (Ver revisão do dono na resposta v6.)

**Q3 — kernels fortes vs aparentemente fortes.** Fortes com auditoria adversarial independente: cashman, payman, fiscalman, buyman. Aparentemente fortes (muitos testes, gaps estruturais): stockman (SPEC dispersa + promise_decision duplicada), offerman (contratos incompletos, decisões silenciosas), doorman (_link_verified_identifier importa Guestman dentro de service e engole falha — verification.py:550-595). orderman/guestman: sólidos, sem auditoria adversarial dedicada.

**Q4 — decisões com mais de uma autoridade.** [F] quatro: promise_decision (stockman availability.py:295-349 × shop adapters/stock.py:1004-1039); preço contextual (shop/services/pricing.py:resolve morto × projections/catalog_context); custo (até ADR-023); fiscal delivery (FiscalBackend.emit sem o parâmetro).

**Q5 — estados escondidos em metadata/JSON.** [F] todos os kernels usam JSONField. É padrão deliberado ("Core é Sagrado"). Custo: chaves como hold_ids, delivery_address_structured, ifood, intent_ref carregam semântica sem dono tipado. metadata.purchase.resale já morreu (shop.0073). O risco é JSON sem envelope de dono.

**Q6 — kernels substituíveis por provider externo?** [I] Nenhum kernel de fato (ledger/invariante não replica em planilha). Substituíveis são as capabilities de borda: pagamento, fiscal, notificação, courier, marketing, OTP. (Ver doutrina na resposta v6.)

**Q7 — ports necessários.** Os que já têm 2+ impls reais. Não criar port para estoque/fulfillment/produção (ADR-001: signal basta). Falta contract test por port, não mais ports.

**Q8 — providers remotos.** O Payman já codifica a resposta correta (timeout consulta gateway, dedupe durável, on_commit). Contraexemplo: fiscalman F2 (except→{} vira nota terminal). Regra: idempotência + snapshot monotônico + envio pós-commit.

**Q9 — sales × orders.** Semanticamente claro (ADR-006/C6), estruturalmente não: checkout/cart/availability no orquestrador, ciclo no Orderman.

**Q10 — módulos coerentes?** Sim como ciclos, não como kernels. Kernel de workflow é anti-padrão.

**Q11 — caixa/encerramento/checklist.** Caixa = Cashman (ADR-022). Encerramento = aplicação (cross-domain). Checklist = Taskman futuro.

**Q12 — Fiscalman suficiente?** Não, e não deveria ser: é schema+classificação+contrato; a emissão depende de Order/Payment/entrega (correto por C5). Gap é de enforcement, não titularidade.

**Q13 — Buyman e recebimento.** [F] recebimento não é gesto de kernel: Move.Kind.BUY existe e nada emite; insumo entra por seed/ajuste. Deve ser a primeira bridge buyman→stockman da Fase 2.

**Q14 — envelope de fato operacional.** [F] fragmentado: custódia de dispositivo (cashman/terminal), PIN (doorman), business_date só como scope de refs (POS_TABLE), posto/setor só em UX. Falta o value object unificado. (Detalhado na resposta v6.)

**Q15 — futuro sem mudar kernels.** Marketing (ADR-020), BI (ADR-021), Concierge (ADR-026) já desenhados. RH/Taskman consomem o envelope Q14 — único fundamento a criar agora.

**Q16 — hard reset vs incremental.** Pré-go-live, reset cirúrgico da camada de aplicação preservando kernels é o mais seguro. Perigo é ler "reset" como licença para reescrever kernel bom.

**Q17 — evitar legacy.** Convenções já existem (zero-residual, zero aliases, make inflight). Falta executar a faxina: gêmeo legado de caixa (backstage/models/cash_register.py) e caminho morto pricing.py:resolve.

**Q18 — executável.** Ver seção 3.10.

## 3. Entregáveis

**3.1 Mapa.** Kernels→ports→módulos→projections→integrations→surfaces. Já existe em grande parte: [mapa semântico da Constituição](../constitution.md#3-mapa-semântico-mínimo), shop/protocols.py (ports), projections/ (22) e adapters/ (54). O reset adiciona a camada de módulos nomeados.

**3.2 Glossário.** Recomendados: os 13 nomes canônicos de kernel + módulos sales/orders/fulfillment/production/procurement/fiscal/delivery. Rejeitados: omniman, offering/stocking/ordering, priceman (sem 2 distribuições reais), operations/checklistman, aparelho.

**3.3 Matriz.** cashman/payman/fiscalman-schema: manter. stockman/offerman/doorman/buyman: completar. shop/services/*: mover para módulos + gate. pricing.py:resolve (morto) e backstage cash_register.py (gêmeo): apagar. promise_decision (cópia): apagar após dual-run. Taskman/RH: não criar.

**3.4 Ciclos ponta-a-ponta.** loja, PDV, iFood, produção, compras — cada um toca 3–5 kernels e um módulo orquestra.

**3.5 Providers + contract tests.** ports = payment, fiscal, notification, courier, marketing_delivery, otp. Contract test por port: semântica, idempotência, concorrência, reversão, rastreabilidade, performance.

**3.6 Reset sem dupla autoridade.** extrair decisão para o kernel → dual-run+shadow até zero divergência → cutover → apagar cópia no commit seguinte.

**3.7 Dados/migrations/rollback.** seed regenerável → reset de dados = re-seed. Migrations append-only só pós go-live-v1. Rollback = switch por contrato, nunca reverter kernel.

**3.8 Orçamentos.** Complexidade alta só na camada de aplicação. Performance neutra (menu já 347→~10). Infra zero. Confiabilidade ganha (on_commit feito; falta WP-7 cross-check). Testes: os 6,5k são a rede; falta contract test por port.

**3.9 Fundamentos futuros.** só o envelope Q14.

**3.10 Plano por horizonte.** dias: ADR de titularidade + envelope + apagar gêmeo. 1 semana: extrair promise_decision + preço morto com dual-run. 2–4 semanas: módulos + gate + contract tests. posterior: Buyman Fase 2, Taskman.

**3.11 Dez modos de falha.** (1) ports vazios; (2) renomear sem matar duplicação; (3) reescrever kernel forte; (4) kernel de workflow; (5) substituir estoque/fulfillment por provider; (6) envelope vira kernel; (7) seed tratado como produção; (8) gêmeo legado sobrevive; (9) escrita plugável onde signal basta; (10) cutover sem dual-run.

**3.12 Condições de abort.** não provar zero-divergência; segundo consumidor real fora do shop para "kernel" interno; move tocar kernels; go-live antecipado → expand-contract.

## 4. Divergências e resolução (aço declarado)

Não houve agentes divergentes — houve aço interno registrado como tal. Aço 1: "capability ports é solução procurando problema" (verdade para 11 de 13 kernels; resolve-se escopando os 6 reais). Aço 2: "renomear 178 services é diff que toca todos os imports" (verdade; por isso o veredito exige dual-run + gate). Aço 3: "a proposta vende desacoplamento que o orquestrador nunca terá" (verdade e saudável; C4/C5 assume).

## 5. Objeção final e resposta do coordenador

> Objeção: "se os kernels são fortes e as ports já existem, o reset é só higiene, e higiene não justifica o risco."

Resposta: é mais que higiene porque a dupla autoridade em promise_decision é bug latente de consistência de estoque/promessa. Junto com o envelope Q14 e a remoção do gêmeo legado, o reset vira fechamento de contrato. Mas a objeção define o limite: o reset se justifica pelos quatro fechamentos, não pelas pastas. Se sobrarem só as pastas, o veredito cai para DERRUBA.
