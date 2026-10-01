# Entrega por parceiro (TaOn/Machine): ensaio na HOMOLOGAÇÃO

Roteiro cronometrado para provar o adaptador `shopman/shop/adapters/courier_machine.py` contra a
**homologação** da Machine, do despacho ao cancelamento, antes de ligar o interruptor no alpha.
O contrato endereço a endereço está em
[DELIVERY-EXTERNAL-LOGISTICS-PLAN §2.1](../plans/DELIVERY-EXTERNAL-LOGISTICS-PLAN.md).

- Homologação: `https://api-vendas.taximachine.com.br/api/integracao` (detalhes em
  `https://api-vendas.taximachine.com.br/api/integracao/v1`).
- Produção: `https://api.taximachine.com.br/api/integracao` (detalhes em `.../api/integracao/v1`).
- A API Key é a mesma nos dois. O usuário de integração precisa da permissão "API - Entrega".
- Na doc, tudo o que se faz na homologação é simulado e não chega à central de produção.

## Antes de começar (5 min)

1. As quatro credenciais em mãos: `MACHINE_API_USER`, `MACHINE_API_PASSWORD`, `MACHINE_API_KEY`
   e um `MACHINE_WEBHOOK_TOKEN` (qualquer segredo longo; gere com
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`). Nunca entram em arquivo do
   repositório nem em mensagem.
2. Escolha onde o ensaio roda. As duas formas abaixo **não mexem no spec vivo** nem no spec do
   repositório: a env vale só para o processo do ensaio.

### Forma A: da sua máquina (passos 1 a 7)

```bash
cd django-shopman
export MACHINE_API_BASE=https://api-vendas.taximachine.com.br/api/integracao
export MACHINE_DETAILS_BASE=https://api-vendas.taximachine.com.br/api/integracao/v1
export MACHINE_API_USER=...  MACHINE_API_PASSWORD=...  MACHINE_API_KEY=...
export SHOPMAN_MACHINE_ALLOW_IN_DEBUG=true   # em DEBUG o adaptador fica inerte sem isto
.venv/bin/python manage.py shell
```

### Forma B: num console do alpha (passos 1 a 8)

`doctl apps console <app-id> web` abre um shell no contêiner que já está no ar. Ali o prefixo de
env vale só para aquele comando; o `web` que atende a loja continua com o padrão de produção do
`config/settings.py` (e sem `SHOPMAN_COURIER_ADAPTER`, nenhum pedido despacha sozinho):

```bash
MACHINE_API_BASE=https://api-vendas.taximachine.com.br/api/integracao \
MACHINE_DETAILS_BASE=https://api-vendas.taximachine.com.br/api/integracao/v1 \
MACHINE_API_USER=... MACHINE_API_PASSWORD=... MACHINE_API_KEY=... \
python manage.py shell
```

O alpha roda com `DEBUG=False`, então a trava de DEBUG não se aplica. O passo 8 (webhook)
precisa que o `web` do alpha conheça o `MACHINE_WEBHOOK_TOKEN`: isso é segredo no painel, e
quem o põe é o dono. Sem ele, o endpoint recusa tudo (401) e o passo 8 fica para depois.

## O ensaio (cerca de 15 min)

Rode os blocos em sequência no mesmo `manage.py shell`. A coluna "T" é o relógio esperado.

```python
from shopman.shop.adapters import courier_machine as m
from shopman.shop.models import Shop
from django.conf import settings
print(settings.SHOPMAN_MACHINE["base_url"], m.is_configured())
```

Confira: a base impressa é a `api-vendas` e `is_configured()` é `True`. Se não for, pare.

| T | Passo | Comando | O que conferir |
|---|---|---|---|
| 0:00 | 1. Estimar | ver bloco 1 | `CourierEstimate(value_q=..., minutes=..., km=...)` com `value_q > 0`. `CourierError` com `[...]` na mensagem é recusa da Machine: anote o código |
| 0:01 | 2. Abrir | ver bloco 2 | volta `CourierDispatchResult(courier_ref='<id>')`. Guarde o id em `ride` |
| 0:02 | 3. Status | `m.get_status(ride)` | uma letra: `D`, `G` ou `P` logo depois de abrir |
| 0:03 | 4. Detalhes | `m.get_details(ride)` | dicionário sem envelope, com `request_id == ride`; `driver` vazio até alguém aceitar. Erro 404 aqui é base de detalhes errada (`/api/integracao/v1`) |
| 0:04 | 5. Posição | `m.get_position(ride)` | `None` enquanto `D`/`G`/`P` (a doc devolve lat/lng nulos fora de A/S/E) |
| 0:05 | 6. Link de rastreio | `m.tracking_links(ride)` | lista com `link_rastreio`. **Anote o formato cru** (rode também `m._request("GET", f"/obterLinkRastreio/{ride}")`): a doc v1 mostra `{"link": ...}`, a coleção antiga mostrava lista por parada; o adaptador aceita os dois |
| 0:06 | 7. Cancelar | `m.cancel(ride)` | `True`; em seguida `m.get_status(ride) == "C"`. Recusa por `motivo_id` inválido: peça à central o id certo e use `m.cancel(ride, reason_id=<id>)`, depois ajuste `MACHINE_CANCEL_REASON_ID` |
| 0:08 | 8. Webhook (só forma B) | ver bloco 8 | dois "Webhook ... cadastrado"; abra e cancele uma segunda corrida (blocos 2 e 7) e veja o evento chegar no log do `web` |

Bloco 1, estimar (endereço da loja e um destino de teste em Londrina; a API de entregas exige o
endereço completo nos dois pontos):

```python
shop = Shop.load()
pickup = {"lat": str(shop.latitude), "lng": str(shop.longitude),
          "street": f"{shop.route} {shop.street_number}".strip(),
          "neighborhood": shop.neighborhood, "city": shop.city, "state": shop.state_code}
dropoff = {"lat": "-23.3103", "lng": "-51.1628", "street": "Avenida Higienópolis 1000",
           "neighborhood": "Centro", "city": "Londrina", "state": "PR"}
m.estimate(pickup=pickup, dropoff=dropoff)
```

Bloco 2, abrir (o mesmo corpo que `services/courier.build_machine_payload` monta para um pedido):

```python
body = {
    "forma_pagamento": settings.SHOPMAN_MACHINE["forma_pagamento"],
    "retorno": False,
    "partida": {"endereco": pickup["street"], "bairro": pickup["neighborhood"],
                "cidade": pickup["city"], "estado": pickup["state"],
                "lat": pickup["lat"], "lng": pickup["lng"]},
    "paradas": [{"endereco_parada": dropoff["street"], "bairro_parada": dropoff["neighborhood"],
                 "cidade_parada": dropoff["city"], "estado_parada": dropoff["state"],
                 "lat_parada": dropoff["lat"], "lng_parada": dropoff["lng"],
                 "id_externo": "ENSAIO-HOMOLOG-1", "observacao_parada": "Ensaio de homologação",
                 "nome_cliente_parada": "Ensaio", "telefone_cliente_parada": "43999990000"}],
}
ride = m.dispatch(body).courier_ref
ride
```

Bloco 8, webhook (forma B, com o `MACHINE_WEBHOOK_TOKEN` já no `web` do alpha e o mesmo valor
exportado no console):

```bash
MACHINE_API_BASE=https://api-vendas.taximachine.com.br/api/integracao \
MACHINE_API_USER=... MACHINE_API_PASSWORD=... MACHINE_API_KEY=... MACHINE_WEBHOOK_TOKEN=... \
python manage.py machine_register_webhook https://api.boulangerie.com.br
```

O que conferir no log do `web` (`machine.webhook raw=...`), contra o payload documentado
(DELIVERY-EXTERNAL-LOGISTICS-PLAN §2.1):

- **status**: `request_id` igual ao `ride`, `status_code` com a letra, `event_id` e `links.request`.
  A resposta do nosso endpoint é `kind: unknown_ride` (a corrida de ensaio não tem pedido): está
  certo, o evento foi entendido.
- **posicao**: só chega com corrida aceita (`A`, `S`, `E`), em lote a cada 10 s, com `data[]`.
  Na homologação sem entregador simulado ele pode não chegar; anote se chegou.
- Header `Signature-V2` presente (ainda não conferido pelo nosso endpoint).

## Depois do ensaio

- Anote no PR ou no plano: formato real do link de rastreio, `motivo_id` aceito, se o evento de
  status chegou e com que atraso.
- Os webhooks cadastrados na homologação apontam para o alpha. Para limpar, liste com
  `m._request("GET", "/listarWebhook")` e apague cada um com
  `m._request("DELETE", f"/deletarWebhook/{id}")`.
- Ligar no alpha (decisão do dono): credenciais no painel, `SHOPMAN_COURIER_ADAPTER=
  shopman.shop.adapters.courier_machine` no painel e `fulfillment.courier="auto"` no canal de
  entrega. O spec do repositório nunca carrega o interruptor: com ele e sem credenciais, o
  `check --deploy` do job release reprova com `SHOPMAN_E011` e o deploy para.

## Limites que importam no ensaio

Janela deslizante de 60 s por `api-key`; estourar devolve `429` com `Retry-After`. Na v1:
**3 consultas por minuto por solicitação** em `solicitacaoStatus`. Rodar o passo 3 em laço
apertado estoura; espere 20 s entre consultas da mesma corrida.
