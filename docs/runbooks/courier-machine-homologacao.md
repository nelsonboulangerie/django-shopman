# Entrega por parceiro (TaOn/Machine): corrida de prova e ensaio

Três roteiros neste arquivo:

1. **[Rodada de homologação da revisão das Entregas](#rodada-de-homologação-da-revisão-das-entregas-16112026)**
   (16/11/2026): todas as sondas que a revisão adversarial das Entregas deixou atrás de "homologar",
   com o que cada resposta destrava. É o roteiro da vez.
2. **[Corrida de prova em produção](#corrida-de-prova-em-produção)** (decisão do dono E2=1,
   13/10/2026): uma corrida curta de verdade, acompanhada de A a F, e outra cancelada antes da
   coleta, na janela que o dono combinar. A casa não tem chave de homologação da TaOn
   (ensaio de 01/10, abaixo).
3. **[Ensaio na homologação](#o-ensaio-cerca-de-15-min)**: o roteiro original, chamada a chamada no
   `manage.py shell`, para quando houver chave de homologação.

## Rodada de homologação da revisão das Entregas (16/11/2026)

A revisão adversarial das Entregas (DEV-2026-026) deixou atrás de "homologar" tudo o que a
documentação da TaOn não responde sozinha. Esta rodada mede cada ponto uma vez e diz qual frente
cada resposta destrava. A primeira coisa que ela destrava é a **decisão 6C do dono**: o cliente
recebe "entregue" pelo aviso da TaOn por parada, e não só no fim da corrida inteira.

Corrida aqui se chama por **letra** (A a G), como na tela.

### Onde a rodada roda, e o que pedir ao dono

| Ambiente | O que é | Custa | Credencial |
|---|---|---|---|
| **Homologação** (`api-vendas.taximachine.com.br`) | simulado: nada chega à central nem a entregador | nada | **própria**. A de produção não vale lá (medido em 01/10: "Chave da API inválida.") |
| **Produção** (`api.taximachine.com.br`) | a conta de verdade | cada corrida aberta chama entregador e é paga (a cotação de 01/10 deu R$ 8,00 para 3,4 km) | já está no app, como `SECRET` |

Três coisas a pedir ao dono, nesta ordem:

1. **"Você tem a credencial de HOMOLOGAÇÃO da TaOn?"** São três valores do ambiente `api-vendas`:
   usuário de API, senha e API Key. Se ele não tiver, quem emite é a TaOn (pedir ao suporte uma
   chave de homologação para a conta da casa).
2. **Com a credencial:** ele digita os três valores no terminal que a coordenação abre com
   `make taon-probe homolog=1` já rodando. A senha e a chave não aparecem na tela, nada vai para
   arquivo e nada passa pelo chat.
3. **Sem a credencial:** as sondas de leitura (L1 a L8) rodam em produção sem ele, pelo console do
   app. As sondas de corrida (C1 a C6) pedem uma janela de cerca de 60 min com ele presente, dois
   destinos curtos de verdade com alguém para receber, e o custo de até sete corridas curtas.

Três sondas dependem de chave que só o painel da TaOn liga (`cloud.taximachine.com.br`), e quem
liga é o dono ou a central: **impulsionamento de entregas liberado para a empresa** (sem isso o
impulsionar responde `254`), **edição de pedidos em andamento** (sem isso o `PUT` recusa) e
**solicitar código de confirmação de entrega** (decide o erro `118`).

### A ferramenta: `courier_machine_probe`

Um comando só, que **só faz `GET`** enquanto não receber `--write`. O laudo mostra formato e não
conteúdo: chaves presentes, letras de status, ids e códigos de erro. Nome, telefone, CPF, placa,
endereço, coordenada e código de confirmação saem mascarados, e link de rastreio sai só com a parte
fixa. Por isso o laudo pode ser colado no PR da rodada.

```bash
# Produção (console do app; a credencial já está lá):
doctl apps console 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f directive-worker --context shopman-do-app-admin
python manage.py courier_machine_probe --recent 3 --out /tmp/taon-laudo.txt

# Homologação (da máquina de quem roda; pergunta as três credenciais no terminal):
make taon-probe homolog=1 args='--pickup="<lat>,<lng>;<rua e número>;<bairro>;<cidade>;<UF>"'
```

| Opção | O que faz | Escreve na TaOn? |
|---|---|---|
| (nenhuma) | conta: webhooks cadastrados, categorias, e se a mesma API Key abre a v2 | não |
| `--ride <id>` | lê a corrida pelas cinco vias da v1 e pelas cinco da v2 | não |
| `--recent <n>` | lê as últimas corridas gravadas nos pedidos, as de várias paradas primeiro (só no console do app, que tem o banco) | não |
| `--stop="<ponto>"` (repetível) | cota: direta, com retorno e com paradas nos quatro formatos de `latlng_paradas` | não (cotar não abre corrida) |
| `--window <min>` | lista as corridas abertas nos últimos minutos, com o pedido de cada parada | não |
| `--out <arquivo>` | grava o laudo num arquivo | não |
| `--cancel <motivo>` | cancela a corrida com este motivo (v1) | **sim** |
| `--attach <id>[,<id>]` | agrupa estas corridas na corrida de `--ride` (v2) | **sim** |
| `--remove-stop <parada_id>` | tira a parada da corrida (v2) | **sim** |
| `--boost <reais>` | impulsiona a corrida (v2), de 2,00 a 100,00, uma vez por corrida | **sim, e gasta** |

Toda sonda que escreve pede `--write`, uma corrida só em `--ride` e o mesmo id repetido em
`--confirm`. Sem os três o comando recusa antes de chamar a TaOn.

O ponto de `--stop` e de `--pickup` é `"lat,lng;rua e número;bairro;cidade;UF"`, sempre com `=`
(`--stop="-23.31,-51.16;…"`): a latitude começa com `-` e, sem o `=`, é lida como outra opção. O
último `--stop` é o destino e os anteriores são paradas. Sem `--pickup` a partida é o endereço da
loja.

**Como ver o aviso (webhook) chegar.** Numa segunda aba, antes de abrir a primeira corrida:

```bash
doctl apps logs 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f web-operator --context shopman-do-app-admin --follow | grep machine.webhook
```

Cada linha `machine.webhook` é um aviso: o id da corrida, a letra ou o evento (`AP`, `ER`), o
`event_id`, o `stop_id` e o `will_reopen`. É por ela que se responde C1, C2 e C3.

### Sondas de leitura (sem corrida nova; rodam hoje em produção)

| # | Pergunta | Passo | É sucesso quando | Destrava |
|---|---|---|---|---|
| **L1** | A mesma API Key abre a v2? | `courier_machine_probe` sem opção | a linha `v2: a api-key VALE na v2`. Recusa `B4`, ou 403 com corpo `-`: a chave não vale e a v2 precisa de habilitação da TaOn | toda a F9 e a camada B do P1-4. Sem a v2, cada item da F9 espera a habilitação |
| **L2** | Quantas categorias a central tem? | o mesmo laudo, linha `categorias (n)` | uma categoria: o seletor de veículo fecha como `not planned` (TAON-19). Mais de uma: vira item da F9 | F9, categoria do veículo |
| **L3** | O aviso está cadastrado, e para onde? | o mesmo laudo, linhas `webhook:` | um `status` e um `posicao` apontando para `/api/webhooks/machine/`. Nenhum: rode o cadastro (passo 3 do roteiro de 13/10, abaixo) antes das sondas de corrida | F7 (sonda do watchman com `listarWebhook`) e todas as sondas C |
| **L4** | Qual é o separador de `latlng_paradas`, e a cotação conta as paradas? | `--stop=` três vezes (duas paradas e o destino), com endereços reais e curtos | exatamente um formato com `veredito … paradas contadas`. Nenhum: a cotação de várias paradas não é confiável e a sugestão não vem marcada | F4b (cotação "juntas contra separadas") e a regra de preço da F5 (marcar a sugestão só com cotação) |
| **L5** | O que uma corrida de várias paradas já feita devolve? | `--recent 3` (ou `--ride <id>` de uma corrida juntada antiga) | no laudo: `links: LISTA com n itens` ou `OBJETO ÚNICO`; `stops: n · status vistos`; `listagem: … numero_pedido em n · link_rastreio_pedido em n`; `taxas_cancelamento`. Compare o `parada_id` de cada link com o `id` de cada parada da listagem | F2a (casar o link por parada), F2b (`stop_id` por pedido), parte da #2428 e da #2427, e a taxa de cancelamento da F9 |
| **L6** | Qual é o teto de paradas? | `--stop=` seis vezes (cinco paradas e o destino). A resposta final é da central: perguntar "quantas paradas a nossa empresa pode pôr numa entrega?" | a cotação responde 200 com cinco paradas, ou recusa com o código do limite | `MAX_RIDE_STOPS` (hoje 4, no código) e a copy da corrida cheia na F5 |
| **L7** | A TaOn avisa o limite de chamadas? | `--ride <id>` de uma corrida **encerrada**, até quatro vezes em menos de um minuto (a v1 limita a 3 consultas por minuto por corrida em `solicitacao` e `solicitacaoStatus`) | uma linha `HTTP 429` com `Retry-After=`. Anote também os `X-RateLimit-*` que aparecerem nas outras linhas | F1b (429 como transitório, reagendado pelo `Retry-After`) |
| **L8** | A listagem acha uma corrida pelo pedido? | logo depois de abrir qualquer corrida da rodada: `--window 30` | a corrida aparece com `numero_pedido` igual ao pedido em **todas** as paradas. O filtro é por data: a listagem não filtra por `id_externo` | o reconcile do despacho sem resposta (P2, TAON-16): com `numero_pedido` em todas as paradas ele adota a corrida; sem isso fica a conferência manual |

L7 nunca se roda em corrida viva: o limite é por corrida, e a batida do polling disputa o mesmo
balde.

### Sondas de corrida (abrem corrida)

Na homologação, abra as corridas pelo bloco 2 do [ensaio](#o-ensaio-cerca-de-15-min), com duas
entradas em `paradas` quando a sonda pede duas paradas. Em produção, abra pelo Gestor, com pedidos
de verdade: é o caminho que prova também o nosso lado (o aviso, a tela, a página do cliente).

| # | Corrida | Pré-condição | Passo | O que anotar |
|---|---|---|---|---|
| **C1** | **A**: uma parada, com retorno (cobrança na porta em dinheiro, com troco) | aba do `machine.webhook` aberta (L3 feito) | chamar, acompanhar até o fim, e anotar a hora em que o entregador **volta** à loja | no log: a hora do `ER` (vem? traz `stop_id`?), a hora do `F`, e a hora da volta física. Depois do fim, `--ride <A>` |
| **C2** | **B**: duas paradas, com retorno | dois pedidos prontos, dois destinos | chamar juntas pelo Gestor (ou duas `paradas` no bloco 2) | no log: um `ER` por parada, cada um com o seu `stop_id`, e em que ordem. `--ride <B>` **durante** a rota (depois do primeiro `ER`) e depois do fim: `links`, `stops`, `status vistos`. A hora da volta física. É a mesma corrida do passo 6a da [corrida de prova](#corrida-de-prova-em-produção): anote também o `tracking_match` de cada pedido e abra os dois links |
| **C3** | **C**: desistência | um entregador que aceite e desista. Na homologação não há entregador: combine com a central da TaOn, ou colha o primeiro caso que acontecer sozinho | chamar, esperar o aceite e a desistência | no log: a linha `C` traz `will_reopen=true`? O `A` do entregador seguinte vem com outro `event_id` para o mesmo id de corrida? O id da corrida muda? |
| **C4** | **D**: cancelar antes do aceite | corrida recém-aberta, ainda em `D`, `G` ou `P` | `--ride <D> --cancel 1 --write --confirm <D>` e depois o mesmo com `--cancel 10` | motivo 1: recusa com código `102`? Motivo 10: sucesso, e o status seguinte é `C`? |
| **C5** | **E**: cancelar depois do aceite (opcional: tira um entregador da rua e pode gerar taxa) | corrida aceita, antes da coleta. Avise a central | `--cancel 10` e depois `--cancel 12` | motivo 10 depois do aceite: recusa `102`? Motivo 12 cancela? No dia seguinte, `--ride <E>`: `taxas_cancelamento` veio preenchida? |
| **C6** | **F** e **G**: a v2 numa corrida viva | L1 deu "VALE". Duas corridas de uma parada abertas, as duas antes do aceite | nesta ordem: `--ride <F> --attach <G>`; `--ride <G>` (só leitura); `--ride <F>` (só leitura); `--ride <F> --remove-stop <parada_id de G>`; `--ride <F> --boost 2`; `--ride <F> --cancel 10` | agrupar: 200, ou 406/409/422 com a mensagem. `G` vira `U`, e a leitura dela responde `97` com `solicitacao_agrupadora_id` igual a `F`? Os links de `F` passam a ter duas entradas? Tirar a parada: 200 com a nova `estimativa`, e o que acontece com `G` (cancele-a se voltar a existir)? Impulsionar: 200 com `origem: 'empresa'`, ou `254` (não liberado)? |
| **C7** | campos da abertura (**só na homologação**) | credencial de homologação | bloco 2 do ensaio, um campo novo por vez: `valor_cobrar` numa parada; `info_antes_aceite` com mais de 70 caracteres; `codigo_confirmacao` sem `exigir_codigo_confirmacao`; e a mesma abertura duas vezes com o mesmo `id_externo` | no painel da TaOn: o que o entregador vê de `valor_cobrar` (soma ao valor? vira cobrança na porta?). `info_antes_aceite` na v1: aceito ou ignorado, e onde corta. Código sem a exigência: recusa `118`? Mesmo `id_externo`: recusa com código `8`? Cancele cada corrida aberta (`--cancel 10`) |

O `PUT` da v2 (editar a corrida em andamento) é substituição total das paradas e só responde com a
"edição de pedidos em andamento" ligada no painel. Sonda, depois do impulsionar de C6 e antes do
cancelamento final, no `manage.py shell`:

```python
from shopman.shop.adapters import courier_machine as m
V2 = m._base_url().replace("/api/integracao", "/api/v2/integracao")
ride, stop = "<id de F>", <parada_id lido em --ride>
# A mesma parada, só com a observação trocada: é o "Atualizar a cobrança na TaOn".
m._request("PUT", f"/entregas/{ride}", base=V2, json_body={"paradas": [{
    "pedido_id": stop, "endereco_parada": "<o mesmo>", "bairro_parada": "<o mesmo>",
    "cidade_parada": "<a mesma>", "estado_parada": "<o mesmo>",
    "observacao_parada": "Sonda: cobrar R$ 58,00 em dinheiro"}]})
```

Volta `{}`: aceitou (confira a observação no painel da TaOn). `CourierError` com a mensagem da
recusa: anote o texto, que é o motivo de a edição não estar disponível.

Em produção C7 fica de fora: `codigo_confirmacao` e `valor_cobrar` numa corrida de verdade mudam o
que o entregador cobra e pede na porta. O `id_externo` repetido se responde sem abrir nada: um
pedido que teve "Chamar de novo" já abriu duas corridas com o mesmo `id_externo`. Conte quantos há
(`manage.py shell`, só leitura):

```python
from shopman.orderman.models import Order
sum(1 for o in Order.objects.filter(data__courier__has_key="attempts")
    if len(o.data["courier"]["attempts"]) > 1 or o.data["courier"].get("id_mch"))
```

Maior que zero: a TaOn aceita o `id_externo` repetido depois de uma corrida encerrada.

### O F chega na porta ou na loja? (os documentos discordam)

Dois documentos da casa dizem coisas opostas sobre a corrida com retorno, e nenhum dos dois foi
medido:

- [DELIVERY-EXTERNAL-LOGISTICS-PLAN](../plans/DELIVERY-EXTERNAL-LOGISTICS-PLAN.md), decisão 6:
  "cada pedido só vira 'entregue' no `F` da corrida inteira (com retorno, depois da volta à loja)".
- Este runbook, na corrida de prova, passo 6: "**F (finalizou)** na porta".

C1 e C2 resolvem com três horas anotadas por corrida: a do `ER`, a do `F` e a da volta física.

| Medido | O que muda |
|---|---|
| `F` chega **na porta** (antes da volta) | Entrega por parada (P1-7): o `ER` é ganho só na corrida de várias paradas; na de uma parada o `F` já basta. Falha na porta (P1-8): o `F` não prova entrega em mãos, e "Voltou com a sacola" se trata na volta, como a decisão 6C descreve. Página do cliente: o estado "voltando" depois do `F` é verdadeiro e fica |
| `F` chega **na loja** (depois da volta) | Entrega por parada (P1-7): o `ER` passa a ser a ÚNICA forma de dizer "entregue" na hora, também na corrida de uma parada com retorno; sem ele o cliente espera a volta inteira. Falha na porta (P1-8): o `F` coincide com o "Entregador voltou", e os dois gestos viram um. Página do cliente: o estado "voltando" nunca aparece depois do `F`, e sai |
| `ER` **não vem**, ou vem sem `stop_id` | a decisão 6C não tem como ser cumprida pelo aviso. Fica o interino (B, como hoje), e a alternativa é ler `stops[].status` na batida, se C2 mostrar que o status muda por parada |

Enquanto C1 e C2 não rodarem, o item "o estado 'back' diz 'está voltando' depois do F" da revisão
fica **não decidido**, e não refutado.

### Resultado → frente destravada

| Sonda | Se a resposta for | Frente |
|---|---|---|
| L5, C2: links | lista com um item por parada, com `parada_id` | confirma o casamento da F2a (já no ar): o `tracking_match` de cada pedido diz por onde o link casou (`id`, `stop` ou `position`). Se a listagem liga o `parada_id` ao nosso pedido (`paradas[].id` com `numero_pedido`), o casamento por `id` vale sempre. Fecha a medição da #2427: a parte fixa do link vira `MACHINE_TRACKING_LINK_BASE` |
| L5, C2: links | objeto único `{link}` numa corrida de várias paradas | F2a mantém a falha fechada: corrida de várias paradas sai sem link, e o botão do cliente não aparece. Resta o `link_rastreio_pedido` da listagem, se L5 mostrar que ele vem por parada |
| L5, C2: `stops`, `numero_pedido` | cada parada traz o nosso pedido (`external_id` ou `numero_pedido`) | o casamento por pedido da F2a deixa de depender da posição, e a F2b grava `courier.stop_id` por pedido |
| C2: `ER` | um por parada, com `stop_id` | **a F2b sai: decisão 6C**. O cliente recebe "entregue" na parada dele |
| C2: `stops[].status` | muda por parada durante a rota | os valores vistos preenchem `STOP_DONE_CODES` (convergência do polling). Fecha a #2428 |
| C3: `will_reopen` | vem `true` na desistência, e o id da corrida continua | confirma a F1b como foi feita. Se o campo não vier, a F1b ganha a regra de reserva: `C` seguido de `D` ou `A` do mesmo id é reabertura |
| C1, C2: hora do `F` | na porta ou na loja | a tabela da seção anterior: P1-7, P1-8 e o estado "voltando" da página do cliente |
| C4, C5: cancelamento | 1 recusa com `102` antes do aceite e 10 cancela; depois do aceite, 12 cancela | confirma a F1a (tabela letra → motivo) |
| C5: `taxas_cancelamento` | vem preenchida | F9, `cancel_fee_q` somado no B.I. |
| L1 | a chave vale na v2 | abre a F9 inteira |
| C6: agrupar | 200, e `G` responde `97` com a agrupadora | F9 encaixe (P1-14, "Encaixar na corrida B") e a camada B do P1-4 (seguir a agrupadora no `U`) |
| C6: tirar parada | 200 com a nova estimativa | F9, o pedido cancelado sai da corrida juntada (TAON-10) |
| C6: impulsionar | 200 com `origem: 'empresa'` | F9, "Aumentar a oferta". A TaOn aceita de R$ 2,00 a R$ 100,00, uma vez por corrida |
| C6: impulsionar | `254` | pedir à TaOn para liberar o impulsionamento da empresa; até lá o botão não aparece |
| `PUT` | aceita a observação nova | F9, "Atualizar a cobrança na TaOn". Recusa: a tela oferece "Ligar para o entregador" |
| `--ride`, v2 status | traz `fase` e `data_hora_*` | F8, espera no balcão por leitura. A doc diz que só o gestor da central lê este endereço (usuário de empresa recebe `67`): o esperado é a recusa, e a espera no balcão vem do aviso (`AP`, `AN`, `AW`) |
| `--ride`, v2 detalhes | `stops[].comprovante` com `url` | F9, "Ver foto da entrega" (o link vale 30 min e não se guarda) |
| L2 | uma categoria | a categoria do veículo fecha como `not planned` |
| L4 | um separador conta as paradas | a F4b cota a corrida juntada, e a F5 pode marcar a sugestão |
| L6 | teto diferente de 4 | ajustar `MAX_RIDE_STOPS` e a copy da corrida cheia |
| L7 | 429 com `Retry-After` | a F1b respeita o tempo pedido |
| L8 | `numero_pedido` em todas as paradas | o reconcile do despacho sem resposta (P2) adota a corrida achada |
| C7: `valor_cobrar` | o entregador vê como cobrança na porta | F9, `valor_cobrar` no lugar da observação. Qualquer outra leitura: não usar |
| C7: `info_antes_aceite` | a v1 aceita | F9, resumo antes do aceite com corte nosso em 70 caracteres. A v1 ignora: só pela v2 |
| C7: código de confirmação | `118` sem a exigência | #2466: o código nosso pede `exigir_codigo_confirmacao`, ou a chave ligada no painel |

### Onde anotar

Abra um PR `docs(taon): resultado da rodada de homologação` que preenche a tabela abaixo neste
arquivo e cola o laudo de cada sonda (`--out`). Comente o resultado nas issues #2428 e #2427 e
feche a que a rodada responder.

| Sonda | Data | Ambiente | Resultado | Laudo |
|---|---|---|---|---|
| L1 | | | | |
| L2 | | | | |
| L3 | | | | |
| L4 | | | | |
| L5 | | | | |
| L6 | | | | |
| L7 | | | | |
| L8 | | | | |
| C1 | | | | |
| C2 | | | | |
| C3 | | | | |
| C4 | | | | |
| C5 | | | | |
| C6 | | | | |
| C7 | | | | |

## 13/10/2026: a primeira corrida real ficou parada em "Procurando entregador"

Pedido `PDV-261013-S80`, corrida `776722699`, aberta 18:40:59 UTC. Medido no vivo (banco pela
conexão direta, só leitura; log do `directive-worker`):

- O polling **rodou**: 27 `courier.sync` `done` até 19:08, um por minuto, o primeiro 45 s depois da abertura.
- **Toda** batida caiu em `GET /solicitacaoStatus?id_mch=776722699` → `400 [67] O usuário
  informado não pode realizar essa operação.` O handler só escrevia `WARNING` no log e reagendava:
  `Order.data["courier"]["status"]` ficou `D`, nenhum SSE saiu (nada mudou), nenhum aviso.
- O webhook **não chegou**: nenhuma linha `machine.webhook` no `web-operator` desde 18:35 (o
  passo 1 do roteiro abaixo não tinha sido feito, ou não vingou).
- O mesmo `[67]` já tinha aparecido no ensaio de 01/10 com `id_mch=1` e foi lido como "a corrida 1
  não é nossa". Era a mesma recusa.

O que mudou no código (PR desta frente): a batida lê a corrida pela primeira de três vias que
responder (`/v1/request/{id}`, `/solicitacao?id=`, `/solicitacaoStatus`) e guarda o andamento
inteiro; leitura que falha aparece na tela ("sem notícias da TaOn desde HH:MM") e vira aviso ao
operador na terceira batida. **O `[67]` em si é permissão do usuário de API na TaOn** (painel:
Minha equipe > Usuário > Permissões, seção Integração). Se as três vias recusarem, o aviso diz isso
na tela, e o conserto é no painel da TaOn, não no código.

### Roteiro do dono (console do alpha; nada aqui abre corrida)

`doctl apps console 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f directive-worker --context shopman-do-app-admin`

1. **Sonda só leitura** (seis `GET`, nenhuma escrita). Mostra qual via a TaOn deixa este usuário
   ler e o formato real dos detalhes:

   ```bash
   python manage.py shell -c '
   import json
   from shopman.shop.adapters import courier_machine as m
   R = "776722699"
   for path, base, params in [("/solicitacaoStatus", None, {"id_mch": R}), ("/solicitacao", None, {"id": R}),
                              (f"/request/{R}", m._details_base(), None), (f"/obterLinkRastreio/{R}", None, None),
                              ("/posicaoCondutor", None, {"id_mch": R}), ("/listarWebhook", None, None)]:
       try:
           print("OK ", path, json.dumps(m._request("GET", path, base=base, params=params), ensure_ascii=False, default=str)[:1500])
       except Exception as exc:
           print("ERR", path, exc)
   '
   ```

   Anote no PR: quais deram `OK`. Se todas derem `[67]`, a permissão de leitura falta ao usuário
   de API no painel da TaOn.
2. **Conferir o aviso (webhook)**, só leitura: `python manage.py machine_register_webhook
   https://api.boulangerie.com.br --list`. O token sai mascarado.
3. **Cadastrar o aviso** (escreve na TaOn, por isso é do dono):
   `python manage.py machine_register_webhook https://api.boulangerie.com.br`. Repetir não duplica
   (o comando lista antes e pula o tipo já cadastrado). Depois, na próxima corrida, o log do
   `web-operator` mostra `machine.webhook raw=...` a cada mudança.

O contrato endereço a endereço está em
[DELIVERY-EXTERNAL-LOGISTICS-PLAN §2.1](../plans/DELIVERY-EXTERNAL-LOGISTICS-PLAN.md).

**Quem autentica.** A integração usa um **usuário de integração (API) da TaOn** com a permissão
"API - Entrega", por HTTP Basic (`MACHINE_API_USER`/`MACHINE_API_PASSWORD`) mais a `api-key`. Não
depende do login Gestor de uma pessoa no painel: se uma pessoa troca a senha dela, a entrega não
pode parar. No alpha as quatro `MACHINE_*` são `SECRET` no spec (conferido em 13/10/2026 com
`doctl apps spec get ... --context shopman-do-app-admin`: `MACHINE_API_USER`, `MACHINE_API_PASSWORD`,
`MACHINE_API_KEY`, `MACHINE_WEBHOOK_TOKEN` todas `type: SECRET`, e
`SHOPMAN_COURIER_ADAPTER=shopman.shop.adapters.courier_machine`). Valor de `SECRET` não se lê pelo
spec, então **qual usuário está lá se confere no painel da TaOn** (passo 0 da prova), não aqui.

## Corrida de prova em produção

> ⚠️ Corrida de produção chama entregador de verdade e custa a corrida (a cotação de 01/10 deu
> R$ 8,00 para 3,4 km). Só na janela combinada com o dono, com ele presente. Nada aqui muda o spec.

Cerca de 40 min. Precisa: o dono, o Gestor (`orders-nuxt`) aberto, o painel da TaOn aberto
(`cloud.taximachine.com.br`), um destino curto e real (alguém da casa recebe) e um console no
alpha (`doctl apps console 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f web --context shopman-do-app-admin`).

| # | Passo | O que conferir | Como desfazer |
|---|---|---|---|
| 0 | **Antes.** No painel da TaOn, Usuários: o usuário de `MACHINE_API_USER` é o de integração (API) com "API - Entrega". No Admin, o canal de entrega: `fulfillment.courier` (`auto` chama sozinho no Pronto; `none` só pelo botão). No console: `python manage.py shell -c "from shopman.shop.adapters import courier_machine as m; print(m.is_configured(), m._base_url())"` | `True` e a base `https://api.taximachine.com.br/api/integracao`. Se o usuário for o login de uma pessoa, anote e siga (a troca é decisão do dono) | nada a desfazer |
| 1 | **Registrar o aviso da TaOn** (webhook), no console: `python manage.py machine_register_webhook https://api.boulangerie.com.br` | duas linhas "Webhook 'status'/'posicao' cadastrado". Sem `MACHINE_WEBHOOK_TOKEN` o comando recusa antes de chamar a TaOn. Polling (60 s) segue como rede, então a prova não depende disto | listar `m._request("GET", "/listarWebhook")` e apagar `m._request("DELETE", f"/deletarWebhook/{id}")` |
| 2 | **Pedido A (corrida curta).** Pela loja, um pedido de entrega no destino curto, pagamento **na porta em dinheiro com troco** (prova a observação). Leve até Pronto no Gestor | o card mostra Pronto, cobrança na porta e "troco para" | cancelar o pedido no Gestor (antes do passo 3 não há corrida) |
| 3 | **Chamar entregador** no painel Entregador do pedido A (ou o `auto` chama no Pronto) | em até 1 min o painel mostra a corrida aberta; no painel da TaOn a corrida existe com a observação `Pedido A47 · Cobrar R$ … em dinheiro · troco para R$ …` e o endereço certo | antes da coleta: **Solicitar cancelamento** no Gestor; depois da coleta: ligar para a central da TaOn |
| 4 | **A (aceita)** | o painel mostra o entregador (nome, telefone, placa) e "Acompanhar corrida". **Anote o link de rastreio cru** (`courier.get_block(order)["tracking_url"]` no console): a base fixa dele é a `MACHINE_TRACKING_LINK_BASE` do modelo de WhatsApp com rastreio | idem 3 |
| 5 | **E (coletou)** ao entregar a sacola | o pedido vai sozinho para Despachado (também com cobrança na porta); sai o aviso "saiu para entrega" com o link de rastreio (SMS/e-mail); `order.data["courier"]["door_charge"]` gravado. Anote se veio por webhook (`last_source: webhook`) e o atraso | ligar para a central; o pedido segue o fluxo de entrega |
| 6 | **F (finalizou)** na porta | o pedido vai para Entregue; `final_value_q` gravado. Na volta, **Entregador voltou** fecha o acerto do dinheiro | acerto à mão no pedido, se o valor divergir |
| 6a | **Corrida de 2 paradas (link por parada).** Dois pedidos de entrega Prontos, chamados juntos na seção Entregas. No aceite (A), no console: `m.tracking_links("<id_mch>")` e, em cada pedido, `courier.get_block(order)["tracking_match"]` | anote a resposta crua: lista com uma entrada por parada, ou o objeto único `{"link"}`? A lista vem na ordem das paradas enviadas? Cada entrada traz `parada_id`, `id_externo` ou `numero_pedido`? O `tracking_match` diz como o link casou com o pedido (`id`, `stop` ou `position`); sem casamento provado o link não é gravado, e o cliente fica sem o sufixo no aviso e sem o botão na página (falha fechada). Abra os dois links: cada um mostra só a entrega do próprio cliente? | **Solicitar cancelamento** da corrida, como no passo 7 |
| 7 | **Pedido B (cancelar antes da coleta).** Outro pedido de entrega (pode ser pago online), Pronto, Chamar entregador; assim que aparecer D/G/P ou A, **Solicitar cancelamento** | corrida C no painel da TaOn; no Gestor a corrida volta ao histórico sem aviso de falha (quem cancelou foi o operador); o pedido continua Pronto, pronto para chamar de novo ou ser cancelado. Se a TaOn recusar o `motivo_id` (default 1), anote o id certo para `MACHINE_CANCEL_REASON_ID` | se o cancelamento não confirmar, ligar para a central e cancelar lá; depois cancelar o pedido B |
| 8 | **Depois** | anotar no PR desta prova: formato do link de rastreio, atraso do webhook, `motivo_id` aceito, custo final. Decidir com o dono se o polling cai para 0 (`Shop.defaults.delivery.courier_poll_seconds`) | — |

- Homologação: `https://api-vendas.taximachine.com.br/api/integracao` (detalhes em
  `https://api-vendas.taximachine.com.br/api/integracao/v1`).
- Produção: `https://api.taximachine.com.br/api/integracao` (detalhes em `.../api/integracao/v1`).
- A doc diz que a API Key é a mesma nos dois; a de produção NÃO valeu na homologação (01/10). O
  usuário de integração precisa da permissão "API - Entrega".
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
| 0:05 | 6. Link de rastreio | `m.tracking_links(ride)` | lista com `link_rastreio`. **Anote o formato cru** (rode também `m._request("GET", f"/obterLinkRastreio/{ride}")`): a doc v1 mostra `{"link": ...}`, a coleção antiga mostrava lista por parada; o adaptador aceita os dois. Anote também a **parte fixa** do link (tudo antes do pedaço que muda por corrida): ela vira `MACHINE_TRACKING_LINK_BASE` e o prefixo do botão do `pedido_saiu_entrega_rastreio` (docs/reference/whatsapp-templates-meta.md) |
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
- Header `Signature-V2` conferido pelo nosso endpoint (HMAC-SHA-512 hexadecimal do corpo cru com
  o `MACHINE_API_KEY` do `web`). Resposta `401` com `Signature-V2 não confere` no log e o corpo cru
  logado logo antes: a chave do `web` não é a que a TaOn usa para assinar (a homologação pode ter
  chave própria), ou a conta da Machine difere da documentada. Anote qual dos dois.

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

## Ensaio de 01/10/2026: o que aconteceu

Credenciais do login Gestor da empresa (painel `cloud.taximachine.com.br`, cargo de
administrador, permissões fixas com API Empresa, Entrega e Webhook; em 13/10/2026 o dono afirmou que
já existe um usuário de API da TaOn, e é ele que a integração deve usar, ver "Quem autentica") e a API Key que o dono tinha em
mãos, lidas de um arquivo fora do repositório. Nenhuma corrida foi aberta.

| Chamada | Ambiente | User-Agent | Resposta |
|---|---|---|---|
| `GET /solicitacaoStatus?id_mch=1` | homologação | `python-requests/2.32.3` | **403, página HTML** |
| `GET /solicitacaoStatus?id_mch=1` | homologação | `curl/8` | 400 JSON `"Chave da API inválida."` |
| `GET /solicitacaoStatus?id_mch=1` | produção | `python-requests/2.32.3` | **403, página HTML** |
| `GET /solicitacaoStatus?id_mch=1` | produção | `curl/8` | 400 JSON código 67 (a corrida 1 não é nossa) |
| `estimate()` (cotação, não cria corrida) | produção | `Shopman/1.0` | `CourierEstimate(value_q=800, minutes=11.0, km=3.43)` em 0,40 s |
| `GET /listarWebhook` | produção | `Shopman/1.0` | `{"webhooks": [], "quantidade_webhooks": 0}` em 0,31 s |

O que isso prova:

1. **A borda da Machine recusa o User-Agent padrão do `requests`**, nos dois ambientes. O adaptador
   passou a mandar `courier_machine.USER_AGENT`; sem isso, toda chamada em produção falharia com 403.
2. **A chave de produção não vale na homologação** ("Chave da API inválida."). A frase "a mesma
   API Key vale nos dois" não se confirmou para esta chave. Ensaiar abrir e cancelar exige uma chave
   de homologação (pedir à Machine) ou uma corrida real em produção, que chama entregador de verdade:
   as duas são decisão do dono.
3. **Credencial, cotação e leitura funcionam em produção.** Faltam provar, sem corrida real:
   abrir, status, detalhes, posição, link de rastreio, cancelar e webhook.
