# WP-09-agente-c — Admin canônico (Django + Unfold)

**Status:** pronto para implementação · **Autor:** Agente C (terceira leitura, 2026-08-29)
**Superfície:** Django Admin + Unfold — `shopman/backstage/admin/`, `admin_console/`, `packages/*/contrib/admin_unfold/`, `scripts/check_unfold_canonical.py`
**Objetivo:** nenhuma ação de estado é disparada por um link, ninguém age além do que a persona dele autoriza, e o guardrail canônico enxerga o drift que ele foi criado para pegar.

## Diferenças vs. WP-09 (Agente G) e WP-09-agente-d

**O P0 do Agente D está certo no mecanismo e errado no alvo — e o alvo certo é pior.** Ele afirmou que
"qualquer staff com view executa refund". Provado por introspecção: view-only **recebe** a ação, mas o único
grupo não-superusuário com `payman.view_paymentintent` é **Dono** — a persona que o RBAC define como dona do
dinheiro. Pela porta da frente, quem estorna é quem deve.

O buraco real é maior e é outro. Ver P0-1.

**Refutado com medição: "dezenas de violações" no gate ampliado é falso.** Rodei o gate sobre os alvos fora
dele: **20 violações em 4 arquivos**, todas da mesma família (span colorido, tailwind à mão), nenhuma exigindo
primitiva nova. Meio dia de trabalho. E **17 das 20 estão em código que nunca renderiza** — admins que o
contrib do próprio pacote desregistra. O faseamento que o Agente D propõe continua certo; o argumento dele
não. Ampliar o gate hoje faria `make admin` falhar por causa de arquivos que nenhuma tela usa — o que é
motivo para decidir sobre esses arquivos (pergunta 2), não para adiar o gate indefinidamente.

**Descartados:**
- **"Migrar `payment_refund.html` para primitivas Unfold" (G e D).** O template **já é** 100% `{% component %}`
  canônico — 44 linhas, lidas. Sobra montar label/help/errors à mão em uma faixa. Custo de mexer maior que o
  risco. Vira nota de estilo, se tanto.
- **"Reset de PIN é exposição a view-only" (G).** `has_view_permission` e `has_change_permission` do admin de
  credenciais são a **mesma** permissão. Não há assimetria. O que fica é a trilha (P1-3).
- **"Remover o token do agente do HTML" (G).** O Agente D já corrigiu com razão: o token precisa estar no DOM
  para o clipboard, o tradeoff está escrito no próprio arquivo, a tela é gateada, e o admin de terminal já o
  mostra mascarado. Se algo entrar, só o log de visualização, como P2.
- **"TrustedDevice deletável" como P1 (G e D).** Nenhum grupo tem permissão em doorman; só superusuário; e o
  delete grava `LogEntry`. P2 de higiene, não aceite de WP.
- **"View-only exporta PII" como escalonamento (D).** A ação aparece para view-only, mas o único grupo com
  `view_customer` também tem `change_customer`. O achado real é **motivo e trilha de LGPD**, não permissão —
  reescrito, não descartado.
- **"Import não deve publicar item fiscalmente incompleto" (G).** É feature nova offerman↔fiscalman. Fora.

**Novos:** os fieldsets em português do TOTPDevice são código morto **e a chave do 2FA está exposta**; o
Gerente reexecuta estorno pela tela de Diretivas; `unlock_pin` também não deixa trilha; o inventário do gate
esquece dois diretórios; o teste de refund existente prova a coisa errada.

## Pré-requisitos

⚠️ **Sobreposição em voo (29/08):** o [PR #395](https://github.com/nelsonboulangerie/django-shopman/pull/395)
(sessão `confident-pasteur-6cf01c`) traz um `SignInEventAdmin` somente-leitura e uma entrada nova em
`shopman/backstage/admin/navigation.py` — o mesmo arquivo que este WP toca. Sem permissão custom nova do lado
dela (o Gerente já pega `view_signinevent` pelo `_ver("backstage")` existente — o que é, aliás, mais uma
instância do auto-grant descrito na seção de RBAC). Rebasear sobre o #395. Migrations deste WP começam em
`backstage 0039`.

📎 **Frente de 2FA do Admin — três achados que não se fecham sozinhos.** Este WP tem *não existe check de 2FA
no deploy* (P1-6) e *a chave TOTP está exposta* (P1-4). O item 13 do inventário
`docs/plans/fallbacks-perigosos-go-live.md` (PR #393) traz o terceiro: *o middleware de 2FA do Admin deixa
passar quando a URL não resolve*. **Não são duplicata** — são as três metades do mesmo problema, e nenhuma
delas sozinha fecha a porta. Vale executá-las juntas. **Confirmado com a sessão dona do inventário: o item 13 é
deste WP, sem divisão** — ela o inventariou de passagem e não abriu frente. Idem o item 14, que pertence ao
WP-08. Incorporar o item 13 como P1-7 ao executar.

- Nenhum outro pré-requisito técnico. **Mas a pergunta 1 bloqueia parte do P0-1**, e a pergunta 2 define o tamanho da fase 2.
- ⚠️ Este WP toca `config/settings.py` em quatro pontos. **Agrupe as quatro linhas num bloco único, com
  comentário** — o arquivo tem 1.500+ linhas e é disputado por praticamente todo WP; um bloco contíguo torna
  o conflito trivial de resolver.

## Achados priorizados

### P0-1 — Ação de estado executada por GET, sem permissão de modelo e sem CSRF

**Não é "o refund do payman". É um padrão de três ocorrências, e o payman é a menos perigosa das três.**

**Mecanismo (provado por introspecção):**

1. O Unfold registra as URLs de `actions_row` / `actions_detail` / `actions_submit_line` embrulhadas
   **apenas** em `admin_site.admin_view`. Não há `AdminSite` custom no projeto — então isso é
   `is_active and is_staff`, e **zero permissão de modelo**.
2. O decorador de ação só checa permissão se receber `permissions=`. **Nenhuma ação do repositório usa
   `permissions=` ou `allowed_permissions`** — zero ocorrências em grep global.
3. Nenhuma dessas funções checa `request.method`. **Executam em GET.**
4. `SESSION_COOKIE_SAMESITE = "Lax"`, e Lax **envia** o cookie em navegação top-level GET. Um link mandado
   num WhatsApp, clicado pelo gestor logado, dispara a ação e redireciona para a lista como se nada tivesse
   acontecido.

| Ação | Quem alcança pela tela | Quem alcança pela URL |
|---|---|---|
| `refund_row` / `refund_selected` (payman) | só **Dono** | **qualquer staff** |
| `release_hold_row` / `release_holds` (stockman) | **Cozinha e Gerente** (têm `view_hold` sem change) | qualquer staff |
| `execute_row` / `execute_now_*` (orderman Directive) | **Gerente** | qualquer staff |

**O que dói de verdade, e que nem G nem D viram.** Entre os handlers de Directive existe um de tópico
`payment.refund`. E o `setup_groups.py` diz, por escrito: *"Dinheiro fica de fora, e não é esquecimento:
payman é do Dono."* **O Gerente, excluído do payman de propósito, reexecuta um directive de estorno pela tela
de Diretivas.** A fronteira de dinheiro desenhada no RBAC é contornada um model adiante.

Escopo honesto: ele não cria directive novo — não tem `add_directive`. Só reexecuta os que estão em fila ou
falhados. O que, para um estorno, basta.

**Fix mínimo — duas linhas por ação:** declarar `permissions=[...]` no decorador e definir o
`has_<x>_permission` correspondente; mais `require_POST` nas três `*_row` — ou migrar para dialog action do
Unfold, que já usa POST.

⚠️ **O teste que existe hoje dá falsa sensação de cobertura:** os quatro testes de refund usam
`admin_client` (superusuário). A suíte atesta que o refund **funciona** e nada diz sobre **quem pode**.

### P1-1 — Import de catálogo aberto a qualquer staff

O admin de produto herda o mixin de import/export sem sobrescrever `has_import_permission`, e o projeto não
define o código de permissão — então o default da biblioteca é `True`. As views de import são apenas
`admin_view`. **Um usuário do grupo Caixa POSTa um CSV e reescreve preço, publicação e vendabilidade de todo
o catálogo por SKU.** Sem dry-run visível para o gestor e sem trilha agregada.

**Fix mínimo — duas linhas em `config/settings.py`:** definir os códigos de permissão de import como
`"change"` e de export como `"view"`. O recorte já está certo: Gerente e Admin de Catálogo têm
`change_product`; Caixa e Cozinha não. Permissão dedicada só se o dono quiser separar "importar" de "editar".

### P1-2 — Ações de massa do catálogo sem confirmação

Seis ações — despublicar, publicar, pausar, retomar, **reprecificar por percentual** e adicionar a coleção —
sem permissão declarada, sem página de confirmação e sem preview. Provado: view-only recebe as seis.

**Recalibrado:** não é escalonamento (os dois grupos com `view_product` também têm `change_product`). É risco
de **erro humano**: "selecionar tudo" mais reprecificação por percentual reprecifica o catálogo inteiro num
clique. O save por item preserva o histórico, então há como reverter — o que baixa de P0 para P1.

**Fix:** `permissions=["change"]` nas seis, mais página de confirmação. O padrão já existe na casa: a ação de
etiquetar cliente do guestman usa `TemplateResponse` com template de confirmação.

### P1-3 — `reset_pin` e `unlock_pin` sem trilha; o PIN temporário sai por cookie

Gerar segredo novo **não** grava `LogEntry`, enquanto emitir e revogar crachá gravam — a assimetria é o
achado. E, novo: sem `MESSAGE_STORAGE` definido, o default escreve o PIN no **cookie** `messages` (assinado,
não cifrado) antes de tentar a sessão.

**Fix:** uma linha de registro em cada uma das duas ações; `MESSAGE_STORAGE` de sessão em `settings.py` (uma
linha, resolve metade do problema de graça); e o PIN em página one-time seguindo o padrão que a emissão de
crachá já usa.

### P1-4 — A chave do 2FA está exposta, e a tradução que "consertou" a tela é código morto

O admin de TOTPDevice declara `fieldsets` como atributo, mas herda de uma classe que **sobrescreve
`get_fieldsets()` e ignora `self.fieldsets`**. Provado por introspecção. Duas consequências:

1. A tela continua em inglês — exatamente o que o docstring do arquivo afirma ter consertado. Ninguém
   percebeu porque a tela é superusuário-only.
2. `OTP_ADMIN_HIDE_SENSITIVE_DATA` é `False` (default da biblioteca; o projeto não o define). Logo o
   **segredo TOTP e o link do QR de enrollment** aparecem na tela de qualquer dispositivo. Quem lê a chave de
   outro usuário gera os códigos dele — **o que anula o step-up de 2FA que os dois WPs querem usar como
   controle de segurança**. Hoje só superusuário chega; mas o hub de configurações **já oferece esse card**,
   então a intenção é abrir.

**Fix — uma linha em `config/settings.py`** (`OTP_ADMIN_HIDE_SENSITIVE_DATA = True`), e apagar o `fieldsets`
inerte (ou sobrescrever `get_fieldsets` de verdade, se a tradução importar).

### P1-5 — O drift do Unfold é invisível ao próprio guardrail

O helper de badge de tabela reconstrói o badge com a tabela de cores copiada — exatamente o anti-padrão que o
módulo de badges canônico documenta como já resolvido — e a base injeta `attrs["style"]`. **Rodei o gate
sobre esses dois arquivos: passa.** O gate lê classe em literal de template; classe em constante Python e
`style` em `attrs` escapam.

**Fix:** o helper delega para o badge canônico (o vocabulário de cor já existe); e uma regra nova no gate
para `attrs["style"]` e para constantes com `bg-`/`text-` alimentando `format_html`.

### P1-6 — Não há system check de 2FA no deploy

`SHOPMAN_ADMIN_REQUIRE_2FA` tem default `False`, e `checks.py` tem 15 erros de deploy e **nenhum** sobre 2FA.
Um deploy de produção sobe com o Admin sem segundo fator e nada acusa. **Fix:** mais um check no arquivo que
já existe, no molde dos que existem — erro se não estiver em DEBUG e o 2FA estiver desligado, e erro se o
host do Admin estiver vazio em produção.

### P2-1 — O hub de configurações oferece cards que respondem 403

O builder não recebe o `request`. Pelo menos cinco cards dão 403 para o Gerente. A primitiva certa já existe e
já é usada pelo menu e pelo dashboard. **Fix:** filtrar por ela; o teste é cópia de um que já existe.

### P2-2 — Segredos de gateway crus; delete não bloqueado no doorman

Os campos de gateway aparecem sem máscara — mas só para Dono e superusuário. Os quatro admins do doorman não
bloqueiam delete — mas nenhum grupo tem permissão em doorman e o delete grava `LogEntry`. Ambos são higiene:
baratos, nada urgente.

### P2-3 — Export de PII sem motivo e sem trilha

Não é escalonamento (reescrito a partir do achado do Agente D). É requisito de LGPD: exportar base de clientes
deve pedir motivo e deixar registro de quem exportou o quê e quando.

### P2-4 — O inventário do gate esquece dois diretórios

Os dois WPs falam em "`packages/*/admin.py`". Faltam `packages/offerman/.../admin/` (onde estão 3 das 20
violações) e `packages/utils/.../admin/`. Se a fase 2 for escrita como `packages/*/shopman/*/admin.py`, esses
dois passam batido.

## RBAC / `setup_groups`

Regra de ouro deste WP: **preferir `permissions=["change"]` a permissão custom sempre que a divisão já
esteja certa.** Metade dos itens não toca o arquivo.

| Ação | Permissão | Grupo | Mexe no `setup_groups`? |
|---|---|---|---|
| Refund | `payman.refund_paymentintent` (custom, migration no payman) | **Dono** | **Sim** — 1 linha |
| Liberar reserva de estoque | `stockman.change_hold` (já existe) | Gerente | **Sim** — hoje ninguém tem `change` em stockman |
| Executar diretiva | `orderman.change_directive` (já existe) | **pergunta 1** | Talvez |
| Import/export de catálogo | reusa `offerman.change_product` via settings | Gerente, Admin de Catálogo | **Não** ✅ |
| Ações de massa do catálogo | `permissions=["change"]`, reusa | idem | **Não** ✅ |
| Export de PII | motivo LGPD, não permissão | — | **Não** ✅ |

⚠️ As mudanças de `setup_groups` vão no **PR único de permissões da onda 4** (WP-00 Bloco D3).

Nota transversal que este WP precisa considerar (WP-00 Bloco D3): o grupo Gerente recebe `_ver("backstage")`
— o app **inteiro**, incluindo models futuros. Enquanto uma ação executar sem declarar permissão, esse
auto-grant amplia o alcance a cada model novo, sem ninguém decidir. O P0-1 é o que fecha essa interação.

## Testes

1. Usuário staff sem permissão de modelo recebe 403 ao **abrir por GET** a URL de cada uma das três ações de
   estado (refund, release hold, execute directive). Hoje executa.
2. As mesmas URLs recusam GET depois do fix (`require_POST` ou dialog action).
3. Um usuário do grupo **Gerente** não executa directive de tópico `payment.refund` — pendente da resposta 1.
4. Usuário do grupo Caixa recebe 403 em `/admin/offerman/product/import/`; Gerente recebe 200.
5. As seis ações de massa do catálogo não aparecem para quem só tem `view_product`, e exigem confirmação.
6. `reset_pin` e `unlock_pin` gravam `LogEntry`; o PIN temporário **não** aparece no cookie `messages`.
7. `get_fieldsets` do TOTPDevice não expõe `key` nem `qrcode_link`.
8. `manage.py check --deploy` reprova quando o 2FA do Admin está desligado fora de DEBUG.
9. O gate canônico acusa `attrs["style"]` e classe tailwind vinda de constante Python (hoje passa).
10. O hub de configurações não oferece card que o usuário não consegue abrir.
11. Substituir os quatro testes de refund que usam superusuário por testes que provam **quem pode**.

## Fase 2 do gate — dimensionada, não estimada

Rodei o gate sobre os nove alvos fora dele:

- **20 violações, 4 arquivos**: doorman 8, orderman 7, offerman/admin/product.py 3, guestman 2.
- Por regra: estilo inline 13, token de design não canônico 4, classe CSS desconhecida 2, shell visual cru 1.
- **Nenhuma exige primitiva nova**: 13 são `<span style="color: x">` → badge canônico; as 7 do orderman são
  classes tailwind à mão em `format_html`.
- **17 das 20 estão em código que nunca renderiza** — desregistrado pelo contrib do próprio pacote. O único
  admin plano vivo é o do orderman.
- Trabalho real se a decisão for migrar: **meio dia, sem waiver nenhum.**

A alternativa mais barata e mais honesta é a pergunta 2.

## Arquivos tocados (para a matriz de colisão)

| Arquivo | Risco | Observação |
|---|---|---|
| **`config/settings.py`** | **ALTO** | 4 linhas (import/export, message storage, OTP). **Agrupar em bloco único com comentário.** Disputado por quase todo WP. |
| `shopman/shop/management/commands/setup_groups.py` | **ALTO** | **PR único de permissões, onda 4.** |
| `packages/orderman/shopman/orderman/admin.py` | **ALTO** | O fix de permissão **e** a fase 2 do gate caem no mesmo arquivo — o único package admin plano vivo. Coordenar. |
| `packages/payman/.../contrib/admin_unfold/admin.py` | MÉDIO | P0-1, P2-2 |
| `packages/stockman/.../contrib/admin_unfold/admin.py` | MÉDIO | P0-1 |
| `packages/offerman/.../contrib/admin_unfold/admin.py` | MÉDIO | P1-2 |
| `shopman/backstage/admin/{operators,accounts}.py` | BAIXO | — |
| `shopman/backstage/projections/settings_hub.py` | BAIXO | — |
| `packages/utils/.../contrib/admin_unfold/{tables,base}.py` | BAIXO | P1-5 |
| `scripts/check_unfold_canonical.py` | BAIXO | regra nova + alvos da fase 2 |
| `shopman/shop/checks.py` | MÉDIO | WP-01 e WP-06 tocam o mesmo arquivo |
| `shopman/backstage/tests/test_admin_action_permissions.py` | — | arquivo novo, sem colisão |

## O que pertence a outro dono

Refund é permissão custom em model de core → migration no payman, com a assinatura do dono. `Hold` e `Quant`
são do stockman: quem decide se o Gerente libera reserva é o dono do estoque. `Directive` é infraestrutura
(ADR-003). Mascaramento e motivo de LGPD são do guestman. `has_delete_permission` é do doorman. As quatro
linhas de settings e o check novo são de infra/deploy. Validação fiscal no import é do fiscalman — **fora**.

## Fora de escopo

Step-up de 2FA como feature (sessão verificada, dossiê de estorno) — é outro tamanho de trabalho, e depende
da pergunta 3. Validação fiscal no import. Reescrita do template de refund. Qualquer coisa que o gate
canônico já cubra hoje.

## Perguntas para o dono do produto

1. **O Gerente pode reexecutar uma diretiva de estorno?** O `setup_groups` diz por escrito que dinheiro é do
   Dono, e a tela de Diretivas dá ao Gerente o botão "Executar" sobre directives de estorno. Ou a tela ganha
   permissão dedicada e o Gerente perde o botão, ou a regra "dinheiro é do Dono" tem uma exceção que ainda não
   está escrita. Não dá para decidir lendo código.
2. **Os `packages/*/admin.py` mortos: migrar ou apagar?** 17 das 20 violações estão em admins que o contrib do
   próprio pacote desregistra. Migrar custa meio dia e mantém arquivos que ninguém usa; **apagar** custa
   menos, respeita "zero resíduos" e faz a fase 2 passar quase de graça — mas remove o fallback "roda sem
   Unfold" que os pacotes anunciam. Como os pacotes são pip-instaláveis, é decisão sobre o pacote, não sobre
   este deployment.
3. **Refund no Admin: permissão dedicada ou tirar a ação da tela?** Se o refund é sempre decisão do Dono,
   `permissions=["refund"]` mais POST resolve com quatro linhas. Se a intenção é o Gerente estornar com
   autorização, isso é feature nova.

## Prompt para agente executor

~~~text
Execute WP-09-agente-c (Admin canonico).

⚠️ As mudancas de setup_groups.py NAO vao neste branch — PR unico de permissoes, onda 4.
⚠️ As 4 linhas de config/settings.py vao num BLOCO CONTIGUO com comentario. O arquivo e
disputado por quase todo WP; bloco contiguo torna o conflito trivial.

Bloqueios: pergunta 1 (Gerente x diretiva de estorno) e pergunta 2 (admins mortos).

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-09-agente-c-admin-canonico.md
- .codex/skills/unfold-admin-canonical/SKILL.md + docs/engineering/unfold_canonical_policy.md
- packages/payman/**/contrib/admin_unfold/admin.py (refund_row, refund_selected)
- packages/stockman/**/contrib/admin_unfold/admin.py (release_hold_row)
- packages/orderman/shopman/orderman/admin.py (execute_row) — unico package admin plano VIVO
- shopman/shop/handlers/payment_refund.py (o handler que o Gerente alcanca)
- shopman/shop/management/commands/setup_groups.py:127-131 (a regra escrita "dinheiro e do Dono")
- shopman/backstage/admin/{operators,accounts}.py
- scripts/check_unfold_canonical.py
- shopman/shop/checks.py

Fases:
1. P0-1: permissions= + has_<x>_permission + require_POST nas TRES acoes. Escreva o
   teste 1 ANTES — ele deve provar que hoje um GET executa.
2. Substituir os 4 testes de refund que usam admin_client por testes de QUEM PODE (teste 11).
3. P1-1 e P1-4: as linhas de settings, em bloco contiguo. Depois P1-3 (MESSAGE_STORAGE
   entra no mesmo bloco).
4. P1-2: permissions=["change"] nas 6 acoes de massa + confirmacao, no padrao do
   tag_selected do guestman.
5. P1-6: check novo em checks.py, no molde do SHOPMAN_E010.
6. P1-5: table_badge delega ao badge canonico + regra nova no gate.
7. P2-1, P2-3, P2-4.
8. Fase 2 do gate: SO depois da resposta 2. Se for "apagar", apagar zera 17 das 20.

Rode `make admin` sem url= antes de abrir o PR.
NAO migre payment_refund.html (ja e canonico). NAO tire o token do agente do DOM.
NAO construa step-up 2FA como feature aqui.
~~~
