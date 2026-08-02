# Piloto automático de staging

> O staging se opera sozinho: um testador sem cozinha e sem gestor do outro lado
> vê o pedido inteiro, do "novo" ao "concluído", em poucos minutos.

## O problema

O staging existe para alguém de fora experimentar a loja. Só que a loja de
verdade tem gente do outro lado: a cozinha aciona o KDS, o gestor dá "iniciar
preparo", o balcão entrega. Sem ninguém no backstage, o pedido do testador
encalha — e ele nunca vê o que veio depois do "aceito".

Três coisas travavam o caminho:

| Trecho | Por que travava |
| --- | --- |
| `aceito → em preparo` | A loja online declara `fulfillment.prep_start="operator"` **de propósito**: o cliente remoto só lê "em preparo" quando alguém de fato encosta. |
| `em preparo → pronto` | Depende do bump dos tickets no KDS. |
| `pronto → concluído` | Depende da expedição/balcão. |
| Qualquer pedido fora de 9h–18h, seg–sáb | Loja fechada: o aceite é adiado para a próxima abertura. Quem testa às 22h ou no domingo não sai do lugar. |

## Como funciona

Um operador de mentira apertando os botões de verdade. Não existe lifecycle
paralelo:

```
order_changed ──▶ agenda Directive `staging.autopilot` (available_at = agora + 30s)
                          │
                          ▼
              handler ──▶ operator_orders.confirm_order   (novo)
                          operator_orders.advance_order   (aceito, pronto, …)
                          kds.complete_ticket             (em preparo)
                          │
                          ▼
                  a transição dispara order_changed de novo → próximo passo
```

Cada salto passa pelos **mesmos guardas** do gestor: pagamento capturado,
encomenda na data, transição válida na máquina de estados. Um guarda que
bloqueia não é erro — o passo é reagendado (teto de `MAX_DEFERRALS`, 20
tentativas). Se um operador de verdade mexer no pedido no meio do caminho, o
passo vira no-op: o status gravado no payload não bate mais e o piloto sai de
fininho.

Em `em preparo` o piloto **bumpa os tickets do KDS** em vez de usar o "avançar"
do gestor. O botão do gestor leva o pedido a "pronto" e abandona os tickets
abertos no board; a cozinha de mentira deixa o KDS do staging limpo.

Não há worker novo: o `directive-worker --watch` que já roda no staging entrega
os passos com latência de segundos.

## Ligando

| Variável | Default | O que faz |
| --- | --- | --- |
| `SHOPMAN_STAGING_AUTOPILOT` | `false` | Liga o piloto **e** faz o `seed` abrir a loja 24/7, sem feriados. |
| `SHOPMAN_STAGING_AUTOPILOT_DELAY_SECONDS` | `30` | Espera entre um passo e o outro. |
| `SHOPMAN_STAGING_AUTOPILOT_CHANNELS` | vazio (= todos) | CSV de `channel_ref`. Preencher deixa os outros canais na mão do operador. |

Já está no `.do/app.staging-subdomains.yaml`. Depois de mudar a flag, **rode o
`seed` de novo** — o horário 24/7 é dado, não código:

```bash
python manage.py seed --flush
```

Local, para experimentar:

```bash
SHOPMAN_STAGING_AUTOPILOT=true SHOPMAN_ENVIRONMENT=staging .venv/bin/python manage.py seed --flush
```

## O que o testador vê

Pedido PIX na loja online, com os defaults do staging:

| t | Estado |
| --- | --- |
| 0s | Pedido criado (`novo`) |
| ~30s | `aceito` — o piloto confirma (o timeout de 1 min do canal chegaria depois e vira no-op) |
| ~38s | PIX pago — o `payment_mock` confirma sozinho em 8s (`SHOPMAN_MOCK_PIX_CONFIRM_DELAY_SECONDS`) |
| ~60s | `em preparo` |
| ~90s | `pronto` — tickets do KDS bumpados |
| ~120s | `concluído` |

Pedido de entrega passa ainda por `despachado` e `entregue` (+60s).

No cartão o `payment_mock` autoriza na hora e a captura acontece no aceite; o
testador não vê tela de checkout de cartão (o mock não expõe `checkout_url`), o
pedido simplesmente segue pago.

## Por que nunca em produção

Lá isso avançaria pedido de cliente real sem ninguém ter encostado: cobrando,
baixando estoque e emitindo nota. Três travas:

1. **`SHOPMAN_E012`** — check de sistema: `manage.py check --deploy` falha se a
   flag estiver ligada com `SHOPMAN_ENVIRONMENT=production`.
2. **`is_enabled()`** — o agendador e o handler se calam sozinhos fora de
   `development`/`staging`, mesmo com a flag ligada.
3. **Registro condicional** — em produção o handler de `staging.autopilot` nem
   é registrado, e o receiver de `order_changed` nem é conectado.

Em staging o boot emite o `SHOPMAN_W011` como lembrete de que os pedidos andam
sozinhos.

## Onde mexer

| Arquivo | Papel |
| --- | --- |
| [`shopman/shop/services/staging_autopilot.py`](../../shopman/shop/services/staging_autopilot.py) | `is_enabled`, `schedule`, `step` — o miolo |
| [`shopman/shop/handlers/staging_autopilot.py`](../../shopman/shop/handlers/staging_autopilot.py) | Handler da Directive (reagenda no bloqueio) |
| [`shopman/shop/apps.py`](../../shopman/shop/apps.py) | Conecta o receiver de `order_changed` |
| [`shopman/shop/checks.py`](../../shopman/shop/checks.py) | `SHOPMAN_E012` / `SHOPMAN_W011` |
| [`config/management/commands/seed.py`](../../config/management/commands/seed.py) | Loja 24/7 sob a mesma flag |

Ver também: [lifecycle](lifecycle.md) · [ADR-003 (directives sem Celery)](../decisions/adr-003-directives-sem-celery.md)
