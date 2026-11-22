# Suíte de operador do Gestor (Playwright, Django de verdade)

O Gestor **compilado** contra o Django de uma pilha de pé, com as pessoas fazendo o que
fazem: a Gerente entra com senha e abre o dispositivo, o Caixa se identifica na tela de
bloqueio e digita o PIN no teclado da tela, o cliente novo pede pela loja e paga, a Cozinha
dá Pronto na estação. Nenhum estado nasce por API, Admin ou banco.

Regra da casa: `docs/coordination/ROUNDS/EXCELENCIA-base.md`, seção "Teste como um
operador de verdade". As jornadas a canonizar estão na seção 8 de
`docs/plans/EXCELENCIA-GESTOR-PLANO.md`.

| Spec | Jornada | Papéis |
|---|---|---|
| `j1-pedido-de-hoje.spec.ts` | J1: pedido de retirada para hoje, de ponta a ponta. Roda na hora do balcão (hoje, 10h16, pelo relógio de teste), e pula sem `OPERATOR_CONTROL_DIR` | cliente novo (loja, 375 px) · Gerente e Caixa (Gestor, 1366 px) · Cozinha (estação, 1366 px) |
| `j2-recusar-com-motivo.spec.ts` | J2: recusar um pedido pago, lendo o destino do dinheiro antes de confirmar. Roda na hora do balcão (hoje, 10h16, pelo relógio de teste), e pula sem `OPERATOR_CONTROL_DIR` | cliente novo (loja, 375 px) · Gerente e Caixa (Gestor, 1366 px) |
| `j3-aceitar-a-encomenda-com-o-dia.spec.ts` | J3: a cliente encomenda para amanhã e paga; o Caixa lê "Encomenda · Amanhã…" no Painel, na Fila, na Tabela e no sino, e aceita | cliente novo (loja, 375 px) · Gerente e Caixa (Gestor, 1366 px) |
| `j4-encomenda-no-dia-hora-da-cozinha.spec.ts` | J4: a cliente encomenda para amanhã, no turno das 15h, um item de revenda (sem lote de produção) e o Caixa aceita; o relógio da pilha vira o dia e, de manhã, a encomenda diz "Vai para a Cozinha às…" sem pedir gesto; passada essa hora, o cartão pede "Iniciar preparo". Pede o relógio de teste (`OPERATOR_CONTROL_DIR`), e pula sem ele | cliente novo (loja, 375 px) · Gerente e Caixa (Gestor, 1366 px) |
| `j5-cancelar-encomenda-paga.spec.ts` | J5: cancelar a encomenda paga antes do preparo e ver o estorno ("Estornado") | cliente novo (loja, 375 px) · Gerente com PIN (Gestor, 1366 px) |
| `j6-lote-cancelado-promessa-em-risco.spec.ts` | J6: a Gerente cancela na Produção o lote planejado de amanhã e o Gestor mostra a encomenda paga em "Promessa em risco". O lote é o do Pain au Chocolat, que nenhuma outra jornada encomenda (#3295). Pede a Produção na pilha (`OPERATOR_PRODUCTION_URL`), e pula sem ela | cliente novo (loja, 375 px) · Caixa (Gestor, 1366 px) · Gerente com PIN (Produção, 1366 px) |
| `j7-achar-o-pedido-de-ontem.spec.ts` | J7: achar o pedido de ontem pelo nome, ampliando o período. O seed garante à Ana Ferreira um pedido concluído ontem (#3295) | Gerente com PIN (Gestor, 1366 px) |
| `j8-quem-so-expede-abre-o-sino.spec.ts` | J8: quem só expede abre um aviso de pedido no sino e lê por que o detalhe não abre (#2879). Roda na hora do balcão (hoje, 10h16, pelo relógio de teste), e pula sem `OPERATOR_CONTROL_DIR` | cliente novo (loja, 375 px) · Gerente e Cozinha (Gestor, 1366 px) |
| `g07-avisar-o-cliente.spec.ts` | WP-G07: avisar o cliente com um toque (vai atrasar, faltou um item), lendo a mensagem antes de enviar; o recibo que falhou traz o WhatsApp com o mesmo texto. Roda na hora do balcão (hoje, 10h16, pelo relógio de teste), e pula sem `OPERATOR_CONTROL_DIR` | cliente novo (loja, 375 px) · Gerente e Caixa (Gestor, 1366 e 375 px) |
| `f1-nota-recusada-reprocessar.spec.ts` | F1: a cliente pede a retirada de hoje com CPF na nota e paga; o Caixa aceita, a Cozinha dá Pronto, o Caixa entrega; a SEFAZ (nota simulada) recusa, e o detalhe do pedido diz "NFC-e não autorizada" com a resposta do emissor; "Reprocessar NFC-e" emite de novo e a nota sai autorizada. Pede a nota simulada e roda na hora do balcão (`OPERATOR_CONTROL_DIR`), e pula sem ela | cliente novo (loja, 375 px) · Gerente e Caixa (Gestor, 1366 px) · Cozinha (estação, 1366 px) |
| `f2-entrega-sem-cpf.spec.ts` | F2: a cliente pede entrega para hoje sem CPF na nota e paga; o Caixa aceita e inicia, a Cozinha dá Pronto, e a NFC-e nasce com a sacola pronta, autorizada, como venda presencial (sem destinatário nem frete). Pede a nota simulada e a política de emissão do alpha (`SHOPMAN_FISCAL_EMISSION_RESOLVER`), e roda na hora do balcão; pula sem a pasta de controle | cliente novo (loja, 375 px) · Gerente e Caixa (Gestor, 1366 px) · Cozinha (estação, 1366 px) |
| `p1-pix-que-nao-confirma.spec.ts` | P1: a cliente envia o pedido com Pix e não paga; o Caixa vê o pedido esperando o pagamento; o relógio da pilha passa do prazo do Pix, o worker cancela sem cobrar, o pedido sai do painel sozinho, o detalhe diz "Nada foi cobrado · O Pix venceu" e a cliente lê "Pagamento expirado". Pede o relógio de teste (`OPERATOR_CONTROL_DIR`), e pula sem ele | cliente novo (loja, 375 px) · Gerente e Caixa (Gestor, 1366 px) |
| `l1-loja-fechada.spec.ts` | L1: a casa fechou e a cliente encomenda para amanhã e paga; a loja diz que confere o pedido quando abrir; o detalhe do Caixa conta o prazo de aceite a partir da abertura, não de agora; o relógio passa da abertura, o pedido segue esperando com o prazo que sobrou, e o Caixa aceita. Pede o relógio de teste (`OPERATOR_CONTROL_DIR`) e a casa que fecha hoje (seed com `--closing-in-minutes`, abaixo); na pilha aberta 24 h, pula e diz por quê | cliente novo (loja, 375 px) · Gerente e Caixa (Gestor, 1366 px) |
| `w1-fila-de-espera-vaga-paga.spec.ts` | W1: às 10h (relógio de teste) a cliente pede 10 Kuro Pan para hoje, mais do que a vitrine tem; o resto espera o lote do dia e ela entra na fila, sem Pix ("Você está na fila … Nada foi cobrado ainda."); no Gestor o aceite espera; a Gerente finaliza o lote do Kuro Pan na Produção; a cliente lê "Chegou a sua vez!", confirma a vaga, e só então o Pix nasce; paga, e o Caixa aceita. Pede o relógio de teste e a Produção (`OPERATOR_PRODUCTION_URL`), e a pilha semeada HOJE; roda uma vez por seed, porque finaliza o lote do dia | cliente novo (loja, 375 px) · Gerente e Caixa (Gestor, 1366 px) · Gerente com PIN (Produção, 1366 px) |
| `e1-encomendas-do-pdv.spec.ts` | E1: a cliente encomenda para amanhã, no turno das 9h, e paga; antes do aceite, a Caixa abre o dia de amanhã nas Encomendas do PDV e lê "Novo" ao lado de "Pago", o mesmo nome do Gestor; o Caixa aceita no Gestor, e no PDV o "Novo" sai, o dinheiro segue pago e o detalhe traz a cliente, "Amanhã · A partir das 9h" e o item. Pede o PDV na pilha (`OPERATOR_POS_URL`), e pula sem ele | cliente novo (loja, 375 px) · Gerente e Caixa (Gestor e PDV, 1366 px) |

Os papéis vêm de `shopman/shop/management/commands/setup_operators.py` (o `seed` roda o
comando): Gerente `joyce` (senha `admin`, PIN 1234), Caixa `fran` (PIN 1234), Cozinha
`diofer` (PIN 1234). Nunca o superusuário.

## Subir a pilha

Exemplo com as portas do WP-G00 (Django `:8062`, loja `:3180`, Cozinha `:3183`, Gestor
`:3184`, banco `shopman_exc_g00`). Use as suas se outra pilha estiver rodando: confira com
`lsof -nP -iTCP:<porta> -sTCP:LISTEN`.

1. **Ambiente do Django** (na raiz do repositório ou da worktree):

   ```bash
   export DATABASE_URL=postgres://localhost:5432/shopman_exc_g00
   export DJANGO_DEBUG=true DJANGO_ALLOWED_HOSTS='*' DJANGO_SECRET_KEY=dev-local-operador-1234567890
   export SHOPMAN_OTP_DELIVERY_CHAIN=console   # código de entrada só no log, nenhum SMS
   export SHOPMAN_STOREFRONT_BASE_URL=http://127.0.0.1:3180 SHOPMAN_KDS_BASE_URL=http://127.0.0.1:3183 SHOPMAN_ORDERS_BASE_URL=http://127.0.0.1:3184
   export CSRF_TRUSTED_ORIGINS=http://127.0.0.1:3180,http://127.0.0.1:3183,http://127.0.0.1:3184
   unset REDIS_URL
   # Relógio de teste e nota simulada (#2585): a suíte escreve nesta pasta.
   export TEST_STACK_CONTROL_DIR=/tmp/operador-controle
   export SHOPMAN_FISCAL_ADAPTER=shopman.shop.adapters.fiscal_simulated.SimulatedFiscalBackend
   # A política de emissão do alpha (.do/app.alpha-subdomains.yaml): o pagamento eletrônico
   # emite, com ou sem CPF. Sem ela, a nota só sai com CPF ou a pedido (e a F2 não tem nota).
   export SHOPMAN_FISCAL_EMISSION_RESOLVER='shopman.shop.fiscal_resolvers.on_request_or_tax_id,shopman.shop.fiscal_resolvers.eletronic_payment,shopman.shop.fiscal_resolvers.deferred_settlement,shopman.shop.fiscal_resolvers.on_requested_receipt,shopman.shop.fiscal_resolvers.intermediated_sale'
   ```

   O relógio é o arquivo `clock` da pasta (um instante ISO 8601 com fuso; sem ele, a hora
   real) e vale para o runserver e o worker ao mesmo tempo, sem reiniciar. A nota
   simulada autoriza sempre, a não ser que `fiscal.json` peça a recusa da próxima. Regra
   e limites em `docs/reference/settings.md`, seção "Pilha de teste local".

   Numa worktree, o `PYTHONPATH` precisa da worktree e de cada `packages/*` (o `.venv` da
   raiz aponta para a árvore principal). Se o Postgres local quebrar com
   `wait_c() got an unexpected keyword argument 'timeout'`, o `.venv` está com
   `psycopg-binary` atrás do `psycopg`: instale `psycopg-binary` na mesma versão com
   `pip install --no-deps --target <pasta>` e ponha a pasta na frente do `PYTHONPATH`, sem
   mexer no `.venv` compartilhado.

2. **Banco, seed, Django e worker**:

   ```bash
   createdb shopman_exc_g00
   .venv/bin/python manage.py migrate --noinput
   SHOPMAN_STAGING_AUTOPILOT=true .venv/bin/python manage.py seed --flush   # loja aberta 24h
   .venv/bin/python manage.py runserver 127.0.0.1:8062 --noreload > /tmp/operador-django.log 2>&1 &
   .venv/bin/python manage.py process_directives --watch > /tmp/operador-worker.log 2>&1 &
   ```

   O log do `runserver` é onde a loja escreve o código de entrada: a suíte o lê de lá.

   **Expediente.** A J1 pede retirada para hoje, então a loja tem de estar aberta agora.
   O seed com `SHOPMAN_STAGING_AUTOPILOT=true` abre a loja 24h (é o único efeito dele no
   seed); o `runserver` e o worker sobem SEM essa variável, senão o piloto automático
   daria os passos que a jornada quer ver o Caixa dar. Sem isso, a suíte só passa no
   horário real da casa e falha dizendo que a loja está fechada.

   **A casa que fecha (L1).** A L1 precisa de um fechamento hoje: acrescente
   `--closing-in-minutes N` ao seed (a casa abre à 0h e fecha daqui a N minutos; os
   outros dias seguem 24 h). Escolha N para fechar antes das 23h55 e bem depois de a
   suíte terminar: as outras jornadas pedem retirada para hoje no relógio real, e a loja
   encerra as retiradas de hoje antes do fechamento ("Hoje já encerramos as retiradas").
   Rode a L1 sozinha nessa pilha, ou a suíte toda com mais de uma hora de folga. Sem a
   opção, a L1 pula.

3. **Loja e Cozinha compiladas** (`nuxt dev` recarrega sozinho e derruba jornada longa):

   ```bash
   (cd surfaces/storefront-nuxt && npx nuxt build && NUXT_DJANGO_BASE_URL=http://127.0.0.1:8062 HOST=127.0.0.1 PORT=3180 node .output/server/index.mjs &)
   (cd surfaces/kds-nuxt && npx nuxt build && NUXT_DJANGO_BASE_URL=http://127.0.0.1:8062 HOST=127.0.0.1 PORT=3183 node .output/server/index.mjs &)
   ```

   **A Produção** só entra na J6. Ela liga o envelope estrito de produção, então sobe com a
   exceção declarada de teste:

   ```bash
   (cd surfaces/production-nuxt && NUXT_DJANGO_BASE_URL=http://127.0.0.1:8062 NUXT_SHOPMAN_ENVIRONMENT=local npx nuxt build && NUXT_SHOPMAN_ENVIRONMENT=test SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1 NUXT_DJANGO_BASE_URL=http://127.0.0.1:8062 HOST=127.0.0.1 PORT=3185 node .output/server/index.mjs &)
   ```

   e a suíte recebe `OPERATOR_PRODUCTION_URL=http://127.0.0.1:3185`. O PDV da E1 sobe do
   mesmo jeito (`surfaces/pos-nuxt`, outra porta), e a suíte recebe `OPERATOR_POS_URL`; a
   porta dele entra no `CSRF_TRUSTED_ORIGINS` do Django, como as outras. A Gerente vincula o
   PDV ao posto "PDV principal", que o seed cria.

4. **O Gestor** só se compila; quem o sobe é a suíte, na porta `OPERATOR_GESTOR_PORT`
   (padrão 3184):

   ```bash
   cd surfaces/orders-nuxt && npx nuxt build
   ```

**A hora do balcão (#3295).** As jornadas que pedem para HOJE e esperam o card no painel
(J1, J2, J8, G07, F1, F2) fixam o relógio da pilha em hoje, 10h16 (`atCounterHour`, em
`support/clock.ts`). Na hora real, o pedido feito pouco depois da hora cheia (13h05) pega o
horário das 14h, o Croissant vai para a Cozinha às 13h15, ainda no futuro, e o pedido vira
"Encomendas · Hoje": a jornada caía ou passava conforme o minuto em que rodava.

## Rodar

```bash
cd surfaces/orders-nuxt
OPERATOR_DJANGO_URL=http://127.0.0.1:8062 \
OPERATOR_STORE_URL=http://127.0.0.1:3180 \
OPERATOR_KITCHEN_URL=http://127.0.0.1:3183 \
OPERATOR_DJANGO_LOG=/tmp/operador-django.log \
OPERATOR_CONTROL_DIR=/tmp/operador-controle \
npm run test:operator
```

Sem essas variáveis a suíte recusa rodar e diz o que falta. `OPERATOR_CONTROL_DIR` é a mesma
pasta do `TEST_STACK_CONTROL_DIR` do Django: sem ela, as jornadas que viajam no tempo ou
roteirizam a nota pulam. As capturas de cada passo vão
para `test-results/operator/` (fora do git).

A suíte roda de novo sem reseed: cada execução cria um cliente novo (telefone sorteado) e
um dispositivo novo (contexto de navegador limpo).

## Armadilhas medidas

- **Cookies em `127.0.0.1` valem para todas as portas.** Loja, Gestor e Cozinha dividem o
  pote; por isso cada papel tem o próprio contexto de navegador. Não junte dois papéis no
  mesmo contexto.
- **Digitar antes da hidratação perde o texto.** Os helpers esperam a tela assentar antes
  de preencher o login.
- **O relógio de teste vale só para o Django.** O "agora" do Nuxt (servidor da loja e do
  Gestor) segue a hora real; o do navegador a jornada acerta com o `clock` do Playwright.
  Quem lê `datetime.now()` direto no Django (Concierge, Watchman) também segue a hora real.
- **A nota simulada não tem XML nem DANFE hospedados**: a DANFE na tela e a bobina pedem o
  XML autorizado do provedor, e a pilha não inventa um.
