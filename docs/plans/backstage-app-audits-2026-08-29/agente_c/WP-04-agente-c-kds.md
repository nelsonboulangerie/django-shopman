# WP-04-agente-c — KDS

**Status:** pronto para implementação · **Autor:** Agente C (terceira leitura, 2026-08-29)
**Superfície:** `surfaces/kds-nuxt` + `shopman/backstage/{api,projections,services,admin}/kds*`
**Objetivo:** o item que o cozinheiro marca é o item que fica marcado; a estação errada não apaga a certa; e o painel do salão não publica o telefone do cliente.

## Diferenças vs. WP-04 (Agente G) e WP-04-agente-d

Esta é a rodada com mais **rebaixamentos** — e é o principal serviço que ela presta. Os dois achados que o
Agente D promoveu a P0 foram medidos e não sustentam P0; ao mesmo tempo, dois achados que ninguém viu são P1
de verdade. Toda medição abaixo foi executada contra o HEAD de hoje.

**Rebaixados, com medição:**
- **`bool("false")` → P2, não P0.** O bug é real (medido: form-encoded e JSON string viram `True`), mas
  **nenhum caminho da superfície produz uma string** — a UI manda `!item.checked`, boolean real. E o efeito é
  assimétrico: o backstage compara com o estado atual, então um `"false"` espúrio só marca um item que estava
  desmarcado, nunca desmarca um marcado. Um bug que nenhum cliente do sistema alcança não é P0.
- **SSE vazando `session_key`/`order_ref` → P2, não P0.** Confirmado. Mas quem lê o canal já pode ler o board
  inteiro **com nome do cliente** por REST, e o grupo Cozinha **não tem `cashman.operate_pos`** — o único gate
  que aceita `session_key` como entrada. É uma chave que o portador não consegue usar. O que legitima o
  achado é a regra (ADR-016: "payload mínimo"), não o dano.
- **Índice mutável → P2, não P1.** O deslocamento é real e o fluxo é real (o "Cancelar envio" do PDV), mas
  `unfire_session_lines` é o **único** mutador de comprimento, e a janela é sub-segundo.
- **Estação não vinculada → P2, não P1.** Não é escalada de privilégio: quem faz isso já pode operar KDS. É
  erro humano com consequência física, e o antídoto proporcional é identidade visual, não RBAC.

**Descartados:**
- **Campo `version`/`rev` novo no `KDSTicket`** (implícito em G, explícito em D). Migração e campo novo no
  core para um problema que a identidade estável do item resolve sozinha. O CLAUDE.md é explícito: não
  adicionar campo ao core sem necessidade comprovada. Resolver por `line_id` **dentro do lock** elimina a
  classe inteira sem `rev` nenhum.
- **Envelope comum em todas as mutações** (G e D). O cliente não lê **nenhum** campo de **nenhuma** dessas
  respostas — ele refaz o fetch. É inventar contrato para consumidor que não existe, e reabre o `version`
  descartado acima.
- **Vincular `KDSInstance` a `Terminal`** (G). O Agente D já vetou e está certo: acopla cozinha a caixa.
- **Checklist de expedição com troco/equipamento** (G). Nem o card nem o pedido expõem esses dados ao KDS. É
  contrato novo com payman/cashman — intenção registrada, não escopo.
- **"SSE autoriza por tipo de canal" como falha de autorização própria** (G). O REST tem exatamente o mesmo
  gate grosso. Contar como achado separado é contar o mesmo buraco duas vezes.

**Corrigido por excesso:** o fix de RBAC dos dois está **errado por caro**. Não é preciso criar
`backstage.manage_kds_config`. Ver P1-1.

**Novos:** marcar item é um *toggle* com leitura fora do lock; o painel público publica telefone/CPF;
`action` não-string vira 500; a rota pública está em português.

## Pré-requisitos

- **WP-00 Bloco B** (parser de entrada): P2-1 e P2-4 consomem o helper de lá.
- Nenhum outro. Este WP **não cria permissão custom, não cria modelo e não gera migração** — e isso é uma
  escolha, não um acaso.

## Achados priorizados

### P1-1 — A estação do KDS pode ser apagada por quem só sabe fritar pão

O único achado destes nove cujo dano é **irreversível** e cujo gatilho é um clique num botão vermelho.

**Mecanismo.** O grupo Cozinha tem `is_staff` e entra no Admin. Como `KDSInstanceAdmin.has_view_permission`
devolve `True` para `operate_kds`, "estações KDS" aparece no índice para o cozinheiro — e
`has_delete_permission` devolve `True` pela mesma régua. Ele apaga a estação; `KDSTicket.kds_instance` é
`on_delete=CASCADE`, então **todos os tickets vivos daquela estação somem do banco**: sem cancelamento, sem
alerta, sem trilha. O board da outra bancada esvazia no próximo poll e ninguém sabe o que era para fazer. O
caminho menos dramático é o mesmo botão mudando as coleções: o roteamento quebra e os itens deixam de chegar
à cozinha.

**Fix mínimo — e é menor que o dos dois WPs: apagar código.** Remover os quatro overrides `has_*` de
`admin/kds.py:53-63`. Sem eles o `ModelAdmin` cai nas permissões de modelo padrão do Django, que já existem
desde a migração inicial. Efeito:

- **Cozinha** perde a tela inteira automaticamente — não tem `_ver("backstage")`. Zero linha alterada no bloco.
- **Gerente** já tem `view_kdsinstance` via `_ver("backstage")`. Falta escrita: **uma linha**,
  `*_escrever("backstage", "kdsinstance"),`.
- `_escrever` dá `add_` e `change_`; `delete_` fica de fora por decisão já documentada no próprio arquivo
  ("apagar fica de fora de propósito"). **Ninguém** passa a poder apagar estação pelo Admin — que é o
  comportamento certo, e resolve o CASCADE pela raiz.

Sem permissão custom, sem migração, e **sem tocar o teste de paridade** (que rastreia permissões custom, não
permissões de modelo). A proposta de `manage_kds_config` custaria as três coisas.

### P1-2 — "Marcar item" é um toggle, com a leitura fora do lock: o item desmarca sozinho

Dois tablets na mesma bancada é a configuração normal de uma cozinha.

**Mecanismo.** A API recebe um comando de **estado desejado** (`checked: true`), mas o serviço lê o estado
atual **fora de qualquer transação**, compara, e só então chama um `toggle` que abre a própria transação com
`select_for_update`. A decisão "isto muda ou não" é tomada com dado sujo; o lock protege apenas a inversão.

Dois cozinheiros tocam o mesmo item quase juntos, ambos querendo marcar. A requisição A lê "desmarcado" →
inverte → **marcado**. A requisição B, que já tinha lido "desmarcado", inverte → **desmarcado**. As duas telas
mostram marcado por otimismo e, meio segundo depois, a reconciliação reverte as duas ao mesmo tempo. O
cozinheiro vê o pão que ele marcou desmarcar sozinho, sem explicação nenhuma na tela.

**Fix mínimo:** o core precisa de um `set`, não de um `toggle` — escrever o estado desejado dentro do lock, e
apagar a comparação pré-lock. A operação vira idempotente por construção, que é o que a API já dizia ser (há
um teste chamado "idempotent" que só passa porque roda em série).

Combina com o P2-2: os dois fixes tocam a mesma função do core.

### P1-3 — O painel público de retirada mostra telefone ou CPF inteiro

É a tela do salão, à vista de todo mundo — e a função que deveria proteger contra isso **se chama
`_public_comanda_code` e promete no docstring que protege**.

**Mecanismo.** A função trata "puramente numérico" como sinônimo de "não identificante": se a referência da
comanda é `isdigit()`, devolve o número; só o caso não-numérico vai para o hash. Mas a normalização de
comanda só faz `zfill(8)` em numéricos **de até 8 dígitos** — acima disso guarda o valor cru. Um telefone ou
um CPF (11 dígitos) digitado como referência passa por tudo e vai inteiro para a TV, em fonte de 7rem.

**Medido:** `normalize_tab_ref("43999887766")` devolve o número intacto, e a projection pública o publica.

O caminho do operador é banal: o balcão abre a comanda usando o telefone do cliente — hábito comum de
padaria, é o identificador que ele já pediu para o WhatsApp. O assert-negativo de PII que existe hoje não
pega: ele testa nome, não dígito.

**Fix mínimo — uma linha:** amarrar a heurística ao formato real de comanda numérica, que é conhecido e tem
no máximo 8 dígitos. Acima disso, cai no hash — que é o comportamento que o docstring já promete.

⚠️ Ver a pergunta 2: se o balcão **usa** telefone como comanda, isto é P0, não P1. A pergunta muda a
prioridade, não o fix.

### P1-4 — Ref de estação inválida **ou desativada** vira 500

**Mecanismo.** A projection faz `.get(ref=..., is_active=True)` sem guarda, e `DoesNotExist` não é convertido
pelo handler de erro. **Medido:** ref inexistente → 500; e **estação existente com `is_active=False` → 500
também** — essa metade é nova, e é o caso que um gerente provoca sozinho.

Do lado do operador: o gerente desativa "Bancada 2" no fim do turno. O tablet daquela bancada, com a URL no
bookmark do kiosk, passa a mostrar "Falha ao carregar o board. Reconectando…" **para sempre** — o poll bate
num 500, o operator-kit trata 5xx como retryável, e ele tenta a cada 15 s indefinidamente, enchendo a
telemetria de erro de servidor. O operador não tem como saber que a estação foi desligada de propósito.

Isso contraria uma regra já escrita da casa: "não encontrado mapeia por tipo de exceção". A regra existe; a
view do board não a aplica.

**Fix:** exceção de domínio nova, irmã da que já existe para ticket, mapeada para 404 — com mensagem
distinguindo "estação não existe" de "estação está desativada", que são coisas diferentes para quem está com
o tablet na mão.

### P2-1 — `checked` não-booleano é aceito

Fix de uma linha, gravidade de higiene. Ver o rebaixamento acima. Consome o parser do WP-00 Bloco B.

### P2-2 — Índice mutável: o `unfire` do PDV desloca os itens de um ticket vivo

Ticket com `[A, B, C]`; o PDV cancela o envio de B; o ticket vira `[A, C]`. Se o cozinheiro tocar antes do SSE
chegar, o POST carrega índice velho: `index=2` dá 400; `index=1` **marca C achando que é B**.

**Fix:** projetar `line_id` como `item_ref` (o dado já está no ticket, só não é projetado), aceitar `item_ref`
no POST e resolver **dentro do lock**. Item cujo `line_id` sumiu → 409 com "Este item saiu do pedido" —
mensagem acionável, não 400 genérico. O card de expedição também tem `line_id` próprio; dá para preencher os
dois.

### P2-3 — O payload SSE do canal `kds` carrega `session_key` e `order_ref`

**Fix — é uma deleção:** apagar as duas chaves do dict, e com elas a query que as buscava, que vira morta.
**Zero risco de regressão no cliente**: a UI não lê campo nenhum do evento, ela refaz o fetch. O único ajuste
é inverter um assert de teste existente.

### P2-4 — `action` não-string na expedição vira 500

`(request.data.get("action") or "").strip()` — um dict ou list é truthy, não é descartado pelo `or`, e o
`.strip()` levanta `AttributeError`. **Medido:** os dois dão 500.

O contraste torna isto inconsistência, não detalhe: existe um teste no mesmo arquivo justamente para garantir
que **500 significa bug de programação**, porque o operator-kit trata 4xx como não-retryável e a telemetria
classifica 5xx como erro de servidor. Aqui um payload malformado é classificado como bug do servidor e o
cliente entra em retry.

**Fix — uma linha:** `str(...)` antes do `.strip()`. A validação do conjunto logo abaixo já rejeita o resto
com 400.

### P2-5 — Estação não é vinculada a nada

Qualquer `operate_kds` abre qualquer board e opera qualquer ticket. O operador da Bancada 1 abre a URL da
Bancada 2 — bookmark errado, tablet trocado — e dá "Finalizar" em tickets que a Bancada 2 ia fazer; os itens
viram todos marcados e o pedido pode avançar sem que aquele preparo tenha existido.

**Fix mínimo, e é o barato:** a "identidade gigante da estação" que os dois WPs já listam como melhoria de
UX — nome, cor e código grandes no topo, mais confirmação no "Finalizar". Isso resolve o erro real.

O vínculo operador→estação com override de supervisor **não entra neste WP**: é modelo novo, permissão nova e
fluxo de exceção, para um risco que a identidade visual resolve. Ver a pergunta 1. Se um dia entrar, a
exceção para `type="expedition"` (board global por design) é obrigatória — o Agente D acertou nisso.

### P2-6 — A rota pública é `kds/cliente/`, em português

O CLAUDE.md diz, sem exceção: "URL é em inglês. Ponto. Vale para toda rota do sistema." A varredura de URLs
do PR #169 pegou Admin e backstage HTML e deixou esta rota de API para trás — resíduo da era HTMX. Não há
waiver documentado. Efeito colateral pequeno mas real: como `kds/cliente/` vem antes de `kds/<ref>/`, uma
estação cadastrada com ref `cliente` fica inalcançável.

**Fix:** renomear para `kds/pickup/`, zerando o nome antigo. Sem 301 — é chamada de BFF, não bookmark de
kiosk (o kiosk aponta para `/pickup` do Nuxt).

## Observação registrada, não é achado

`backstage.operate_kds` concede leitura do canal `orders`, justificado no comentário pelo painel de retirada
— mas o painel de retirada é a **tela pública**, isenta de login, cujo endpoint REST não exige permissão. Numa
TV de salão sem sessão o SSE recebe 403 e o painel cai para poll, e o indicador honesto até mostra "Atualiza
sozinho". O grant só é exercido quando alguém abre a tela pública no mesmo navegador onde a estação está
logada.

**Não proponho remover** — a TV logada é caso plausível e derrubar o grant a quebraria em silêncio. Registro
para que este WP **não** trate isso como achado de autorização, e para que a pergunta 3 seja feita.

## RBAC / `setup_groups`

**Nenhuma permissão custom nova. Uma linha.**

- Cozinha: **zero** alteração — perde o Admin de estações automaticamente ao removermos os overrides.
- Gerente: `*_escrever("backstage", "kdsinstance"),`.
- Teste de paridade: **não muda** (permissão de modelo, não custom). É a vantagem concreta desta solução
  sobre a dos dois WPs anteriores.

⚠️ Esta linha vai no **PR único de permissões da onda 4** (WP-00 Bloco D3).

## Testes

1. Cozinha recebe 403 no Admin de estações KDS, inclusive no delete. Gerente abre a change view.
2. `checked` não-booleano (`"false"` em JSON e form-encoded, `null`, `1`, `[]`) → 400 com `field: checked`, e
   o ticket **não** muda. Boolean real continua 200.
3. Marcar item é idempotente sob concorrência: duas chamadas simultâneas com `checked=true` sobre um item
   desmarcado deixam o item marcado — **hoje deixam desmarcado**. (Basta o teste unitário provando que a
   função **escreve** o estado desejado em vez de inverter.)
4. Remover o item do meio via `unfire` e marcar pelo `line_id` do sobrevivente marca o item certo;
   `item_ref` inexistente → 409 com mensagem acionável.
5. `item_ref` presente e não vazio no ticket de preparo **e** no card de expedição; contrato TS regerado (o
   teste de export já falha sozinho se o espelho ficar velho).
6. Ref inválida → 404; estação desativada → 404 **com mensagem própria**. Hoje os dois são 500 (medido).
7. `action` dict e `action` list → 400, nunca 500. Hoje os dois são 500 (medido).
8. Nenhum evento do canal `kds` contém `session_key` ou `order_ref` (assert-negativo, invertendo o assert
   existente).
9. Comanda de 11 dígitos → o painel público publica o hash (`#…`); comanda de até 8 dígitos continua número.
10. Board de expedição continua global — guarda de regressão contra o P2-5.
11. `kds/cliente/` não existe em nenhum arquivo; a rota resolve para `kds/pickup/`.

## Arquivos tocados (para a matriz de colisão)

| Arquivo | Risco | Quem mais mexe |
|---|---|---|
| `shopman/shop/handlers/_sse_emitters.py` | **ALTO** | Arquivo único de todos os canais SSE. Qualquer WP de PDV/Pedidos/Produção mexe aqui. |
| `shopman/shop/management/commands/setup_groups.py` | **ALTO** | **PR único de permissões, onda 4.** |
| `shopman/shop/services/kds.py` | MÉDIO | Consumido pelo PDV (fire/unfire). |
| `shopman/backstage/api/urls.py` | MÉDIO | Compartilhado por todas as APIs do backstage. |
| `shopman/backstage/{api,services,projections,admin,models}/kds.py` | BAIXO | exclusivos |
| `surfaces/kds-nuxt/**` + `generated/kdsContract.ts` (regerado) | BAIXO | — |

⚠️ **Não tocar `shopman/shop/eventstream.py`.** O fix do P2-3 é só no payload; mexer no gate abre colisão
alta sem necessidade.

## Fora de escopo

Pagamento, desconto, preço, caixa, cancelamento comercial, edição de comanda no PDV, planejamento produtivo,
B.I. Vínculo `KDSInstance` ↔ `Terminal`. Campo `version`/`rev` no core. Envelope comum de mutação. Semântica
do `unfire` (é do PDV — o KDS é vítima do deslocamento, não dono da causa). Sons, densidade, undo e regressão
visual: WP de UX separado, não bloqueiam nada daqui.

## Perguntas para o dono do produto

1. **Uma bancada pode dar "Finalizar" no ticket de outra, e isso deve ser impedido pelo sistema ou pela
   tela?** Dois caminhos com custo muito diferente: identidade visual grande e confirmação (barato, resolve o
   erro humano) ou vínculo operador→estação com override (modelo, permissão, fluxo de exceção). Só o dono
   sabe se, na Nelson, "a Bancada 1 nunca toca na Bancada 2" é regra ou etiqueta. **A resposta decide se o
   P2-5 é UX ou RBAC.**
2. **O balcão usa o telefone do cliente como referência de comanda?** Se sim, o P1-3 é **P0** — hoje o número
   aparece inteiro na TV do salão (medido).
3. **A TV de retirada roda logada como operador ou em navegador anônimo?** Se anônima, o grant do canal
   `orders` não serve a ninguém e pode encolher; se logada, ele é load-bearing e removê-lo quebraria o push
   em silêncio.

## Prompt para agente executor

~~~text
Execute WP-04-agente-c (KDS).

⚠️ A linha de setup_groups.py NAO vai neste branch — vai no PR unico de permissoes da
onda 4 (WP-00 Bloco D3). O resto deste WP e independente e pode ir na onda 1.

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-04-agente-c-kds.md
- docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-00-agente-c-transversal.md (Bloco B)
- shopman/backstage/admin/kds.py:53-63
- shopman/backstage/services/kds.py:18-28 e shopman/shop/services/kds.py:452-477
- shopman/backstage/projections/kds.py:41-51, 183, 322-337, 449-459, 503-513
- shopman/backstage/api/kds.py:67-69, 85-97, 185
- shopman/shop/handlers/_sse_emitters.py:381-399
- docs/decisions/adr-016-sse-first-realtime.md (regra 1: payload minimo)

Fases:
1. P1-1: APAGAR os quatro has_* de admin/kds.py. Nao criar permissao custom.
2. P1-3: uma linha em _public_comanda_code + teste 9.
3. P1-4: excecao de dominio + 404 nos dois casos (inexistente E desativada) + teste 6.
4. P1-2 + P2-2: o core passa a ESCREVER o estado desejado dentro do lock, e o item
   passa a ser enderecado por line_id. Mesma funcao, um PR. Regerar kdsContract.ts
   com `python manage.py export_kds_schema` — nunca a mao.
5. P2-1 e P2-4: parser estrito (helper do WP-00) + str() antes do strip.
6. P2-3: apagar as duas chaves do payload SSE e a query morta; inverter o assert do teste.
7. P2-6: renomear a rota para kds/pickup/, zerando o nome antigo. Sem 301.
8. P2-5: identidade grande da estacao + confirmacao no Finalizar. So isso — o vinculo
   operador->estacao depende da pergunta 1 e NAO entra aqui.

NAO crie backstage.manage_kds_config. NAO crie campo version/rev no KDSTicket.
NAO padronize envelope de mutacao. NAO toque shop/eventstream.py.
NAO mude a semantica do unfire (e do PDV).
~~~
