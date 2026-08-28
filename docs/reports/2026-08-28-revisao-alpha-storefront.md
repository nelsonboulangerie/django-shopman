# Revisão Alpha — Storefront (loja online, Shopman)

**Data:** 27–28/08/2026 · **Tester:** automação Playwright (Chromium, mobile Pixel 7 + smoke desktop) dirigindo a UI real · **Ambiente:** `https://alpha.nelsonboulangerie.com.br` (staging, adaptadores de pagamento em mock) · **Cliente de teste:** "QA Alpha Tester" · +55 (11) 99999-9999

## 1. Matriz executada (tudo via UI)

| Cenário | Resultado |
|---|---|
| Smoke (home, menu, PDP, busca, 404, terms/privacy, desktop) | OK — zero erros de console |
| Login sem senha | OK — WhatsApp handoff (#menu <código>) + "Não consigo usar WhatsApp" (SMS); OTP de 6 dígitos com máscara, auto-avanço, "Reenviar em Xs", "Salvar este aparelho?" (30 dias) |
| Login: telefone inválido / OTP errado | OK — "Revise o telefone — Telefone inválido." / "Código não confere — Código incorreto. (4 tentativas restantes)" |
| Caminho feliz (agendado, loja fechada) | OK — `WEB-260827-F38`: Retirada · Amanhã 15h · Pix · R$ 25,00; tracking com "Estamos fechados agora. Conferimos seu pedido quando abrirmos, amanhã às 9h." + badge de lista de espera |
| Caminho feliz (mesmo dia, loja aberta) | OK — `WEB-260828-N53`: Retirada · Hoje · Pix; Recebido → Aceito (confirmação otimista "Resposta em 00:53") → **Pago** (captura automática do mock) |
| Entrega com endereço novo | OK — `WEB-260827-J07`: busca CEP 86050-270 → sugestão → "Usar este endereço" → etiqueta (Casa/Trabalho/Outro) → frete R$ 8,00 (total R$ 33,00) |
| Mínimo de entrega (R$ 25,00) | OK — abaixo do mínimo bloqueia com aviso + swap em 1 clique "Prefere retirar? Sem mínimo." |
| Cupom inválido | OK — erro claro no passo Pagamento |
| Favoritos / Refazer pedido / Cancelamento | OK — favoritar no PDP → `/conta/favoritos`; "Refazer" → sacola populada; cancelar no tracking → histórico completo (Recebido → Cancelado) |
| Coleção estática / oferta dinâmica | OK — `/colecao/finos` e `/oferta/featured`; refs dinâmicos em `/colecao/` fazem **301 → /menu?secao=…** |
| Guardas e estados vazios | OK — `/finalizar` e `/conta` redirecionam preservando `next`; sacola vazia com copy omotenashi; busca vazia ("Nada por aqui"); 404 com UX de erro |

## 2. Achados e status de fechamento

| Sev | Achado | Status em 28/08 |
|---|---|---|
| P3 | **Hydration mismatch em `/conta/enderecos`** com endereço default: `UiBadge` (div) dentro de `<p>` → parser fecha o `<p>` no bloco e o vdom do Vue espera o aninhado. Reproduzido 3/3. | ✅ **Corrigido nesta revisão** (badge fora do `<p>` + guardrail `surfaceGuardrails`; verificado 0 warnings em dev) — aguarda deploy |
| P3 (copy) | Rótulo do Pix no checkout dizia "Aprovação na hora" (promessa que a tela não podia cumprir) | ✅ **Corrigido pelo time** (PR #381): "Pague com Pix no app do banco"; tracking distingue pagamento pendente × confirmação da loja × fila × preparo × retirada/entrega |
| P3 (rota) | `/colecao/featured` devolvia 404 (build antigo) | ✅ **Corrigido** — 301 → `/menu?secao=destaques` ao vivo |
| P3 (rede) | `POST /offers/<ref>/claim/` 404 com detail cru para oferta inexistente | ✅ **Corrigido pelo time** — `OfferUnavailable` retorna "Esta oferta não existe mais." e a página mostra a mensagem |
| P3 (ops) | Alpha expõe `debug_otp_code` + "Usar código de teste" (staging) | ✅ Guard no código: `SHOPMAN_EXPOSE_DEBUG_OTP` default = `DEBUG or staging` — **verificar que o deploy de produção não seta a env** |
| info | Lag transiente resumo×linha sob cliques rápidos de quantidade (linha R$ 78,00 vs resumo R$ 13,00 por um instante) | Não reproduzido em verificação dedicada; o checkout reprecifica no servidor (guarda `total_changed`) — sem ação |
| info | Rate-limit de login (5/min por IP) responde bem ("Muitas tentativas…") | Comportamento esperado; a suíte faz pacing/retry |

## 3. Notas

- **Pagamento Pix em pedido agendado** não mostra "Pagar agora" até a loja confirmar (por design: `post_commit`). No mock do alpha a captura é automática na aceitação; com a Efí em produção o QR ficaria pendente até o cliente pagar.
- Suíte de revisão reutilizável em `surfaces/storefront-nuxt/tests/e2e/alpha/` (25 testes; login com pacing p/ rate-limit; usa o OTP de teste do ambiente).
- Pedidos criados no alpha para limpeza: `WEB-260827-F38`, `WEB-260827-J07`, `WEB-260828-N53` (mais pedidos de re-rodadas: `WEB-260827-W92`, `WEB-260827-J25`).
