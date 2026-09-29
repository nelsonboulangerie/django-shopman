# DECISIONS — ledger de decisões

> **O que é.** Registro append-only das decisões que governam o produto, com estado explícito.
> Existe porque a queixa medida em 2026-09-29 foi: *"algumas decisões ficaram perdidas
> silenciosamente no meio do caminho"*. A apuração mostrou que o padrão **não é esquecer** —
> é que **o registro não é a verdade**: dois planos mergeados continuavam marcados "não
> iniciado"; dois ADRs implementados continuavam "Proposto"; um inventário de riscos tinha
> 3 itens já corrigidos ainda marcados como abertos, e 9 abertos sem dono.
>
> **O que isto NÃO é.** Não é um segundo plano nem uma segunda matriz de go-live. Plano diz
> *como*; isto diz *o que foi decidido, por quem, quando, e se ainda vale*. Evidência de
> execução vive no código e nos relatórios; aqui fica só o ponteiro.

## Regras

1. **Append-only.** Entrada não se apaga. Decisão que mudou ganha nova entrada e a antiga vira
   `SUPERSEDIDA`, com o id da que a substituiu.
2. **Vocabulário fechado** — só estes estados:
   `DECIDIDA` · `EM_EXECUCAO` · `EXECUTADA` · `ADIADA` · `SUPERSEDIDA` · `BLOQUEADA`.
3. **`revisar_em` é obrigatório** enquanto o estado não for terminal (`EXECUTADA` ou
   `SUPERSEDIDA`). Decisão sem data de revisão é decisão que vai apodrecer em silêncio.
4. **Toda decisão tem dono nomeado.** "Ninguém" não é dono.
5. **`EXECUTADA` exige prova**: commit, PR ou comando com saída. Sem prova, o estado máximo é
   `EM_EXECUCAO`.
6. Ligado a `scripts/check_canonical_docs.py`, que **já roda no CI** (ver
   `GO-LIVE-ACCELERATION-PLAN-2026-09-29.md` §3, Onda 3).

---

## D-001 · Forma de pagamento padrão na loja online

- **Estado:** `DECIDIDA`
- **Dono:** Pablo (produto) · execução: frente F9
- **Data:** 2026-09-29 · **revisar_em:** 2026-10-31

**Decisão:** a casa prefere **Pix** como default, *se* for obrigatório ter um. Mas se *ter* um
default se provar problema real de UX, **abre-se mão dele** — Omotenashi em primeiro lugar.
Portanto: **default só quando foi dito** (preferência lembrada do cliente, ou
`payment.default_method` declarado e validado em config), **nunca por posição na lista**.

**Consequências obrigatórias:**
- Remover o fallback posicional `|| methods[0]?.ref` (`surfaces/storefront-nuxt/app/pages/finalizar.vue:744`).
- `is_default` passa a ser dinâmico (`shopman/storefront/presentation/checkout.py:445-452`).
- A forma escolhida deve ser **audível** no resumo, com troca em 1 clique sempre disponível.
- **Instrumentar** a escolha de forma de pagamento. Hoje não existe telemetria que distinga
  **escolha ativa** de **default aceito** — sem isso, não há como medir o conserto.

**Contexto do defeito:** o testador confirmou o checkout sem perceber que Pix estava marcado.
O rótulo "(padrão)" **não existe na tela** (`is_default` é calculado e nunca renderizado).
Incidente esclarecido pelo dono (corrigido em 2026-09-29): era o **alpha, com Pix no
`payment_mock`** e captura simulada ligada — não Efí de teste. Pedido aceito abertamente como
teste, **nenhuma cobrança real**, nenhum dano. O defeito de UX permanece.

**Consequência registrada:** a rodada de testes do alpha **depende** do botão de captura simulada.
Fechar a porta exige mover o adapter, não só apagar o botão: `mock_capture_allowed`
(`shopman/shop/services/payment.py:1891-1919`) só libera a captura quando o adapter efetivo do
método **é** o simulado. Caminho prescrito: **Pix → `payment_efi` com `EFI_SANDBOX=true`** +
`SHOPMAN_EXPOSE_MOCK_CAPTURE=false`. O botão fecha por construção e o alpha passa a ensaiar o
adapter real.

**Evidência:** `docs/reports/go-live-acceleration-20260929/06-checkout-pix-default.md`

---

## D-002 · Alterar pedido da loja online pelo operador

- **Estado:** `DECIDIDA`
- **Dono:** Pablo (produto) · execução: frente a definir
- **Data:** 2026-09-29 · **revisar_em:** 2026-10-31

**Decisão:** a semântica é **(i) cobrança pendente** — o operador cancela a cobrança aberta e
emite outra. Pedido **imediato também entra** (não só os com data).

**O que isso resolve, e o que ainda falta:**
- O mecanismo de edição **já existe** e não é exclusivo de encomenda: `Order` selado +
  `Order.data["adjustment"]`, um único escritor (`order_composition.record`) e um único
  caminho de leitura (`effective_items()`/`effective_total_q()`), regra em
  `shopman/shop/services/order_edit.py`, com estoque e cozinha reconciliados pelo mesmo
  caminho do `ORDER_PATCHED` do iFood.
- **Falta exposição**, não mecanismo — declarada fora de escopo em `ENCOMENDAS-PDV-PLAN.md:229`.
- **Falta capacidade nova em dois pontos:** cancelar cobrança digital hoje só tem porta pelo
  balcão (`counter_takeover`); e `order_edit` retorna antes de tocar em `payment` quando o
  valor não muda (`order_edit.py:413-414`). Trocar a **forma** (valor constante) é o caso que
  não existe.

**Evidência:** `docs/reports/go-live-acceleration-20260929/07-alterar-pedido-gestor.md`

---

## D-003 · Qual é a superfície de atendimento do cliente

- **Estado:** `DECIDIDA`
- **Dono:** Pablo (produto)
- **Data:** 2026-09-29 · **revisar_em:** 2026-12-31

**Decisão:** a **concierge é (será) o atendimento automatizado**; **hoje**, o atendimento é o
**PDV / aba Encomendas**, operado pela equipe.

**Consequências:**
- Para o caso real do WhatsApp (cliente pede troca de forma de pagamento), o caminho canônico
  **hoje** é **deep-link para o PDV/Encomendas**, não um editor novo no Gestor de Pedidos.
- O editor no Gestor nasce quando a concierge chegar — não antes.
- **Dinheiro não entra no fluxo remoto:** pedido da loja online **não oferece pagamento em
  dinheiro**; COD, troco e tratamento de dinheiro vivem na **encomenda anotada pelo operador**
  (PDV, aba Encomendas), que já tem sessão de caixa.

---

## D-004 · Sessão de PDV compartilhada entre dispositivos e custódia da gaveta

- **Estado:** `EM_EXECUCAO`
- **Dono:** Pablo (produto/operação) · apuração técnica: sessão em andamento
- **Data:** 2026-09-29 · **revisar_em:** 2026-10-15

**Pergunta registrada pelo dono (literal):**

> "Hoje, a mesma sessão do PDV pode ser acessada em diferentes dispositivos, por diferentes
> operadores, confere? Isso é bom, conforme a sincronia é respeitada pelo sistema. Mas se a
> sessão for a mesma, a gaveta de dinheiro é uma só, confere? (é o nosso caso.) Gostaria de
> sanar essa dúvida para que não haja brecha para má operação e fraudes."

**Por que está aqui e não numa conversa:** é pergunta sobre **dinheiro e responsabilização**.
A resposta precisa ficar em lugar durável, com evidência, porque a operação real é
**uma gaveta física** e **vários dispositivos**.

**Status:** apuração em curso. Evidência será anexada em
`docs/reports/go-live-acceleration-20260929/14-sessao-pdv-multidispositivo.md` e
`15-gaveta-custodia-multidispositivo.md`.

**O que a resposta precisa cobrir, no mínimo:**
1. A mesma sessão abre mesmo em vários dispositivos? O sistema **impede** ou apenas **não detecta**?
2. O turno de caixa é por **terminal**, por **operador** ou por **sessão**?
3. Com sessão compartilhada, dois dispositivos operam a **mesma** gaveta? Dois fechamentos? Duas sangrias?
4. Cada movimento registra **qual operador** e **qual dispositivo** — ou só a sessão? (decisivo para responsabilizar)
5. O livro-caixa é append-only? O que impede editar um movimento?
6. Quais brechas concretas de má operação ou fraude existem hoje.

---

## Índice

| id | decisão | estado | revisar_em |
|---|---|---|---|
| D-001 | Forma de pagamento padrão na loja online | `DECIDIDA` | 2026-10-31 |
| D-002 | Alterar pedido da loja online pelo operador | `DECIDIDA` | 2026-10-31 |
| D-003 | Superfície de atendimento do cliente | `DECIDIDA` | 2026-12-31 |
| D-004 | Sessão de PDV multi-dispositivo e custódia da gaveta | `EM_EXECUCAO` | 2026-10-15 |
| D-005 | Marketing/WhatsApp permanece ligado como está | `DECIDIDA` | 2026-10-31 |
| D-006 | Pix simulado permanece no alpha por ora | `ADIADA` | 2026-10-15 |

---

## D-005 · Marketing/WhatsApp permanece ligado como está

- **Estado:** `DECIDIDA` · **Dono:** Pablo (produto) · **Data:** 2026-09-29 · **revisar_em:** 2026-10-31

**Decisão do dono:** *"marketing via whatsapp tem suas próprias barreiras de segurança, nada
será disparado sem querer. deixa como esta."*

**Verificado — o dono está certo:** `SHOPMAN_MARKETING_WHATSAPP_MODE=open` é **teto de
elegibilidade**, não gatilho. Nada sai sem campanha **aprovada** (`marketing_approval.py`), que
recusa por `audience_degraded` e por mínimo de audiência da loja; a serialização do ADR-009
(emenda 17/09) garante uma mensagem com flow por assinante por vez, e a ausência de cache
compartilhado derruba `canary`/`open` para falha fechado
(`shopman/shop/services/manychat_marketing_safety.py:16-29`).

**Correção de registro:** o diagnóstico inicial classificou isto como "o único risco
irreversível aberto" e recomendou desligar. **Era exagero.** Nenhuma ação pendente.

---

## D-006 · Pix simulado permanece no alpha por ora

- **Estado:** `ADIADA` · **Dono:** Pablo (produto) · **Data:** 2026-09-29 · **revisar_em:** 2026-10-15

**Decisão do dono:** *"como ainda estamos em alpha, vou manter o pix com a simulação de
pagamento mais um pouco."*

**Consequência registrada:** enquanto durar, `SHOPMAN_EXPOSE_MOCK_CAPTURE=true` +
`SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true` com Pix em `payment_mock` mantêm, no ar, a
afordância de captura simulada. Isso é **aceitável em alpha e bloqueador em produção** — a
promoção para produção (K2 do caminho crítico) tem de mover o adapter para `payment_efi`.

**Prescrição preservada para quando a hora chegar** (não desligar só a flag, porque se perde a
capacidade de testar): **Pix → `payment_efi` com `EFI_SANDBOX=true`** +
`SHOPMAN_EXPOSE_MOCK_CAPTURE=false`. `mock_capture_allowed`
(`shopman/shop/services/payment.py:1891-1919`) exige que o adapter efetivo do método **seja** o
simulado, então o botão fecha **por construção** e o alpha passa a ensaiar o adapter real.
