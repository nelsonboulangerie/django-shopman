# WP-08-agente-c — Marketing

**Status:** pronto para implementação · **Autor:** Agente C (terceira leitura, 2026-08-29)
**Superfície:** `surfaces/marketing-nuxt` + `shopman/backstage/api/marketing.py` + `shopman/shop/handlers/campaign.py` + `audience.py`
**Objetivo:** o gestor sabe quantas pessoas vão receber, quando vão receber, e que receberam — e nada do que sai carrega a chave de entrar na conta do cliente.

## Diferenças vs. WP-08 (Agente G) e WP-08-agente-d

**Confirmado, e pior do que os dois descreveram:** "publicar agora" pode agendar — e `publish_now` **não tem
produtor nenhum no repositório**, nem no front nem em teste. O toast mente nos **dois** sentidos: agendar no
passado publica na hora dizendo "agendado".

**Refutados:**
- **"O tipo TS omite regras avançadas" (D).** O tipo **já declara** tags, RFM, faixas, churn e aniversário. A
  perda está no `submit()` do formulário — arquivo diferente. O achado é real; a evidência estava errada.
- **"Preview e payload por plataforma divergem" (G).** O conteúdo por plataforma é escrito e **nenhum
  consumidor o lê**.
- **"Filtro que falha vira 'todo mundo'"** (hipótese do briefing, que eu procurei especificamente).
  **Não existe:** o resolvedor parte de conjunto vazio e falha fechado em toda fonte, inclusive consentimento.
  Registro pelo valor do negativo — é a falha mais temida desta superfície e ela não está aqui.

**Recalibrados para baixo:**
- **Divergência de ondas → não é P1.** Ela nunca erra **quem** recebe; erra a estrutura e o atraso das ondas,
  porque as chaves conhecidas sempre cobrem todos. (Com uma exceção grave, que é o P1-3 abaixo.)
- **Permissão única → P2, não P1.** `manage_campaigns` está **só no grupo Gerente**; Caixa e Cozinha não a
  têm. O cenário "qualquer operador dispara para a base" não existe. O que existe é ausência de segregação de
  funções **dentro** de uma persona de gestão — numa padaria com um ou dois gerentes, isso é higiene. E a
  separação tem custo escondido: o fallback de revisores casa por codename e quebraria.

**Aceite descartado (D estava certo ao apontar, e vou além):** *"o número planejado bate com a audiência
confirmada"* exige **congelar** a audiência — decisão de produto não tomada, já que o código re-resolve na
hora do envio **de propósito** (favoritos e alertas mudam). Fora do aceite.

**Novos:** o token de login do cliente vaza para o ManyChat; a onda de hora habitual é entregue a ninguém e
reportada como enviada; `int()` sem guarda em três chaves de audiência; PII de destinatário em log.

## Estado real do disparo

O único canal com blast real é WhatsApp via ManyChat, e ele acende com `MANYCHAT_API_TOKEN`. **Sem token,
falha fechada** — zero enviados, N falharam. Não dá para confirmar o estado do alpha lendo código; é a
pergunta 1.

## Pré-requisitos

📎 O item 14 do inventário `docs/plans/fallbacks-perigosos-go-live.md` (PR #393) —
*`notifications.get_backend(None)` resolve para o console* — mora no **mesmo arquivo** do P2-4 deste WP (PII
de destinatário em log). Se os dois forem feitos, que seja no mesmo PR.


- **WP-00 Bloco C**: `marketing-nuxt` é um dos dois apps **sem contrato TS gerado** — e não é coincidência que
  os achados de divergência FE↔BE se concentrem aqui. O exportador de schema fecha essa classe por construção.
- **WP-00 Bloco B**: o P2-1 consome o parser de lá.

## Achados priorizados

### P1-1 — O token de login do cliente é gravado no perfil dele no ManyChat

Nenhum dos dois viu, e é o achado mais sério desta superfície.

**Mecanismo, do clique ao efeito.**

1. O gestor aprova um anúncio com WhatsApp entre as plataformas.
2. O despacho cunha, **por destinatário**, um link de acesso pessoal e o coloca em `action_url`. O token vale
   até 24 h e cria sessão de cliente identificado por número.
3. O contexto é repassado intacto ao adapter.
4. Havendo flow configurado — que é exatamente a configuração que o app oferece na tela de template —, o
   adapter grava **todo scalar não-denylistado** como campo personalizado do assinante.
5. **`action_url` não está na denylist.** O token de login do cliente passa a viver, em texto claro, no perfil
   dele dentro de uma ferramenta SaaS de marketing — legível por qualquer pessoa com acesso à conta ManyChat, e
   utilizável enquanto o cliente não clicar (o link é de uso único).

**Fix — uma linha:** acrescentar `action_url` à denylist. Um flow que precise do link deve receber o link
**comum**, não o pessoal; se o botão do template precisar do pessoal, ele tem de vir pelo token de flow, que
já é enviado, e não como campo persistido no perfil.

### P1-2 — "Publicar agora" agenda, "agendar no passado" publica, e o toast mente nos dois casos

**Mecanismo.** Uma campanha com agenda de horas preferidas (configurável só pelo Admin) faz o anúncio nascer
com data de publicação na próxima janela. O gestor clica **"Publicar agora"** — e o card emite as edições
**sem `publish_now`**. A aprovação respeita a agenda, reintroduz a data e **não despacha**. A tela olha o
corpo enviado, não a resposta, e mostra **"Anúncio publicado."** O gestor sai da tela achando que publicou.

O espelho: no botão **"Agendar"**, uma data no passado passa pela validação (que só confere formato), e
**dispara imediatamente** — com o toast dizendo "Anúncio agendado."

**Fix mínimo:** o card emite `publish_now: true`; a tela decide o texto pelo `scheduled` **da resposta**, nunca
pelo corpo enviado; e a validação recusa data no passado com erro de campo.

### P1-3 — A onda de hora habitual é planejada, despachada, entregue a ninguém, e reportada como enviada

**Mecanismo.** As ondas são produzidas com chave `nome@hora` para quem tem hora preferida e a regra tem
janela. Uma diretiva é criada por onda, com essa chave. Mas o handler resolve os destinatários por um
**dicionário fixo de três chaves** — `vip`, `general`, `all` — e `general@14` cai no default vazio. Zero
destinatários; a onda é gravada com "0 enviados, 0 falharam"; e como *"onda vazia não é falha"*, o status
vira **`sent`**. O anúncio fecha como publicado. **Ninguém daquela onda recebeu, e nada indica isso.**

A função que resolveria — `select_wave` — **existe**, está descrita no docstring do despacho como se fosse o
contrato em uso, e **não tem um único chamador no repositório**. É código morto que a documentação afirma
estar em uso.

**Fix — uma linha:** trocar o dicionário pelo `select_wave`.

Latente hoje (nenhuma UI escreve a janela de hora preferida — só o Admin, e a chave é oferecida no `help_text`
do próprio model). Mas latente com o mecanismo pronto, e o modo de falha é o pior possível: relatório de
entrega mentindo.

### P1-4 — Test-send é um canhão de texto livre para número livre

**Mecanismo.** Um POST no endpoint de teste com qualquer número e qualquer texto: o servidor só faz `str()`
dos campos e recusa apenas vazio e lista. Nenhuma validação de formato, nenhum vínculo com o operador, nenhum
consentimento, nenhum limite de taxa. O texto vira a mensagem e sai pelo transporte real.

**Efeito colateral que ninguém viu:** havendo flow configurado, o adapter **grava o contexto do teste como
campos personalizados do assinante**. Testar contra o número de um cliente real sobrescreve nome, produto e
link no perfil dele — e a próxima mensagem legítima renderiza com os valores do teste.

**Fix mínimo:** remover `body` do contrato — a UI já não o manda, é dívida sem consumidor; e limite de taxa
por usuário, no mesmo padrão que o login de operador já usa. O vínculo destino↔dono que o Agente D propõe é
bem-vindo, mas depende de dado que não existe (o usuário do operador não tem telefone declarado) — **não
colocar no aceite**.

### P1-5 — O formulário apaga dez chaves de audiência ao salvar

O gestor abre "Editar" numa campanha configurada no Admin com tags, segmento RFM e `match: "all"`, muda só o
nome e salva. O `submit()` monta as regras **do zero** com quatro chaves, e o PATCH sobrescreve o JSON
inteiro. Perdem-se dez chaves.

E a direção importa: com favoritos, alertas e histórico de compra ligados, **perder `match: "all"` troca
interseção por união** — **mais gente do que o gestor pediu**, sem aviso.

**Fix — uma linha, e é a certa:** preservar o que não se edita, espalhando as regras existentes antes das
quatro que o formulário governa, e apagando explicitamente as opcionais quando desligadas. O aviso na tela
("esta campanha tem regras que este formulário não edita") é UX desejável, não pré-requisito.

⚠️ Esta classe inteira de bug é o que o **WP-00 Bloco C** fecha por construção.

### P2-1 — Regra de audiência mal formada devolve 500 e mata a campanha em silêncio

`int()` sem guarda em três chaves, e o serializador aceita qualquer dict como regras, sem validar tipos.
Consequência dupla: 500 na contagem e no disparo, e campanha silenciosamente morta na avaliação.

**Fix:** parser do WP-00 Bloco B, com erro de campo.

### P2-2 — Dois cliques em "Disparar agora" mandam duas vezes

O disparo cria o anúncio com chave de ocorrência vazia, e o índice único parcial só cobre chave não vazia.
Duas requisições produzem dois anúncios, dois conjuntos de diretivas com chaves de dedupe distintas, e **duas
mensagens por pessoa**. A única barreira é o botão desabilitado no cliente, que não sobrevive a um retry de
rede, a duas abas ou a um `curl`.

**Fix:** aceitar `Idempotency-Key` e usá-lo como chave de ocorrência — o índice único do banco já resolve o
resto. **Não precisa de tabela nova.** Ver WP-00 Bloco A: esta é a mesma máquina do PDV, aplicada aqui.

### P2-3 — Uma permissão para editar, aprovar, disparar e testar

Recalibrado para P2 (ver acima). **Se for feito:** separar **apenas** `fire` e o envio de teste — as duas
ações irreversíveis —, manter o resto sob a permissão atual, e ajustar o fallback de revisores para o codename
de leitura.

### P2-4 — PII de destinatário em log de produção

O log de notificação registra o destinatário truncado em 20 caracteres — e um telefone brasileiro em E.164 tem
13, então cabe inteiro. O mesmo no teste. Não é vazamento externo, mas é telefone de cliente em log agregado.

**Fix:** mascarar na origem. ⚠️ O arquivo de notificações é do `shop` e serve todos os canais transacionais: o
fix vale, mas o arquivo não é deste WP.

### P2-5 — `approve` não revalida a audiência

Mantido dos dois. Fica claro o que **não** é aceite: fazer o número "bater" exige congelar a audiência, e o
código re-resolve na hora **de propósito**.

## RBAC / `setup_groups`

**Nenhuma mudança**, a menos que a pergunta 3 peça a separação do P2-3 — e aí vai no **PR único de permissões
da onda 4** (WP-00 Bloco D3), com atenção ao fallback de revisores, que casa por codename.

## Testes

1. Nenhum campo persistido no ManyChat contém `action_url` (assert-negativo sobre o payload de campos).
2. "Publicar agora" numa campanha com agenda de horas despacha na hora; o toast reflete o `scheduled` **da
   resposta**.
3. Data de publicação no passado devolve 400 com `field: publish_at`.
4. Onda `general@14` entrega aos destinatários daquela hora; onda que não resolve destinatário **não** é
   reportada como enviada.
5. Editar só o nome de uma campanha com tags, RFM e `match:"all"` **preserva** as dez chaves.
6. Test-send sem `body` funciona; com `body` é recusado; o sexto teste no mesmo minuto é bloqueado.
7. Dois disparos com o mesmo `Idempotency-Key` produzem **um** anúncio.
8. `bought_within_days: "muitos"` devolve 400 com `field`, nunca 500.
9. Nenhum log de notificação contém telefone completo.
10. **Guarda de regressão do que já está certo:** filtro de audiência que falha resolve para conjunto
    **vazio**, nunca para "todos".

## Arquivos tocados (para a matriz de colisão)

| Arquivo | Risco | Observação |
|---|---|---|
| `shopman/shop/adapters/notification_manychat.py` | MÉDIO | P1-1 — arquivo compartilhado com notificação transacional |
| `shopman/shop/handlers/campaign.py` | BAIXO | P1-3 |
| `shopman/shop/notifications.py` | **MÉDIO** | P2-4 — do `shop`, serve todos os canais. **Não é deste WP**; coordenar |
| `shopman/backstage/api/marketing.py` | BAIXO | P1-2, P1-4, P2-1 |
| `shopman/shop/services/audience.py` | BAIXO | P2-1 |
| `surfaces/marketing-nuxt/**` | BAIXO | P1-2, P1-5 |
| `shopman/shop/management/commands/setup_groups.py` | **ALTO** | só se a pergunta 3 pedir → **onda 4** |

## Fora de escopo

Congelar a audiência no momento da aprovação (decisão de produto não tomada). Vínculo destino↔dono no
test-send (dado inexistente). Conteúdo por plataforma (nenhum consumidor). Mudanças no adapter de notificação
transacional além da denylist.

## Perguntas para o dono do produto

1. **O disparo real está ligado no alpha?** O único canal com blast é o WhatsApp via ManyChat, e ele depende do
   token estar configurado. Sem token, falha fechada. **A resposta muda a gravidade de metade deste WP** — e
   não dá para descobrir lendo código.
2. **O link pessoal de acesso pode ir em campanha de marketing?** Ele existe para o cliente entrar com um
   clique, o que é bom. Mas hoje ele acaba **persistido no perfil do assinante dentro do ManyChat**. Quero
   tirá-lo de lá (P1-1) — mas se o flow depende dele, precisamos de outro caminho, e isso é decisão sua.
3. **Disparar e testar devem exigir permissão além de editar campanha?** Hoje é uma permissão só, e ela está
   só com o Gerente. Numa padaria com um ou dois gerentes, separar pode ser cerimônia sem ganho.

## Prompt para agente executor

~~~text
Execute WP-08-agente-c (Marketing).

Pre-requisito forte: WP-00 Bloco C (export_marketing_schema). Este app NAO tem contrato
TS gerado, e e por isso que os bugs de divergencia FE<->BE se concentram aqui. Gerar o
contrato fecha a classe do P1-5 por construcao.

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-08-agente-c-marketing.md
- docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-00-agente-c-transversal.md (Blocos A, B, C)
- shopman/shop/adapters/notification_manychat.py:253, 282-315  ← o P1-1 mora aqui
- shopman/shop/handlers/campaign.py:297-301, 397-401, 509
- shopman/shop/services/audience.py:172, 242, 285-292, 339-350 (select_wave — codigo MORTO)
- shopman/backstage/api/marketing.py:172, 200-215, 635-640, 735-751
- surfaces/marketing-nuxt/app/components/{AnnouncementCard,CampaignForm}.vue
- surfaces/marketing-nuxt/app/composables/useCampaignBoard.ts:36

Fases:
1. P1-1: uma linha na denylist. Teste 1 (assert-negativo). Faca primeiro — e o unico
   achado desta superficie que expoe conta de cliente.
2. P1-3: uma linha — trocar o dicionario fixo por select_wave. Teste 4.
3. P1-2: publish_now no card + toast pela RESPOSTA + recusar passado. Testes 2 e 3.
4. P1-4: tirar body do contrato + rate limit. Teste 6.
5. P1-5: preservar as regras existentes no submit. Teste 5.
6. P2-1 (parser do WP-00), P2-2 (Idempotency-Key como occurrence_key), P2-4 (mascarar log).
7. Teste 10 — guarda de regressao: filtro que falha resolve para VAZIO, nunca "todos".
   Isso ja esta certo hoje; o teste existe para nao regredir.

NAO congele a audiencia (decisao de produto nao tomada). NAO exija vinculo destino<->dono
no test-send (o dado nao existe). NAO mexa em shop/notifications.py sem coordenar — serve
todos os canais transacionais.
~~~
