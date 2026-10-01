# PENDING-DECISIONS — turno autônomo 30/09 → 01/10/2026

> Decisões que só o dono toma. Cada uma: contexto em 3 linhas, opções, recomendação.
> Nenhuma foi decidida durante a noite; o trabalho seguiu por outras frentes.


## Atualização de 01/10 (manhã): o que já foi decidido e executado

| # | Estado |
|---|---|
| D1 | ✅ Opção 3 decidida e feita (#1330) |
| D2, D3, D8, D9, D10, D11 | seguem abertas, sem mudança |
| D4 | ✅ Lista aprovada feita (#1328) |
| D5 | ✅ "Etapa" feito (#1326). As três perguntas restantes viraram D19 |
| D6 | ✅ Só "Referências externas" (#1332); upload fica para o R2 |
| D7 | ✅ Critérios editáveis no Admin (#1332). Os detalhes viraram D24 |
| D12 | ✅ Pool de Redis + GC (#1331). O degrau `CONN_MAX_AGE=0` virou D21 |
| D13 | ✅ Nada a fazer: zero fichas afetadas no alpha |
| D14 | ✅ Flag aplicada no spec vivo. A rotação do token virou D22 |
| D15 | Medido sem sintoma; o chamado virou D23 |
| D16 | ✅ (a) teto da linha e (b) 1 pedido = 1 data na loja (#1329). O que sobrou virou D17 e D18 |

## D17 — Balcão: "1 linha = 1 data" NÃO existe hoje

**Contexto.** A premissa era "a comanda pode ter linhas de datas diferentes, e isso já funciona". A
apuração da Frente 2 mostrou outra coisa: a comanda tem **uma data por sessão**
(`session.data["delivery_date"]`, `shopman/shop/services/pos.py`), `POSTab` não tem data e as linhas
não carregam data; o PDV não reserva por linha. O `TestOneLineOneDate` é teste da **loja**.

**Opções.** 1) Manter a comanda com uma data (como está). 2) Construir data por linha na comanda
(atravessa cozinha, nota fiscal e fechamento do dia: frente própria, com desenho).
**Recomendação:** 1 até o go-live; 2 só se a conta aberta por dias for uso real do balcão.

## D18 — Loja: como o cliente fica sabendo que precisa de dois pedidos

**Contexto.** Desde o #1329 a sacola recusa item de outra data com "Isso fica para outro pedido" e o
botão "Ver minha sacola". O mínimo inequívoco está feito; o resto é desenho.

**Perguntas.** (a) Quando avisar: ao adicionar (hoje), só no checkout, ou antes do toque (no card).
(b) Oferecer "criar o segundo pedido" em um toque (guardar para depois, ou segunda sacola)?
(c) Item que existe nas duas datas (pronto hoje e na fornada de amanhã) com a sacola em amanhã: hoje
o pronto de hoje vence e a sacola recusa; ele deveria entrar na data da sacola?
(d) Combo no 409 de ajuste mostra o livre do componente que faltou, não o teto: aceitar?
(e) A recompra pula o item de outra data e o lista como "não entrou", sem dizer que é por data.
**Recomendação:** (a) ao adicionar, como está; (c) sim, entrar na data da sacola (é o que o cliente
espera); (b), (d), (e) depois do go-live.

## D19 — Receitas: as três perguntas que sobraram do D5

(a) Em 16/09 você decidiu que o operador só **lê** a etapa (não registra feito). Confirma?
(b) **Tempo** está no modelo (`target_seconds`); **temperatura não existe em lugar nenhum**. Entra?
Se entrar, é campo tipado (°C, afim, não fator) e precisa de valor seu: ver D20.
(c) A anotação mora na **versão** (imutável depois de publicada). Confirma?
**Recomendação:** (a) sim; (b) sim, opcional por etapa; (c) sim.

## D20 — As 92 etapas resgatadas são proposta minha, não dado da casa

**Contexto.** O processo das 11 massas foi para `docs/reference/processo-das-massas-proposta-2026-09-05.md`.
O próprio artifact de origem diz "proposta minha, é a parte que eu menos sei". É a única tabela de
temperatura que existe, mas nunca passou por você. **Pergunta:** quer revisar massa por massa (e aí
vira dado), ou fica só como rascunho?

## D21 — `DATABASE_CONN_MAX_AGE=0` (degrau 1 do D12): escrita no spec vivo

**Contexto.** O spec vivo fixa `DATABASE_CONN_MAX_AGE="60"`; sob ASGI isso não reaproveita conexão
e deixa backend ocioso até o GC (bancada: 15 ociosas depois de 100 requests; 33 a 102 com 8
concorrentes; com 0, zero). O deploy não escreve spec, e este turno só tinha autorização para a
Frente 1. **Pergunta:** aplicar (drift → backup → mudar a env → `apps update` → 42 SECRET)?
**Recomendação:** sim. Risco baixo; não mexe no PgBouncer.

## D22 — Rotacionar `EFI_WEBHOOK_TOKEN` antes de ligar a Efí de produção

Não é opcional, é item de checklist. O token é de sandbox, mas é a mesma variável que vai para
produção, onde é a autenticação **única** do webhook (sem mTLS, allowlist vazia). Rotacionar =
trocar o segredo e recadastrar a URL na Efí (o `efi_webhook --soft` do release faz isso quando o
adapter efetivo é a Efí). **Pergunta:** quando (no corte do Pix, ou já)?

## D23 — Chamado na DO pelos picos da madrugada

Hoje não reproduz (Frente 8). O chamado só serve para pedir o log do load balancer de 04:26–05:09
UTC (520 com cf-ray `a438d03fcc9597d0-GRU` às 04:44:41, fora de qualquer troca; 525 às 04:58).
Rascunho, se quiser abrir:

> **Assunto:** 520/525 e respostas lentas ou truncadas entre o edge Cloudflare e o App Platform, app
> 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f, 2026-10-01 04:26–05:09 UTC. Domínio `api.boulangerie.com.br`
> (componente `web`, 1 instância). `GET /api/v1/storefront/home/` (~19 KB) teve respostas de 15 a 40 s,
> corpo truncado (13 de 19 KB em 40 s), um 520 às 04:44:41 UTC (cf-ray a438d03fcc9597d0-GRU) e um 525 às
> 04:58 UTC. O log da aplicação mostra a resposta concluída em 1–2 s; o 520 ocorreu fora de janela de
> deploy. Hoje, 09:23–09:27 UTC, 400 requisições de teste não falharam. Pedimos os logs do load
> balancer/ingress nessa janela: resets, timeouts de upstream e falhas de handshake TLS.

**Pergunta:** abrir? **Recomendação:** só se voltar a acontecer;
a segunda instância do `web` (custo) é a resposta estrutural e é sua.

## D24 — Nota da receita: quatro detalhes de desenho (#1332)

(a) Rascunho não recebe nota (rascunho pode ser apagado). (b) Avaliar de novo substitui a nota
anterior do mesmo operador, para ninguém pesar mais na média por votar várias vezes; não há
histórico de degustação. (c) Notas e critérios não entram no cofre (backup), como a Favorita; as
referências entram (moram no `meta` da receita). (d) O bloco se chama "Referências", e a tela já usa
"referência" para as faixas da literatura; a alternativa é "Fontes".
**Recomendação:** manter as quatro como estão; trocar para "Fontes" se o operador confundir.

## D1 — Botão "Adicionar" esmaecido e inerte até a página carregar (bug B do segundo clique)

**Contexto.** No `CartQuantityAction.vue` o botão nasce `disabled` no HTML do servidor e só liga
quando o app hidrata. Ele aparece esmaecido (mesmo visual de "Indisponível"), e o toque antes da
hidratação some sem rastro. Em celular lento são alguns segundos: o cardápio inteiro parece
indisponível e só o segundo toque funciona. (A, C e D do mesmo bug entraram no #1300.)

**Opções.**
1. Manter como está. Zero código; o cliente continua lendo "indisponível" durante a carga.
2. Visual de "carregando" no lugar do esmaecido. Simples e seguro, mas muda o que todo produto
   mostra em toda carga de página.
3. Botão com cara de ativo desde o primeiro quadro; o toque precoce é guardado e repetido quando o
   app fica pronto (script inline pequeno; a CSP da loja já permite). Nenhum toque se perde; o item
   entra na sacola um instante depois do toque.
4. Botão funcionando antes do app, como formulário. Descartada: exige endpoint novo no Django.

**Recomendação:** 3. Se quiser algo menor agora, 2, sem a copy "Indisponível".

## D2 — 🔴 Stripe em modo de teste no alpha (O3c, gate de go-live)

**Contexto.** O link de pagamento do pedido `PDV-260930-R62` é `checkout.stripe.com/c/pay/cs_test_…`,
com `provider_environment: "test"` e `STRIPE_PUBLISHABLE_KEY=pk_test_…`. Mesmo que o link tivesse
chegado ao cliente, não era pagável. É credencial: o turno não toca. Diagnóstico: `03-pdv-link-pagamento.md`.

**Opções.** 1) Trocar para as chaves `live` (e o segredo do webhook live) antes do go-live.
2) Manter teste no alpha e trocar só no corte de produção, com item no checklist do go-live.

**Recomendação:** 2 se o alpha ainda não recebe cliente real; 1 assim que receber. Em qualquer caso,
um teste com cartão real de baixo valor depois da troca.

## D3 — Link de pagamento "despachado 2×, entregue 0" (O3b)

**Contexto.** O ManyChat responde `status: success` sem `message_id`, e o sistema conta isso como
entrega. O evento `payment_link_sent` não tem flow aprovado, então sai texto livre, que a Meta só
entrega dentro da janela de 24 h. A cadeia `[manychat, email, sms]` para no primeiro "sucesso":
e-mail e SMS nunca foram tentados.

**Opções.** 1) Exigir `message_id` (ou status real) para considerar entregue e deixar o fallback
seguir. Efeito: e-mail/SMS podem passar a sair em massa em todos os eventos sem flow, com custo de
SMS. 2) Aprovar o template `payment_link_sent` na Meta/ManyChat (resolve este evento, não os outros).
3) As duas, com a 1 restrita a eventos críticos (link de pagamento, confirmação).

**Recomendação:** 3. O turno não mexeu: o efeito em massa do fallback pede a sua palavra.

## D4 — Motivos de rejeição de pedido no Gestor (O4)

**Contexto.** O seletor já existe (presets + texto livre; códigos do provedor no marketplace). O que
falta é o que você pediu: lista configurável e "Outros" explícito. Cabe em `RuleConfig`, sem migração.

**Pergunta.** Quais motivos entram na lista inicial? Sem a lista o turno não implementa (seria
inventar taxonomia de negócio). **Recomendação:** configurável, com "Outros" sempre por último.

## D5 — Receitas: modo de fazer (O5)

**Contexto.** `Recipe.steps` é lista de strings soltas; nenhum operador vê procedimento (nem KDS,
nem ticket de pesagem). A fatia A (steps como `{name, instructions?, target_seconds?, note?}`,
sem migração) pode entrar sem você; as perguntas abaixo mudam o desenho seguinte.

**Perguntas.** (a) O operador REGISTRA a etapa feita, ou só LÊ? (b) Etapa tem tempo e temperatura?
(c) Anotação mora na versão ou na ficha? (d) O nome na tela é "Passos" ou "Etapas"?
**Recomendação:** (a) só lê, por enquanto; (b) tempo sim, temperatura opcional; (c) na versão;
(d) "Etapas" (já é o rótulo do campo).

## D6 — Anexos por papel/função nas receitas (O7)

**Contexto.** Nada existe, e o spec da DO não declara volume nem Spaces: arquivo salvo hoje some no
próximo deploy. A foto que o `/recipes/new` manda já evapora.

**Opções.** 1) DO Spaces (objeto, sobrevive a deploy, custo baixo; componente novo na conta DO).
2) Volume. 3) Por ora só "Referências externas" (links, JSON), que cobre 1/3 do pedido sem infra.
**Recomendação:** 3 agora, 1 quando decidir. (Regra da casa: nada de componente novo na DO sem
esgotar alternativas; por isso é sua.)

## D7 — Nota 0–5 com critérios nas receitas (O8)

**Contexto.** Não existe. "Favorita" por operador e reputação por versão podem entrar sem você.

**Pergunta.** Os critérios são fixos em código (P) ou tabela editável no Admin (M, molde `QualityGrade`)?
**Recomendação:** editável. Os eixos de padaria ("sabor, textura, aparência") vão mudar sem deploy.

## D8 — Backfill do nome dos contatos já gravados pelo login WhatsApp (O1)

**Contexto.** O conserto da entrada (frente O1) só vale daqui para frente. Os contatos já gravados
têm nome+sobrenome inteiros no `first_name`. A regra do primeiro token erra ("Ana Maria Silva" vira
Ana / Maria Silva).

**Opções.** 1) Não mexer no que existe. 2) Backfill com a mesma regra, só onde `last_name` está vazio.
3) Backfill com lista para revisão manual antes de aplicar.
**Recomendação:** 3. É dado de cliente.

## D9 — App instalado da loja: até onde forçar a versão nova (F5, #1301)

**Contexto.** Com o #1301 o app instalado sonda versão nova e mostra um aviso persistente, sem
botão de fechar, até o toque em "Atualizar". Ele some no checkout, no pedido e no login. Mas quem
nunca toca segue na versão velha até fechar o app: a loja nunca recarrega sozinha. A recarga
automática por ociosidade do operator-kit ficou fora de propósito, porque o cliente pode estar
digitando endereço ou pagando.

**Opções.** (a) Só o aviso, como está. (b) Aplicar a versão nova numa navegação entre telas, fora
do checkout, do pedido e do login. (c) Forçar pelo servidor (`shell.pwa_release`) um aviso que
bloqueia a tela.

**Recomendação:** (a) agora, e medir com o `app_version` (novo no relatório de erro) quantos ficam
para trás. Se incomodar, (b).

## D10 — O trilho de sugestão ("leve também") deve ir no `shell/`?

**Contexto.** Com sacola, o `shell/` (o envelope barato que toda página carrega, 3 consultas sem
sacola) monta a sacola inteira com o trilho de sugestão: depois do #1304, 56 consultas com 1 item
(eram 118). `home/` e `menu/` também montam o trilho. O `/catalog/` (a página `/menu`) não monta.

**Opções.** 1) Manter. 2) Tirar o trilho do `shell/` (o resumo da sacola fica; a sugestão vem só
onde ela aparece na tela). 3) Tirar de `shell/` e `home/`.
**Recomendação:** 2, se o front confirmar que o `shell/` não exibe a sugestão. Muda contrato com o
front, por isso é sua.

## D11 — Versão de receita publicada não se apaga mais; e as versões antigas sem "impressão digital" (#1308)

**Contexto.** Com o #1308, versão publicada ou substituída não muda nem se apaga por nenhum caminho
do ORM, nem em cascata ao apagar a receita. Hoje nenhuma tela ou API apaga receita, então nada do
dia a dia muda. Mas a regra da casa antes do go-live é "dado sintético se APAGA". Apagar uma
receita de teste com versão publicada agora exige um comando explícito, que ainda não existe. Além
disso, as versões publicadas antes do #1308 não têm a impressão digital da ficha. Para elas, o
"fora de sincronia" só compara o carimbo `version_ref` e não pega edição feita pelo Admin.

**Opções.** (a) Manter assim; criar um comando `purge_recipe_entry --apply` só quando for
preciso. (b) Carimbar retroativamente as versões antigas com a impressão digital da ficha ATUAL.
Isso certificaria fichas que já podem ter sido editadas por fora.
**Recomendação:** (a). Para as antigas, publicar de novo cada receita que importa, em vez de
carimbar.

## D12 — Conexão nova com Postgres e Redis a cada request (custo fixo de ~200 ms+)

**Contexto (medido nesta madrugada).** Sob daphne/ASGI cada request roda numa thread nova e abre
conexão nova com o Postgres (38 conexões para 38 requests na bancada) e com o Redis. A rota
`shell/` faz 4 consultas e 6–8 ms de banco, mas gasta 267–304 ms de projeção em produção (~10 ms
local). É ~60% do que sobra no `catalog/`. O turno só MEDE: o PR da frente Onda 2b põe `connect`,
`cache` e `gc` no Server-Timing. Não mexeu em conexões.

**Opções (decidir com o número do Server-Timing novo na mão).** 1) Pool de conexões do Django
(Django 5.1+, exige `psycopg[pool]`), com tamanho compatível com o PgBouncer (pool 5 hoje).
2) Ajustar `CONN_MAX_AGE` (efeito limitado sob ASGI). 3) Servir as rotas síncronas por WSGI (gunicorn).
Mais duas, levantadas pela Onda 2b (#1313): 4) um pool de conexões Redis por processo (hoje
cada request monta o seu: 7 conexões para 6 requests); 5) ajuste de coleta de lixo (`gc.freeze()`
após o boot, ou limiares maiores). Na bancada, 3 de 40 requests pagaram 100–150 ms de GC completo.
A opção 3 provavelmente é componente novo na DO (regra dos US$ 100/mês).
**Medido no ar depois do #1313 (01/10 ~04:30 UTC, por request):** `connect` 30–65 ms (sempre 1
conexão nova), `cache` 65–170 ms em 3 a 7 chamadas (**~25 ms por chamada ao Redis**: é o maior
custo fixo), `gc` em geral < 10 ms com picos de 265–325 ms. No `shell/` (7 ms de banco), connect
+ cache = ~110–150 ms dos ~150–200 ms de projeção.
A investigação da madrugada confirmou na bancada com as versões de produção: sob ASGI,
`CONN_MAX_AGE=60` não reaproveita nada; cada request abre um backend novo e o deixa `idle` até o GC.
O cache Redis segue o mesmo padrão (o `CacheHandler` é por contexto), o que explica ~25 ms por
chamada. Passo de risco baixo: `DATABASE_CONN_MAX_AGE=0` (fecha no fim do request em vez de no GC).
**Recomendação:** `CONN_MAX_AGE=0`, 4 e 5 primeiro (não mexem no PgBouncer); depois 1, com 24 h de `connect;dur`
medido e teste de carga no alpha.

## D13 — Republicar as fichas com o mesmo insumo em duas linhas (#1317)

**Contexto.** Até o #1317, fórmula com o mesmo SKU em duas linhas (ex.: água da massa + água da
bassinage) gravava na ficha os gramas errados: 650 g + 50 g viravam 100 g; com levain, zero.
O consumo de insumo das fornadas, o custo, os alérgenos e a nutrição saíram dessa ficha errada, e
o "em sincronia" não acusa nada (a assinatura foi tirada da ficha errada). O #1317 conserta daqui
para frente; o corpo dele traz um trecho só-leitura para `manage.py shell` que lista as receitas
afetadas no alpha, com a quantidade gravada e a certa. O turno não rodou contra o alpha.

**Opções.** 1) Rodar o trecho e republicar (nova versão a partir da atual) cada receita listada.
2) Deixar como está até o reseed.
**Recomendação:** 1. As fornadas já finalizadas baixaram insumo a menos no estoque; isso fica como
está (corrigir ledger é outra decisão).

## D14 — 🔴 Segurança: o `web` vivo grava access log com a URI crua (token da Efí)

**Contexto.** O `run_command` vivo do `web` é `daphne -b 0.0.0.0 -p 8000 config.asgi:application`,
sem o `--access-log=/dev/null` que o arquivo tem desde 01/09 (`15061ed3f`). O access log do daphne
grava a URI inteira, inclusive o `?token=` do webhook da Efí; os logs da DO ficam acessíveis a quem
lê o app. O verificador de drift não comparava comando; passa a comparar no #1320, e contra o vivo
essa é a ÚNICA divergência hoje. O turno não procurou token no log nem mexeu no spec.

**Opções.** 1) Aplicar o spec do arquivo (o drift mostra só esta linha, nada em SUMIRIAM):
`make deploy-spec-drift context=shopman-do-app-admin` → backup do vivo → `apps update` → conferir os
42 SECRET. 2) Editar só o comando do `web` no painel. Depois de qualquer uma: considerar rotacionar o
token do webhook da Efí, se ele já tiver aparecido no log (procurar `token=` nos logs do `web`).
**Recomendação:** 1, seguida da busca; rotacionar se achar.

## D15 — Picos de 15–40 s entre a Cloudflare e a DO (não é o app)

**Contexto (investigação só-leitura).** A origem responde a `home/` em 1–2 s, e o cliente espera
27–40 s, com corpo truncado (13 de 19 KB) e até 520/525 da Cloudflare. O processo atendia outros
requests no mesmo instante. Banco, loop do daphne e CPU foram descartados com prova. A assinatura
bate com perda de pacote ou MTU no salto Cloudflare ↔ load balancer da DO: o que cabe na janela TCP
inicial (~14 KB) passa; o que não cabe espera retransmissão. Um 525 (falha de TLS Cloudflare → DO)
foi registrado às 04:58. A noite teve 17 deployments; cada troca derruba o `web` (1 instância) por
segundos.

**Opções.** 1) Abrir chamado na DO com os horários e o cf-ray `a438d03fcc9597d0-GRU` (520, 04:44:41
UTC). Antes, um teste que separa: pares alternados de `shell/` (12 KB) e `home/` (19 KB) na mesma
janela ruim. 2) Segunda instância do `web` (custo; regra dos US$ 100/mês), que também tiraria o
blip de cada deploy. 3) Timeouts curtos de conexão no banco e no Redis (hoje não há), que viram
travamento em erro rápido sem resolver a causa.
**Recomendação:** 1 agora; 3 como higiene; 2 só com o go-live à vista.

## D16 — Sacola: que número o 409 de AJUSTE mostra, e se uma linha pode juntar hoje + fornada (#1323)

**Contexto.** O #1323 corrige o defeito (a sacola perdia a reserva ao ajustar quantidade com fila de
espera). Ficaram duas perguntas de regra, que ele não decidiu:
(a) No 409 de um ajuste, `available_qty` é o que existe ALÉM do que a sacola já reservou (2 com 2 na
sacola e fornada de 4). Mas o botão "Usar N unidades disponíveis" envia N como quantidade TOTAL da
linha, então oferece "Usar 2", que não muda nada, quando caberiam 4. Erra para menos (não promete o
que não existe), mas rótulo e ação discordam.
(b) Com 2 prontos hoje já na sacola e 4 na fornada de amanhã, pedir 4 dá 409: a linha de
pronta-entrega só cresce dentro de hoje. A alternativa é a linha virar "2 hoje + 2 amanhã" (promessa
nova: que dia a sacola mostra? a parte de hoje espera a de amanhã?).

**Opções.** (a) 1) O 409 do ajuste passa a dizer o total que a linha pode ter (reservado + livre),
alinhado ao botão. 2) Manter e mudar o botão para somar. (b) 1) Manter uma linha = uma data. 2) Dividir.
**Recomendação:** (a) 1. (b) 1, por ora; dividir é desenho de UX, não conserto.
