# 01 · Login por WhatsApp: o nome completo caiu num campo só

**Data:** 30/09/2026
**Árvore:** `.dsh-worktrees/go-live-acceleration` (branch `dsh/handoff-onda1-e-p7-20260930`)
**Escopo:** fluxo NOVO de login por WhatsApp (access-link / ManyChat External Request), do corpo do request até o registro do `Customer`.
**Observação do dono:** o nome completo ("Pablo Valentini") caiu num campo só; ele quer nome e sobrenome separados quando possível ("Pablo" / "Valentini").

> **Validade contra o `origin/main`** — `git diff --stat origin/main...HEAD` devolve **2 arquivos, ambos `.md`** (`docs/plans/NIGHT-SHIFT-BRIEF-2026-09-30.md` e `docs/reports/go-live-acceleration-20260929/HANDOFF.md`). **Nenhum `.py` difere do `origin/main`**, então toda citação de código abaixo vale igual no `main`. [FATO]

---

## 0. Resposta curta

| Pergunta | Resposta |
|---|---|
| **(a) Origem do nome** | O campo `first_name` do objeto `subscriber` que o **Flow do ManyChat** manda no corpo do External Request (a variável `{{First Name}}`), gravado **verbatim** em `Customer.first_name`. Nada entre a porta e o banco divide, valida ou completa. |
| **(b) O modelo** | **Já tem dois campos separados**: `Customer.first_name` (verbose "nome") e `Customer.last_name` (verbose "sobrenome"). Não é campo único — é um campo só sendo *preenchido*. |
| **(c) Dá para separar com segurança?** | **Não com certeza.** Nenhuma regra acerta os três exemplos do dono. Existe uma regra que erra do lado menos nocivo e já é a da casa. |
| **(d) Entrada ou exibição?** | **Entrada** — num único ponto que os dois caminhos de escrita atravessam, e guardando o texto original ao lado. Justificativa na seção 5. |

**Diagnóstico em uma frase:** o caminho de **login** por WhatsApp grava o nome do provedor sem dividir; o caminho de **pedido** pelo mesmo ManyChat já divide. É inconsistência entre dois fluxos irmãos, não ausência de capacidade.

---

## 1. O caminho exato — do WhatsApp ao banco

```
WhatsApp (cliente digita #menu ou o botão do site)
   │
   ▼
ManyChat Flow  ── External Request (POST, json) ──►  /api/auth/access/create/
   │   body: {"subscriber": {"id": "{{Subscriber ID}}",
   │                         "whatsapp_id": "{{WhatsApp ID}}",
   │                         "first_name": "{{First Name}}",     ◄── O NOME ENTRA AQUI
   │                         "last_name":  "{{Last Name}}"},
   │          "access_code": "{{Last Text Input}}", "next": "/menu"}
   ▼
doorman/views/access_link.py:26   AccessLinkCreateView.post
   ├─ :403  source = data.get("source", AccessLink.Source.MANYCHAT)   ← default MANYCHAT
   ├─ :429-433  subscriber = data["subscriber"] or data["manychat_subscriber"] or top-level
   └─ :435  if source == MANYCHAT and subscriber:            ◄── É ESTE O RAMO DO LOGIN
         :446  customer = resolver.upsert_manychat_subscriber(subscriber)
                │
                ▼
guestman/adapters/auth.py:64   CustomerResolver.upsert_manychat_subscriber
   ├─ :68   _enriched_subscriber(subscriber_data)     ← busca no getInfo o que faltou
   └─ :67   ManychatService.sync_subscriber(...)
                │
                ▼
guestman/contrib/manychat/service.py:71   ManychatService.sync_subscriber
   ├─ :143  _create_customer(data, source_system)     ← cliente NOVO
   └─ :122  _update_customer(customer, data)          ← cliente EXISTENTE
              │
              ▼
   service.py:301-319  _create_customer
        :311  first_name=data.get("first_name", "")     ◄── VERBATIM, sem split
        :312  last_name=data.get("last_name", "")
   service.py:321-359  _update_customer
        :331  if data.get("first_name") and not customer.first_name:
        :332      customer.first_name = data["first_name"]   ◄── VERBATIM, sem split
        :335  if data.get("last_name") and not customer.last_name:
        :336      customer.last_name = data["last_name"]
```

**Caminho irmão (magic link com `customer_id`) — também grava verbatim:**
`doorman/views/access_link.py:406-425` → `resolver.upsert_access_link_customer(customer_id, payload)` (`guestman/adapters/auth.py:51-62`) → `ManychatService.sync_customer` (`service.py:203-217`) → `_update_customer` (`:215`). Mesmo `:331-337`.

**O exchange do token NÃO escreve nome.** `AccessLinkService.exchange` (`packages/doorman/shopman/doorman/services/access_link.py:210`) e `AccessLink.get_customer` (`packages/doorman/shopman/doorman/models/access_link.py:157-162`) só **leem**. O nome já entrou no banco na criação do link. [FATO — grep por `first_name` em todo `packages/doorman/` só encontra o adaptador noop, o bridge de `User` e a docstring do view]

### 1.1 O vazamento também é visível pela via de enriquecimento

`guestman/adapters/auth.py:100-126` (`_enriched_subscriber`) consulta a API do ManyChat quando o payload não trouxe telefone e, de lambuja, copia nomes:

```
:123   for key in ("ig_id", "ig_username", "first_name", "last_name", "email"):
:124       if not payload.get(key) and (info or {}).get(key):
:125           payload[key] = info[key]
```

Ou seja: **mesmo que o Flow não mande nome nenhum**, o login busca `first_name`/`last_name` no ManyChat e grava. E o `name` do assinante (o campo que a própria API do ManyChat expõe, ver `evidence/conversational/whatsapp-window/message-identity-audit.json:7-37`, item `"name"`) é **descartado** — nunca é lido. [FATO]

---

## 2. (a) Origem exata do nome

### 2.1 Contexto factual

1. **O contrato documentado do Flow manda dois campos separados** — `docs/guides/whatsapp-access-link.md:134-146`:
   ```json
   {"subscriber": {"id": "{{Subscriber ID}}", "whatsapp_id": "{{WhatsApp ID}}",
                   "first_name": "{{First Name}}", "last_name": "{{Last Name}}"}, ...}
   ```
   [FATO — é a documentação do repositório, e ela registra a **intenção**, não a configuração viva]

2. **O código grava o que chega, sem dividir** — `service.py:311-312` e `:331-337`. [FATO]

3. **Sintoma do dono** (nome completo em "Pablo Valentini", num campo só) é consistente com: `first_name = "Pablo Valentini"` e `last_name = ""`. [INFERÊNCIA a partir do relato — não vi o registro real]

### 2.2 A pergunta que decide o conserto — e a resposta honesta

Há **duas causas possíveis**, e elas pedem consertos diferentes:

| # | Mecanismo | Conserto |
|---|---|---|
| **M1** | O contato no ManyChat tem `First Name = "Pablo Valentini"` e `Last Name` vazio. É o comportamento esperado para contato de **WhatsApp**: o WhatsApp só tem **um** campo de nome de perfil (texto livre), e o ManyChat o despeja em `first_name`; `last_name` fica vazio porque nunca existiu. | **Código** — dividir na entrada. |
| **M2** | O Flow está com a variável errada no campo `first_name` (ex.: `{{Full Name}}`/`{{Name}}` em vez de `{{First Name}}`), ou o campo `Last Name` não está preenchido no External Request. | **Flow no ManyChat** — corrigir a variável. Zero código. |

**Não é possível decidir entre M1 e M2 de dentro do repositório.** [NÃO VERIFICADO]

**Onde procurei e não achei** (nenhum payload real de assinante de WhatsApp capturado no alpha):
- `evidence/conversational/` — só payload sintético: `flows/manychat-conversation-v2.json:22` traz `"first_name": "Cliente sintético"` (literalmente "sintético"); `whatsapp-window/message-identity-audit.json` é a **lista de campos** da Page API do ManyChat (útil, ver 2.1), não um payload.
- varredura por `"first_name": "<Duas Palavras>"` em `.py`/`.json`/`.md` — o único acerto é um **teste** (`shopman/storefront/tests/api/test_account_summary.py:288`, que manda `{"first_name": "Ana Maria"}` para provar outra coisa: que o PATCH parcial não apaga e-mail).
- `docs/` — nenhum documento diz de onde vem o `First Name` do contato de WhatsApp no ManyChat. A busca por "perfil do WhatsApp", "profile name", "push name" em `docs/**/*.md` volta zero.
- `docs/plans/NIGHT-SHIFT-BRIEF-2026-09-30.md:103-104` registra que a observação do dono existe ("login por WhatsApp (nome/sobrenome)") mas a seção 6.2 que traria o veredito **ficou vazia**.

**Teste decisivo que só o dono (ou quem tem a conta) pode fazer, e leva 1 minuto:**
1. Abrir o contato do "Pablo Valentini" no ManyChat → ver se o campo **First Name** contém `Pablo Valentini` inteiro e **Last Name** está vazio.
2. Abrir o External Request do Flow *Fluxo Login Cardápio* → conferir se o campo `first_name` do JSON está com **`{{First Name}}`** (seletor de variáveis) e não com `{{Name}}`/`{{Full Name}}` nem com um nome digitado à mão.
   - ⚠️ O backend já **recusa com 422** variável não renderizada e diz o campo — `packages/doorman/shopman/doorman/views/access_link.py:86-103` (`access_link.unrendered_manychat_variables`). Então "variável digitada à mão" já está excluída. O que **não** está coberto é a variável *existente e renderizada, mas errada*.

**Recomendação:** assumir **M1** como hipótese de trabalho (é o mecanismo padrão de contato de WhatsApp e explica o sintoma exato) e **mesmo assim** deixar o conserto robusto a M2 — que é o que a proposta da seção 5 faz, por construção: se o Flow passar a mandar `{{First Name}}`/`{{Last Name}}` corretamente, a regra "confie no `last_name` explícito" não toca em nada.

---

## 3. (b) O modelo — campo separado ou um só?

**Já são dois campos.** `packages/guestman/shopman/guestman/models/customer.py:55-57`:

```python
# Basic data (first_name + last_name - see spec 000 section 12.5)
first_name = models.CharField(_("nome"), max_length=100)
last_name  = models.CharField(_("sobrenome"), max_length=100, blank=True)
```

- Comentário no código cita "spec 000 section 12.5". [FATO]
- `Customer.name` (`:156`) recompõe para exibição: `f"{self.first_name} {self.last_name}".strip()`. [FATO]
- Migração inicial idem: `packages/guestman/shopman/guestman/migrations/0001_initial.py:23-24`. [FATO]
- **Não há campo único de nome** e **não há nada em `metadata`** com o nome cru. `metadata` é `JSONField` (`customer.py:112`) e o único uso no sync do ManyChat é `{"manychat_custom_fields": ...}` (`service.py:316`, `:351-355`). [FATO]

**Consequência:** o problema do dono **não é de modelo**. É de um write que enche um campo com o conteúdo dos dois.

---

## 4. (c) Dá para separar com segurança?

### 4.1 O que a casa já tem

Existe **um** divisor de nome no repositório, em duas cópias:

- `shopman/shop/services/customer.py:314-316`
  ```python
  def _split_name(full_name: str) -> tuple[str, str]:
      parts = full_name.strip().split(None, 1)
      return (parts[0] if parts else "", parts[1] if len(parts) > 1 else "")
  ```
- `shopman/shop/services/pos.py:5277-5278` — **cópia idêntica**. [FATO]

### 4.2 Onde ela é usada — e onde NÃO é

| Caminho | Divide? | Evidência |
|---|---|---|
| Pedido vindo do **ManyChat** | **SIM** | `shop/services/customer.py:114` (`_handle_manychat`), e `:359` (`_maybe_update_name`) |
| Pedido **iFood** | SIM | `:161` |
| **PDV / balcão por CPF** | SIM | `:243` |
| **Balcão por telefone** | SIM | `:275` |
| **PDV (registro no caixa)** | SIM | `shop/services/pos.py:4326`, `:4774` |
| **LOGIN por WhatsApp (access-link)** | **NÃO** | `service.py:311-312`, `:331-337` — nenhum `_split_name` no caminho |

**É a inconsistência exata.** O pedido que chega pelo ManyChat já divide; o login pelo mesmo ManyChat não. [FATO]

> ⚠️ Nota de acoplamento: `_split_name` mora no **orquestrador** (`shopman/shop/services/`). O `guestman` é pacote de Core e **não pode importar do shop** (regra de dependência do `CLAUDE.md`). O conserto proposto (seção 5) precisa de uma cópia local — o que faria a **terceira** cópia do mesmo helper. Vale considerar na hora de implementar (seção 6).

### 4.3 O teste empírico — rodei o helper real contra os exemplos do dono

Comando (extrai a função por AST do arquivo real e executa; `[FATO]`):

```bash
/usr/bin/python3 - <<'PY'
import ast
src = open('shopman/shop/services/customer.py', encoding='utf-8').read()
fn = next(n for n in ast.parse(src).body
          if isinstance(n, ast.FunctionDef) and n.name == '_split_name')
ns = {}; exec(compile(ast.Module(body=[fn], type_ignores=[]), '<split>', 'exec'), ns)
for c in ["Pablo Valentini", "Ana Maria Silva", "Jos\u00e9 da Silva Neto",
          "Pablo", "Maria Jos\u00e9", "Ana Maria de Souza"]:
    print(f'{c!r:24} -> {ns["_split_name"](c)}')
PY
```

Saída (verbatim):

```
'Pablo Valentini'        -> first_name='Pablo'        last_name='Valentini'
'Ana Maria Silva'        -> first_name='Ana'          last_name='Maria Silva'
'José da Silva Neto'     -> first_name='José'         last_name='da Silva Neto'
'Pablo'                  -> first_name='Pablo'        last_name=''
'Maria José'             -> first_name='Maria'        last_name='José'
'Ana Maria de Souza'     -> first_name='Ana'          last_name='Maria de Souza'
```

### 4.4 As três regras candidatas e seus erros

| Regra | "Pablo Valentini" | "Ana Maria Silva" | "José da Silva Neto" | "Maria José" (só prenome) | Erro característico |
|---|---|---|---|---|---|
| **A** — primeiro token = nome, resto = sobrenome (**a da casa**, `customer.py:315`) | Pablo / Valentini ✔ | **Ana / Maria Silva** ✘ | José / da Silva Neto ✔ | **Maria / José** ✘ | prenome vaza para o sobrenome; inventa sobrenome em nome único composto |
| **B** — último token = sobrenome | Pablo / Valentini ✔ | Ana Maria / Silva ✔ | **José da Silva / Neto** ✘✘ | Maria / José ✘ | sobrenome cai no campo do nome e **sufixo fica sozinho**; pior dos erros |
| **C** — partir antes da última sequência ligada por partícula (`de/da/do/das/dos/e`) | Pablo / Valentini ✔ | **Ana / Maria Silva** ✘ | José / da Silva Neto ✔ | Maria / José ✘ | melhor nos 3 do dono, **mas ainda inventa sobrenome** em "Maria José" |

**Resposta honesta:** **não, não dá para separar com segurança.** Em português do Brasil o sobrenome é composto e sem marcador sintático; "Ana Maria Silva" e "José da Silva Neto" têm pontos de corte corretos **diferentes** e **nenhuma regra puramente sintática** os distingue. A regra C chega mais perto, mas o único jeito de *saber* é perguntar à pessoa.

**O que dá para fazer com segurança:**
1. **Nunca adivinhar quando o provedor já disse** — `last_name` não vazio entra verbatim, sem tocar.
2. **Nunca sobrescrever** — `_update_customer` (`service.py:331-337`) já só preenche campo vazio. Preservar isso.
3. **Escolher a regra cujo erro é menos nocivo.** A **Regra A** erra sempre do lado do **sobrenome** ("Maria Silva", "Maria de Souza"). O `last_name` **nunca é usado para tratar ninguém** — todas as saudações do sistema usam o primeiro nome (`omotenashi/context.py:193`, `marketing_delivery_whatsapp.py:116`, `handlers/campaign.py:584`). Já a Regra B põe sobrenome no campo que **é** usado para saudar. Errar do lado do sobrenome é degradação silenciosa; errar do lado do nome, não.
4. **Guardar o texto cru ao lado** para que a divisão seja reparável (seção 5).

---

## 5. (d) Dividir na ENTRADA ou na EXIBIÇÃO?

### Recomendação: **DIVIDIR NA ENTRADA** — em `ManychatService`, com o texto cru preservado.

### 5.1 Por quê (cada razão ancorada em código)

**1. `first_name` não é campo de exibição — é o token de saudação, consumido cru em pelo menos 3 lugares que saem do sistema:**
- `shopman/shop/adapters/marketing_delivery_whatsapp.py:116` → `"customer_name": (getattr(customer, "first_name", "") or "").strip()`
- `shopman/shop/handlers/campaign.py:584` → `"customer_name": getattr(recipient, "first_name", "") or ""`
- `shopman/shop/handlers/_stock_receivers.py:289` → idem
- e o derivado `customer_name_greeting` = `f", {name}"` em `shopman/shop/adapters/_notification_templates.py:80-81`

Com o nome completo lá dentro, a mensagem que sai é **"Oi Pablo Valentini"** — em WhatsApp, para o cliente. Dividir na exibição significa consertar **cada um desses**, mais os templates de `NotificationTemplate` editáveis no Admin, mais as variáveis de Flow que já saíram do repositório. [FATO nas linhas; a conclusão é [INFERÊNCIA] direta]

**2. A tela de edição assume a divisão — e o portão de boas-vindas não consegue consertá-la.**
- `surfaces/storefront-nuxt/app/pages/conta/perfil.vue:22` tem `reactive({ first_name, last_name, email, birthday })` e `:239-241` dois campos rotulados "Primeiro nome" / "Sobrenome", carregados de `GET /api/v1/account/profile/` (`shopman/storefront/api/account.py:456-457`). Hoje o cliente vê **"Pablo Valentini" dentro da caixa "Primeiro nome"** e "Sobrenome" vazia — foi provavelmente o que o dono viu.
- Pior: o **portão de boas-vindas manda SÓ `first_name`** — `surfaces/storefront-nuxt/app/pages/entrar.vue:461-466` (`body: { first_name: name }`), onde `name` vem de `welcome_suggested_name` (`:337`), que é o `clean_display_name(customer_name)` do backend (`storefront/api/auth.py:85`). Ou seja: **a tela que existe para o cliente confirmar o próprio nome é fisicamente incapaz de gravar o sobrenome.** [FATO]
- Isso já custou caro uma vez: `shopman/storefront/tests/api/test_account_summary.py:263-301` é um teste-trava nascido de um bug em que o portão mandava só `first_name` e apagava e-mail/sobrenome/aniversário. O comentário do teste (`:266-271`) diz explicitamente: *"O portão de boas-vindas (`entrar.vue`) manda SÓ `first_name`"*.

**3. A divisão na exibição não conserta o registro — e o registro é o que o dono olhou.** Ele é a fonte para: ticket do KDS (`shopman/backstage/services/order_ticket.py:248`), cupom impresso (`shopman/backstage/services/receipt_escpos.py:312-314`, `"Cliente: {name}"`), pagamento (`shop/services/payment.py:839-841`), prompt do concierge (`storefront/concierge/prompt.py:120-121`), B.I. e Exportação de conta. [FATO nas linhas]

**4. A exibição é N superfícies; a entrada é UMA função.** `_create_customer` + `_update_customer` (`service.py:301-359`) são atravessadas por **ambos** os caminhos de escrita do login (o do `subscriber` em `:143`/`:122` e o do `customer_id` em `:215`). É um só lugar em vez de uma varredura sem fim. [FATO]

**5. `Customer.name` já recompõe** (`customer.py:156`), então **nenhuma exibição perde o nome inteiro** ao adotar a divisão. [FATO]

### 5.2 O argumento contrário, dito com honestidade

Dividir na entrada **grava um palpite como se fosse dado**. "Ana Maria Silva" vira `sobrenome="Maria Silva"`. Mitigações, todas obrigatórias:
- só dividir quando o provedor **não** mandou `last_name` explícito;
- só preencher campo **vazio** (comportamento atual, `service.py:331-337`);
- **guardar o texto cru**;
- a tela de perfil do cliente é a superfície de correção (ela já existe e já edita os dois campos).

### 5.3 O desenho proposto (não implementado — esta tarefa é diagnóstico)

**Arquivo:** `packages/guestman/shopman/guestman/contrib/manychat/service.py`
**Ponto único:** `_create_customer` (`:301-319`) e `_update_customer` (`:321-359`).

```python
# regra, na ordem:
# 1. last_name explícito e não vazio  -> confia, não toca em nada
# 2. first_name com 1 token           -> so first_name, last_name fica ""
# 3. first_name com 2+ tokens         -> Regra A: primeiro token = first_name, resto = last_name
```

E, junto: gravar o valor original **cru** para tornar a divisão auditável e reparável, em `Customer.metadata` (JSONField, `customer.py:112` — **sem migração**, e alinhado à regra "Core é Sagrado" do `CLAUDE.md`), por exemplo:

```json
{"manychat_name_raw": {"first_name": "Pablo Valentini", "last_name": ""}}
```

⚠️ **Fora de escopo mas obrigatório citar** — ao adotar isso, três coisas precisam de decisão de quem implementa:
1. **A terceira cópia do divisor.** Já existem duas (`shop/services/customer.py:314`, `shop/services/pos.py:5277`). O `guestman` não pode importar do `shop` (regra de dependência). Ou se aceita a terceira cópia, ou se extrai para `shopman-utils` — que **é** importável por todos e é o lugar canônico para isso.
2. **O portão de boas-vindas** (`entrar.vue:465`) continua mandando só `first_name`. Enquanto for assim, corrigir o nome pela tela de entrada continua jogando o nome inteiro no primeiro campo **de novo** — a correção de entrada seria desfeita pelo próprio cliente na próxima confirmação. Consertar os dois é o mesmo trabalho.
3. **Contatos já gravados** com o nome inteiro em `first_name` não são corrigidos por um conserto de entrada. Um backfill seria decisão do dono (mexe em dado de cliente) — **não decidir sozinho**.

---

## 6. Resumo do que é fato e do que não é

**[FATO]**
- O login por WhatsApp grava o nome do provedor **verbatim**, sem dividir: `service.py:311-312` e `:331-337`.
- O modelo **já tem** `first_name`/`last_name` separados (`customer.py:56-57`) e recompõe em `name` (`:156`).
- O caminho de **pedido** pelo mesmo ManyChat **já divide** (`shop/services/customer.py:114` + `:359`); o de login, não.
- O contrato documentado do Flow manda `{{First Name}}` e `{{Last Name}}` (`whatsapp-access-link.md:140-141`).
- O exchange do token não escreve nome nenhum.
- A saudação em Marketing/Campanha usa `customer.first_name` **cru** (`marketing_delivery_whatsapp.py:116`, `campaign.py:584`, `_stock_receivers.py:289`).
- O portão de boas-vindas grava **só** `first_name` (`entrar.vue:465`), com teste-trava em `test_account_summary.py:263-301`.
- Divisão por regra sintática **erra** em "Ana Maria Silva" (saída do helper real, seção 4.3).

**[INFERÊNCIA]**
- Que o `First Name` do contato de WhatsApp no ManyChat venha do nome de perfil do WhatsApp, que é **um** campo de texto livre, e que por isso `{{Last Name}}` chegue vazio (mecanismo M1). Consistente com o sintoma e é o comportamento padrão desse tipo de contato, mas **não confirmado** neste repositório.
- Que "Pablo Valentini" esteja hoje em `Customer.first_name` com `last_name=""` — não vi o registro.

**[NÃO VERIFICADO]**
- A configuração viva do Flow no ManyChat (é fora do repositório) — se está com `{{First Name}}` ou com outra variável (mecanismo M2).
- Se existe contato real no alpha com `First Name` de duas palavras (procurei em `evidence/`, `docs/`, testes e fixtures: só sintético, ver 2.2).
- Se o `name` do assinante do ManyChat (`message-identity-audit.json:13`) carrega o nome de perfil completo — o campo existe na API e **é descartado** por `_enriched_subscriber` (`auth.py:123`), mas o conteúdo não foi observado.

**Teste decisivo pendente (1 minuto, precisa da conta do ManyChat):** abrir o contato e o External Request do Flow *Fluxo Login Cardápio*. Se `First Name` = "Pablo Valentini" e `Last Name` vazio → M1, conserto é código. Se o campo `first_name` do JSON do request estiver com variável errada → M2, conserto é no Flow.

---

## 7. Anexo — comandos usados (reproduzíveis)

```bash
# 1. o branch não difere do main em código
git diff --stat origin/main...HEAD            # -> 2 arquivos, ambos .md

# 2. a cadeia de escrita do nome
grep -rn "upsert_manychat_subscriber" --include=*.py .
grep -rn "def _split_name" --include=*.py .

# 3. quem usa customer.first_name cru na saudação
grep -rn '"customer_name":' --include=*.py shopman/shop/

# 4. comportamento real do divisor da casa (seção 4.3)
/usr/bin/python3 - <<'PY' ... PY
```
