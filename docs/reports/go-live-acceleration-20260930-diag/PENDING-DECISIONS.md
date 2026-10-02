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

## Atualização de 01/10 (tarde): decidido pelo dono e executado

| # | Estado |
|---|---|
| D3 | ✅ Recibo de envio crítico (#1339). Perguntas restantes em D27 |
| D6 | ✅ R2 pronto e desligado (#1337). O que falta é do dono: D30 |
| D9 | ✅ Versão nova forçada, nunca no pagamento (#1341) |
| D10 | Não removido: a `/sacola` exibe o trilho vindo do `shell/`. Pergunta em D31 |
| D11 | ✅ Versão livre (#1338). Perguntas restantes em D26 |
| D19, D20, D24 | ✅ (#1338) |
| D21 | ✅ Aplicado no spec vivo, arquivos no #1334 |
| D16(b), D17, D18 | Viraram o mapa WP-DATA-E-PROMESSA (#1335). Perguntas em D25 |

## Atualização de 01/10 (noite): decidido pelo dono

| # | Estado |
|---|---|
| D28 | ✅ Decidido: proposta de corte **recusada**. Ficam fora do go-live só Marketing e B.I.; entra todo o resto, com entrega por parceiro (TaOn/Machine) e Concierge nomeados. Registro: D-017 em `docs/coordination/DECISIONS.md`; custo de cada frente em `docs/plans/GO-LIVE-SCOPE-CUT-PROPOSTA.md` |
| D32 | Nova: a proposta de triagem do Concierge, abaixo |

## Atualização de 02/10: decidido pelo dono e executado

| # | Estado |
|---|---|
| D32 | ✅ Decidido: "aprovo a triagem" (opção 1, triagem completa). Implementada no #1347. Registro: D-018 em `docs/coordination/DECISIONS.md`; mapeamento e sequência para ligar em `docs/plans/WHATSAPP-CONCIERGE-PLAN.md` |

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


## D25 — Data e promessa: as perguntas do mapa (destrava a Frente 5)

**Contexto.** O mapa `docs/plans/WP-DATA-E-PROMESSA.md` (#1335) confirma "uma data alvo por pedido"
com ressalva: a data também mora na reserva (`Hold.target_date`), e nada obriga as duas a
concordarem (sacola montada na fornada de amanhã, "Hoje" escolhido no checkout).
**Perguntas.** As P1 a P9 estão na seção 7 do mapa, cada uma com opções e recomendação. **P1, P2 e
P3 destravam o conserto da loja** (passar a data da sacola para a resolução no `add_item`).
**Recomendação:** P1 sim (uma data nos quatro canais), P2 vale a data da sacola, P3 sim.

## D26 — Receita: editar a versão publicada direto no app?

**Contexto.** Com o D11 o banco e o Admin deixam editar e apagar versão publicada (#1338). O
serviço do app (`update_draft`, regra anterior ao #1308) ainda edita só rascunho: no app, mudar uma
versão publicada continua sendo criar versão nova.
**Opções.** 1) Manter (o app cria versão nova; o Admin edita direto). 2) Liberar edição direta da
publicada no app. E: os comandos `rewrite_recipe_per_unit` e `convert_material_base_unit` ainda
dizem "versão publicada é história" (escolha deles de não reescrever versões): trocar?
**Recomendação:** 1, e manter a frase dos comandos (descreve o que eles fazem).

## D27 — Recibo de envio: mais eventos críticos, e o alerta frequente

**Contexto.** Críticos hoje: `payment_link_sent` e `order_accepted` (#1339). ManyChat e Comtele não
devolvem identificador; só o e-mail comprova. Cliente sem e-mail recebe WhatsApp + SMS e, mesmo
assim, o operador recebe alerta de "sem comprovante" em todo link de pagamento.
**Perguntas.** (a) Entram `payment_requested` (cobrança Pix), `order_received`,
`order_rejected`/`order_cancelled`, `waitlist_available`? (b) O alerta em todo link sem e-mail é
aceitável, ou o e-mail passa a ser pedido na venda por link? (c) Mensagem em dobro (WhatsApp + SMS,
ou WhatsApp + e-mail) é o custo aceito?
**Recomendação:** (a) só `payment_requested`; (b) aceitar o alerta por uma semana e medir; (c) sim.

## D28 — Corte de escopo do go-live

**Contexto.** `docs/plans/PRODUCT-V1-SCOPE-BACKLOG.md:77` exige as 11 frentes e se auto-bloqueia.
A proposta (`docs/plans/GO-LIVE-SCOPE-CUT-PROPOSTA.md`, #1336) deixa DENTRO Gestor, loja com
retirada e PDV (8 a 11 já entregues) e FORA entrega própria, WhatsApp conversacional, catálogos
externos e media persistente, com o custo de cada corte e o texto novo da linha 77.
**Pergunta.** Aprova o corte como está? **Recomendação:** sim; ele não tira nada que o balcão use.
**✅ Decidido pelo dono (01/10/2026, noite): RECUSADO.** Ficam fora só Marketing e B.I.; entra todo
o resto, explicitamente a entrega por parceiro (TaOn/Machine) e o Concierge ("a equipe está defasada e a
triagem das mensagens será muito útil"). Registro: D-017; o arquivo da proposta virou a decisão, com o
custo e a dependência externa de cada frente que voltou.

## D29 — Ensaio de restauração: token ou painel

**Contexto.** Backup e PITR estão verificados, mas o ensaio pelo fork deu `403` (o contexto
`shopman-do-app-admin` não tem `database:create`). O ensaio lógico (pg_dump direto → Postgres local)
passou: 104 s + 23 s, contagens batem, 0 migração pendente. Ele não substitui o fork.
**Opções.** 1) Gerar token com `database:create`, `database:read`, `database:view_credentials`,
`database:delete`, `regions:read`, `sizes:read`, `actions:read` e o agente faz o ensaio inteiro
(~40 a 60 min, cluster descartado no mesmo dia). 2) Você faz pelo painel, com o runbook.
**Recomendação:** 1 (fica cronometrado e com evidência).

## D30 — R2: o que só você faz

**Contexto.** O código está pronto e desligado (#1337, D-010). Passo a passo em
`docs/runbooks/r2-passo-a-passo-do-dono.md`: criar o bucket privado, criar o token R2 com leitura e
escrita só naquele bucket, colar `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID` e
`R2_SECRET_ACCESS_KEY` como segredo no painel da DO. Segredo nunca vai por chat.
**Pergunta.** Depois disso, liga `SHOPMAN_MEDIA_STORAGE=r2` no alpha? **Recomendação:** sim.

## D31 — Trilho de sugestão no `shell/`: aceitar que ele "pule" na sacola?

**Contexto.** A sugestão da sacola (`cart.upsell`) vem no `shell/`, e a `/sacola` a mostra na primeira
pintura (`surfaces/storefront-nuxt/app/app.vue:32`, `pages/sacola.vue:302`); a sacola própria só
responde depois. Nenhuma outra tela exibe esse trilho (#1341, tabela tela a tela).
**Opções.** 1) Manter (o `shell/` segue montando a sacola inteira, ~56 consultas com 1 item). 2) Tirar
do `shell/`: a `/sacola` abre sem o trilho e ele aparece um instante depois.
**Recomendação:** 1 até o go-live (omotenashi); 2 se o custo do `shell/` voltar a doer.

## D32. Concierge: a proposta de triagem

> ✅ **Decidida em 02/10/2026** pelo dono: *"aprovo a triagem"* (opção 1). Implementada no #1347;
> registro D-018. As perguntas abaixo ficaram respondidas pela proposta aprovada: as 12 intenções
> bastam; o resumo vai no sino do Gestor de pedidos; vaga, parceria e fornecedor vão para a outra
> mesa no Admin; a observação passiva acaba quando o modo passa a `assist`. Fora do expediente o
> que escala espera a equipe (nada toca ninguém): não estava na proposta e segue o comportamento de
> hoje.

**Contexto.** O Concierge entrou no go-live (D-017) e a razão do dono é a triagem. Ela não existe no
código: hoje uma regex com quatro causas decide só o handoff (`shopman/storefront/concierge/handoff.py:16-49`),
o modelo não consegue escalar (sem ferramenta de handoff, `tools.py:1948-1960`), o alerta ao operador não
tem resumo (`service.py:1302-1307`) e só aparece no Gestor se a conversa tiver pedido
(`shopman/backstage/services/alerts.py:69-70`). Já existem as 12 intenções combinadas com o dono em 23/09
(`intent_pilot.py:58-91`) e o campo `Conversation.summary`, que nada escreve. Proposta completa em
`docs/plans/WHATSAPP-CONCIERGE-PLAN.md`, seção "Triagem: PROPOSTA para o dono corrigir".
**Opções.** 1) Triagem completa: toda mensagem ganha intenção (das 12) e urgência; o simples é respondido;
`human`, `complaint`, `allergy`, `order` que o chat não fecha e `special_order` escalam com resumo de uma ou
duas linhas no sino do Gestor; `job`, `partnership`, `supplier_offer` vão para uma fila de "outra mesa" no
Admin. 2) Triagem mínima: manter a regex de quatro causas e só acrescentar o resumo no alerta e o alerta no
sino do Gestor. 3) Só escalar tudo para a equipe, sem resposta automática (Concierge vira recepcionista).
**Perguntas.** As 12 intenções bastam? Quem é "atendimento" na casa hoje? O resumo vai no sino do Gestor ou
num app próprio? Fora do expediente, o que escala espera a manhã ou toca alguém? E a observação passiva
(`CONCIERGE_OPERATION_MODE=observe`) acaba quando o Concierge passa a responder: aceita?
**Recomendação:** 1, porque é o que o dono descreveu ("já classificado e resumido") e reaproveita o
vocabulário que ele já aprovou; 2 só se o prazo do go-live apertar.

## D33. Textos de quatro modelos que o ManyChat recusa por formato

> ✅ **DECIDIDA em 02/10/2026** (D-023): o dono aprovou as três propostas abaixo como estão.

**Contexto.** Ao enviar os modelos revisados em 25/09, o ManyChat recusou dois antes de chegarem à
Meta (01/10, tela "Criar modelo"): `pedido_em_preparo` ("Minimum of 7 words required for 2 variable
parameter"; o corpo tem 4 palavras fixas) e `pagamento_falhou` ("Template body cannot start or end
with a variable"; o ponto final depois de `{{2}}` não conta como texto). `pontos_fidelidade` termina
igual e vai cair na mesma regra. O dono aprovou em 01/10 "textos ok" para as sugestões da sessão; a
sessão encontrou depois uma repetição na do `pedido_em_preparo` (o `status_note` já termina em
"avisamos assim que estiver pronto") e propõe a versão abaixo.
**Proposta (corpo WhatsApp; SMS e e-mail não mudam):**
- `pedido_em_preparo`: `Estamos preparando seu pedido {{1}} com todo carinho. {{2}}. Qualquer dúvida, estamos à disposição.`
- `pagamento_falhou`: `Oi, {{1}}. Não conseguimos gerar o pagamento do seu pedido {{2}}. Qualquer dúvida, estamos à disposição.`
- `pontos_fidelidade`: `Parabéns, {{1}}! 💛✨ Você ganhou pontos de fidelidade com o pedido {{2}}. Obrigada por nos prestigiar!`
**Recomendação:** aprovar as três; a sessão envia em seguida. `reembolso_processado` não tem defeito,
só não foi enviado nesta rodada (a aba do ManyChat em segundo plano não aceita digitação).

## D34. Opções de produto (chá, sabor, predefinidos)

**Contexto.** Não existe opção de produto. `shopman/shop/modifiers.py` é modificador de PEDIDO
(desconto, taxa). Hoje cada sabor é um SKU próprio: os chás da casa são cinco produtos de
R$ 14,00 a R$ 18,00 (`CHCAM`, `CHROU`, `CHSOP`, `CHBLU`, `CHHIB`, medido no alpha em 01/10;
`seed.py:1874-1880`). O caso contrário também existe: o `FRAP` (Frappé) é um SKU só, e o sabor
("café, chocolate ou frutas vermelhas") mora na descrição, sem jeito de o cliente escolher.
Mexer em opção toca preço (`Product.base_price_q`), estoque por SKU, fiscal (`metadata['fiscal']`),
projeção do catálogo e o PDV (`usePosSale.ts`, `pushProduct`).
**Opções.**
1) **Agrupar os SKUs que já existem** (a mais barata). Um campo de agrupamento no dado do produto
   (ex.: `metadata.group`), e o cardápio e o PDV mostram um cartão "Chás da casa" que abre a
   escolha entre os cinco. Cada escolha continua sendo o SKU de hoje: preço, estoque, ficha, nota
   fiscal e KDS não mudam. Custo: 2 a 3 dias (projeção do catálogo, um componente no storefront e
   no PDV). Risco baixo. Não resolve o Frappé (sabor sem SKU).
2) **Escolha predefinida sem preço** ("escolha obrigatória" no produto: lista fechada de textos,
   ex. café/chocolate/frutas vermelhas). A escolha viaja como observação da linha
   (`meta["notes"]`, o caminho que o PDV já usa e que a loja ganha nesta rodada) e chega ao KDS.
   Preço, estoque e fiscal não mudam porque o SKU é um só. Custo: 3 a 4 dias. Risco médio: a
   receita (ficha) não sabe qual sabor saiu, então o consumo de insumo fica pela média.
3) **Variante de verdade no Core** (produto pai e filhos com preço, estoque e ficha próprios).
   Custo: semanas; mexe no `offerman`, no ledger, na nota e em todas as superfícies. Risco alto
   antes do go-live.
**Resposta à pergunta "só agrupar resolve o chá?":** sim. Os chás já são SKUs separados com preço,
ficha e nota próprios; o que falta é a apresentação (cinco cartões quase iguais viram um). Não
resolve o Frappé, que é o caso da opção 2.
**Recomendação:** 1 agora para o chá (barata e sem risco); 2 depois do go-live para os
predefinidos sem preço; 3 só se aparecer opção que muda preço ou estoque e não cabe como SKU.

## D35. Threads

**Contexto.** Não existe publicador de Threads. O token da Meta que o Marketing usa é de Página,
com permissões de Facebook e Instagram (`config/settings.py:849-851`), e não publica no Threads. O
Threads exige um app próprio na Meta, autorização própria (`threads_basic` e
`threads_content_publish`) e revisão da Meta. O código é pequeno porque há molde
(`marketing_delivery_*`); o processo (app, revisão, conta) é a frente.
**Resposta ao dono, em três linhas:** hoje o sistema não publica no Threads, e o acesso que já
temos da Meta não serve para ele. Para ligar, é preciso criar um app do Threads na Meta e passar
pela revisão deles (dias a semanas, fora do nosso controle). Depois disso, o código é de um a dois
dias, porque o Instagram e o Facebook já servem de molde.
**Opções.** 1) Seguir: a sessão prepara o pedido de revisão no painel da Meta (no Chrome do dono) e
o código em paralelo, desligado. 2) Não agora: fica para depois do go-live (Marketing já está fora
do escopo do go-live, D-017).
**Recomendação:** 2, pelo D-017; abrir a revisão da Meta cedo só se o dono quiser o Threads logo
depois do go-live, porque a espera é deles.

## D36. Jev no comparador de intenções do Concierge

**Contexto.** A premissa "o ManyChat classifica" não vale: o ManyChat manda cinco campos sem
intenção (`transport.py:319-415`); quem identifica é o nosso código, antes do modelo de resposta
(`service.py:897-916`), com as 12 intenções de `intent_pilot.DEFAULT_INTENTS` e a regra local
sempre ligada (`handoff.py`, `triage.py`). O Jev (TypeSafe) existe só no comparador
(`intent_benchmark.py`, `INTENT-PILOT-PLAN.md`), e está FORA da lista aprovada
(`SHOPMAN_INTENT_PILOT_PROVIDERS_APPROVED`, `settings.py:1408-1417`).
**O que sai da casa com o Jev (decisão do dono):** o texto das mensagens dos clientes, já redigido
(sem CPF, cartão, contato, endereço e detalhe de saúde), vai para um fornecedor novo, cujos termos
de guarda e de uso para treino não foram avaliados.
**Por que o placar não rodou (medido no alpha, 01/10):** três travas, e nenhuma é código.
1) **Gabarito vazio:** 147 mensagens com intenção *sugerida* e **zero conferidas**; o placar
   precisa de 30 conferidas (Admin, Clientes, Mensagens para rotular). Sem conferência não há
   contra o que medir, nem para o Jev nem para os outros.
2) **Sem chave:** não há `JEV_API_KEY` no spec nem em arquivo local (o cadastro do Jev estava
   pausado em 23/09).
3) **Sem aprovação:** `typesafe` fora da lista aprovada.
**Opções.** 1) Aprovar o envio ao Jev, conseguir a chave, conferir 30 mensagens; a sessão roda o
placar com regex, embeddings, Haiku e Jev. 2) Medir sem o Jev: conferir as 30 e rodar o placar
só com o que já é aprovado (nada sai para fornecedor novo). 3) Encerrar o piloto do Jev.
**Recomendação:** 2. A conferência é pré-requisito de qualquer placar, e o critério de empate do
plano já prefere o que não sai da casa; o Jev entra depois, se os aprovados não baterem 95% nas
intenções sensíveis.
**Armadilhas:** há dois `adr-026` (o do Concierge, "Proposto", e o de superfície de operador,
"Aceito"). Sem `event_id` verificado o turno do ManyChat é somente leitura; e "escalar" só cala o
robô se o flow do ManyChat tiver o campo `concierge_handoff` ligado, o que se faz no ManyChat.

## D37. Padronização dos controles de data: por onde começar

**Contexto (inventário de 01/10):** 11 controles de data distintos no operador, nenhum
compartilhado, mais um no storefront. PDV: `preorders/index.vue:307`, `PosScheduleModal.vue:122`,
`PosPreorderRescheduleDialog.vue:117`. Produção: `board.vue:154`, `expedite.vue:524`,
`ProductionStageGrid.vue:626`, `reports.vue:345,355`. B.I.: `BiTopBar.vue:114,122`,
`forecast.vue:73`. Marketing: `CampaignForm.vue:1045,1059`. Compras: `ReceiptLineSheet.vue:251`.
O `operator-kit` não tem primitiva de data (o filtro só tem single, multi e boolean). Nesta rodada
não se cria primitiva.
**Recomendação: começar pelos três do PDV de Encomendas** (navegador do período, agendar,
reagendar). São o mesmo gesto ("escolher o dia da encomenda"), no mesmo app, usados pelo balcão
todo dia e com o cliente na frente; um defeito ali vira encomenda no dia errado. Com eles a
primitiva nasce com três consumidores reais (a regra da casa para criar abstração). Depois a
Produção (quatro, mesmo gesto de "dia de trabalho"); B.I. e Marketing por último, que são intervalo
de datas e estão fora do go-live (D-017).
**[INFERÊNCIA]** que os três do PDV divergem entre si no comportamento: o inventário mediu que são
distintos no código, não comparou o que cada um faz.
