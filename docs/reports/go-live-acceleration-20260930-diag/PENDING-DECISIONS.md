# PENDING-DECISIONS — turno autônomo 30/09 → 01/10/2026

> Decisões que só o dono toma. Cada uma: contexto em 3 linhas, opções, recomendação.
> Nenhuma foi decidida durante a noite; o trabalho seguiu por outras frentes.


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
