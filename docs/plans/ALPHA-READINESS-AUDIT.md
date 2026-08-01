# ALPHA-READINESS-AUDIT — pronto para pessoas reais no staging?

**Status:** aberto (2026-08-01). Alpha = colocar o staging na frente de
testadores reais (amigos, equipe, alguns clientes) para exercitar o produto de
ponta a ponta. NÃO é go-live (produção): para produção, ver
[GO-LIVE-READINESS-PLAN](GO-LIVE-READINESS-PLAN.md),
[GO-LIVE-CREDENTIALS-MATRIX](GO-LIVE-CREDENTIALS-MATRIX.md) e
[GO-LIVE-SMS-WHATSAPP-STATUS](GO-LIVE-SMS-WHATSAPP-STATUS.md).

O objetivo aqui é honesto: dizer **o que já dá para testar de verdade**, **o que
está simulado/degradado no staging** (e o que isso significa para o teste), e
**o que falta fechar** para um alpha sem furos.

Staging: loja `https://shopman-staging-cdjpy.ondigitalocean.app` ·
gestor `https://gestor.boulangerie.com.br` (PIN) · admin
`https://admin.staging.nelsonboulangerie.com.br`.

---

## 1. O que já está pronto no staging (verde)

- **Pagamento fundido no acompanhamento** (PAYMENT-TRACKING-MERGE): sem rota
  `/pagamento`; Pix (QR + copia-e-cola + contador) e cartão renderizam inline no
  próprio acompanhamento. Verificado no ar.
- **Aceite otimista em 1 min** (staging): o cliente vê o QR rápido após o aceite.
- **prep_start por canal**: web espera o operador dar "Iniciar preparo" (honesto
  com o cliente remoto); iFood/PDV auto-disparam. Encomenda futura não forna antes
  do dia.
- **Pill do gestor**: pago = verde (qualquer canal/meio), esperando = ampulheta,
  marketplace pré-pago (iFood) = verde. Dinheiro = verde ao liquidar no PDV
  (tender recebido) ou COD acertado na entrega; neutro enquanto por receber.
- **Seed rico**: Cardápio 2027 (59 SKUs, coleções, bundles, receitas, fotos),
  personas (cliente novo/fiel/staff), cupons/promoções, loyalty, zonas de entrega
  + bandas de distância, slots de retirada, encomenda com produção planejada,
  happy hour, D-1 (sobras staff-only).

## 2. Roteiro de teste humano (as dimensões a exercitar)

Matriz para os testadores baterem — cada linha é um caminho que precisa "só
funcionar". Marcar ✅/❌ e anotar o pedido.

| Dimensão | Cenários a cobrir |
|---|---|
| **Pagamento** | Pix (paga / não paga → expira → cancela) · cartão (Stripe) · dinheiro (balcão/entrega) · pago iFood |
| **Fulfillment** | Retirada (slots) · entrega (endereço na zona / fora da zona / taxa por distância) |
| **Datas** | Hoje · amanhã · encomenda (data futura, dentro do lead time / além do horizonte) |
| **Descontos** | Cupom (válido / expirado / esgotado) · happy hour · loyalty (resgate) · D-1 (staff) |
| **Combinações** | Bundle · múltiplos itens · quantidades · item esgotado (estoque) · substituto |
| **Personas** | Cliente novo (OTP 1ª vez) · cliente fiel (reconhecido) · staff (D-1) |
| **Horários/dias** | Loja aberta · loja fechada (mensagem "conferimos na abertura") · vira o dia |
| **Endereço** | CEP → autofill · seleção no mapa (Google) · endereço salvo · reuso |
| **Operador (gestor)** | Aceitar/recusar · "Iniciar preparo" · avançar até pronto/entregue · KDS bump |
| **Acompanhamento** | Cada estado da cascata (recebido → pago → preparando → pronto → entregue) · SSE ao vivo |

> Pré-condição p/ testar Pix de ponta a ponta: em DEBUG/staging há "Simular
> pagamento" no acompanhamento (captura por gateway mock). Pagamento Pix REAL
> depende de sair do sandbox Efí (ver §3).

## 3. O que está simulado/degradado no staging (e o que significa)

| Área | Estado no staging | Impacto no teste |
|---|---|---|
| **Pix (Efí)** | Sandbox (QR real do sandbox, ~2,3s) | QR aparece e o fluxo roda; captura real exige "Simular pagamento" ou sair do sandbox |
| **Cartão (Stripe)** | A confirmar (adapter mock por padrão) | Validar se o staging usa Stripe test ou mock |
| **SMS (Comtele)** | ✅ configurado | OTP por SMS deve chegar de verdade |
| **WhatsApp (Meta)** | ⏳ credencial pendente | OTP/notificação por WhatsApp podem cair no fallback |
| **NFC-e (Focus NFe)** | ⏳ pendente | Sem emissão/impressão fiscal (obrigação legal — bloqueia go-live, não o alpha) |
| **iFood** | Direto ✅ staging; homologação prod pendente | Entrada de pedido iFood testável em staging |
| **Estoque** | ⚠️ "fantasma" (autosserviço) | Por isso o aceite (disponibilidade) existe antes de cobrar — não confiar 100% no número |

## 4. Comportamentos que os testadores VÃO encontrar (esperados, não bugs)

- **Espera pelo QR**: pedido web novo fica "conferindo a disponibilidade" até o
  aceite (auto em 1 min no staging, ou o operador aceita antes no gestor). Só
  então o QR do Pix aparece. É a confirmação otimista + estoque fantasma.
- **"Iniciar preparo" é do operador**: pago não vira "Em preparo" sozinho no web;
  o operador dispara no gestor. O cliente lê "Pagamento confirmado / já vamos
  começar" nesse meio-tempo.
- **Sem tela de pagamento**: tudo acontece na página do pedido. Isso é de propósito.

## 5. Pendências e decisões abertas

- [x] **Pill de dinheiro — DECIDIDO:** verde ao liquidar no PDV (tender
      recebido) ou COD acertado na entrega; neutro enquanto por receber (COD
      pendente, web pagar-na-retirada). Lê `Order.data.payment.tenders`.
- [ ] **Hydration mismatch global** (2 warnings de console em TODA página —
      header/status ao vivo): cosmético, pré-existente ao merge. Baixa prioridade.
- [ ] **Cartão no staging**: confirmar Stripe test vs mock.
- [ ] **WhatsApp Meta**: credencial (Pablo) — ver GO-LIVE-SMS-WHATSAPP-STATUS.
- [ ] **NFC-e**: pré-requisito legal de go-live, não de alpha.
- [ ] **Pix real (sair do sandbox Efí)**: para um alpha com pagamento de verdade.
- [ ] **iFood**: homologação de produção (staging já testa direto).

## 6. Gate "pode chamar os testadores?"

Mínimo para um alpha honesto (staging, sem dinheiro real):
- [x] Fusão pagamento→acompanhamento no ar e verificada.
- [x] Seed rico aplicado (dados de teste para todas as dimensões).
- [x] Aceite 1 min + prep_start operador no staging.
- [ ] Rodar o roteiro §2 uma vez (smoke humano) e anotar furos.
- [ ] Decidir o pill de dinheiro (§5).
- [ ] Alinhar com testadores o que é "simulado" (§3) — combinar que Pix é
      "Simular pagamento" enquanto o Efí estiver em sandbox.

Alpha com **pagamento real** adiciona: sair do sandbox Efí + Stripe test→live +
(recomendado) NFC-e, o que já encosta no go-live.

---

## Referências

- [GO-LIVE-READINESS-PLAN](GO-LIVE-READINESS-PLAN.md) — prontidão de produção.
- [GO-LIVE-CREDENTIALS-MATRIX](GO-LIVE-CREDENTIALS-MATRIX.md) — credenciais externas.
- [GO-LIVE-SMS-WHATSAPP-STATUS](GO-LIVE-SMS-WHATSAPP-STATUS.md) — SMS/WhatsApp.
- [PAYMENT-TRACKING-MERGE-PLAN](PAYMENT-TRACKING-MERGE-PLAN.md) — a fusão que
  habilitou este alpha.
