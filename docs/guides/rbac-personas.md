# RBAC por Persona — Guia Operacional

> Introduzido em WP-GAP-13. Baseado no padrão estabelecido pelo WP-GAP-06 (`shop.manage_rules`).

## Princípio: menor privilégio por default

Nenhum usuário recebe permissões por padrão ao ser criado. O dono atribui deliberadamente cada operador ao grupo correto.

Superuser (`is_superuser=True`) passa em tudo — sem necessidade de grupo.

Regularização financeira manual não faz parte de `shop.manage_orders`. Se
necessária, deve viver em fluxo administrativo/financeiro próprio, com motivo,
evidência e auditoria, sem confirmar pedido automaticamente.

---

## Permissões disponíveis

| Permission | Modelo | Concede acesso a | Surface |
|------------|--------|-----------------|---------|
| `shop.manage_orders` | `Shop` | Confirmar, rejeitar, avançar, cancelar pedidos; adicionar notas internas | Gestor (orders-nuxt, `gestor.`) via `api/v1/backstage/orders/*` |
| `backstage.operate_kds` | `KDSTicket` | Check item, marcar ticket done, ações de expedição | KDS (kds-nuxt, `kds.`) via `api/v1/backstage/kds/*` |
| `cashman.operate_pos` | `cashman.Shift` | Abrir/fechar caixa, sangria, lookup de cliente, fechar venda | PDV (pos-nuxt, `pos.`) — antesala `/session` + venda |
| `cashman.audit_shift` | `cashman.Shift` | **Ver a apuração**: esperado, contado e diferença dos turnos; faturamento do dia; conferir comprovante | Admin (Turnos de caixa) **e** PDV `/session/report` |
| `cashman.adjust_shift` | `cashman.Shift` | Segunda assinatura das exceções do caixa: sangria, troco atendido, correção da contagem, desconto acima do teto (PIN de gerente) | PDV (diálogo de gerente) |
| `cashman.manage_operators` | `cashman.Shift` | Resetar PIN, provisionar operador, crachá | Admin (Operadores) |
| `shop.manage_production` | `Shop` | Criar WorkOrders, planejar e avançar produção | Produção (production-nuxt, `prod.`) via `api/v1/backstage/production/*` |
| `backstage.perform_closing` | `DayClosing` | Executar fechamento do dia, registrar perdas, mover sobras p/ "Ontem" | PDV `/session/closing` (antesala) via `api/v1/backstage/closing/` |
| `shop.manage_catalog` | `Shop` | Criar/editar Product, Listing, Collection | Admin |
| `shop.manage_customers` | `Shop` | Criar/editar Customer, grupos, loyalty | Admin |
| `shop.manage_rules` | `RuleConfig` | Criar/editar regras de pricing e validação | Admin |
| `backstage.view_production_reports` | `DayClosing` | Relatórios de produção | Produção `/reports` via `api/v1/backstage/production/reports|management|weighing/blind-map/` |

---

## Grupos padrão

Criados por `python manage.py setup_groups`. Nenhum usuário é atribuído por default.

| Grupo | Permissões de AÇÃO | Persona típica |
|-------|-----------|----------------|
| **Caixa** | `cashman.operate_pos`, `shop.manage_orders` | Atendente de balcão / PDV |
| **Cozinha** | `backstage.operate_kds`, `shop.manage_production` | Cozinheiro / preparador |
| **Gerente** | `shop.manage_orders`, `shop.manage_catalog`, `shop.manage_customers`, `shop.manage_campaigns`, `cashman.operate_pos`, `cashman.adjust_shift`, `cashman.manage_operators`, `backstage.perform_closing`, `backstage.view_bi` | Gerente de turno |
| **Admin de Catálogo** | `manage_catalog`, `manage_rules` | Responsável por produtos e regras |
| **Rules Managers** | `manage_rules` | Segurança (WP-GAP-06, sem membros por default) |
| **Dono** | `cashman.audit_shift` | Quem vê dinheiro. Portão, não persona — some com "Gerente" quando a pessoa faz as duas coisas |

### Ação é uma permissão; ABRIR A TELA é outra

As permissões acima dizem o que a pessoa pode **fazer**. Quem decide se uma tela
do Admin **abre** é o Django: `/admin/offerman/product/` pede
`offerman.view_product`, e mais nada. Por muito tempo nenhum grupo concedia esses
`view_*` — o resultado é que o Admin era, na prática, **só-superusuário**: o menu
oferecia 26 telas à Fran e as 26 respondiam 403, e `manage_rules` não abria nem a
lista de regras que ela governa.

Desde 22/08/2026 o `setup_groups` concede os dois lados juntos, e o menu e os
cards do dashboard perguntam à própria tela antes de oferecê-la
(`shopman/backstage/admin/gates.py`). O que cada persona alcança na retaguarda:

| Grupo | Lê no Admin | Escreve no Admin |
|---|---|---|
| **Caixa** | nada — ela opera no PDV, a retaguarda não é ferramenta dela | — |
| **Cozinha** | fichas técnicas, ordens, insumos, fornecedores, estoque | — (mexer acontece no app de Produção) |
| **Gerente** | catálogo, clientes, produção, estoque, pedidos, B.I. e a configuração inteira | catálogo, clientes, promoções, cupons, textos da interface, terminais |
| **Admin de Catálogo** | catálogo, regras, promoções, cupons | catálogo e regras |
| **Rules Managers** | regras de preço | regras de preço |
| **Dono** | turnos de caixa (apuração), cobranças, comprovantes | — |

⚠️ **Dinheiro é do Dono, e o Gerente não vê** — nem a apuração do turno, nem as
cobranças (Pix/cartão). É a mesma régua do fechamento cego, explicada abaixo.

---

### O gerente opera, o dono audita

O **Gerente** não tem `cashman.audit_shift`, e isso não é esquecimento.

Ele abre e fecha turno, autoriza sangria com o PIN, resolve exceção — e conta às
cegas, como todo mundo. **Quem sabe o esperado não conta às cegas**: confere um
gabarito, e o fechamento cego perde a única coisa que existe para pegar. O mesmo
vale para o faturamento do dia, que é questão financeira e não operação.

Quem audita **e** opera entra em **Dono** e **Gerente**. Permissões somam, e
separá-las deixa a pergunta "quem vê dinheiro?" com uma resposta só, legível numa
tela do Admin.

O que o balcão **não** perde: a antesala segue mostrando a contagem de vendas do
próprio turno. Contagem é operação; valor é apuração.

## Como adicionar um novo operador

```bash
# 1. Crie o usuário via admin Django
#    Admin → Auth → Users → Adicionar usuário
#    Marque "Staff status" = ✓

# 2. Atribua ao grupo correto
#    Na aba "Groups" do usuário, adicione "Caixa", "Cozinha", etc.
```

Ou via shell:

```python
from django.contrib.auth.models import User, Group

u = User.objects.create_user("novo-operador", password="...", is_staff=True)
g = Group.objects.get(name="Caixa")
u.groups.add(g)
```

---

## Como criar um grupo customizado

```python
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

# Obter permissões desejadas
ct_shop = ContentType.objects.get(app_label="shop", model="shop")
perm_orders = Permission.objects.get(content_type=ct_shop, codename="manage_orders")
perm_reports = Permission.objects.get(content_type=ct_shop, codename="view_reports")

# Criar grupo
g, _ = Group.objects.get_or_create(name="Supervisor")
g.permissions.add(perm_orders, perm_reports)
```

---

## Reatribuir grupos (idempotente)

```bash
python manage.py setup_groups
```

O comando recria/atualiza todos os grupos padrão com as permissões corretas. Seguro para
rodar múltiplas vezes — o release job do deploy o chama logo depois do `migrate`.

Ele é a **fonte da verdade** dos seis grupos padrão: usa `permissions.set(...)`, então
o que sai da lista em `setup_groups.py` sai do banco no deploy seguinte, e as revogações
aparecem no log da forma `Caixa: atualizado (2 permissões) — revogadas: shop.manage_catalog`.

⚠️ Consequência prática: **permissão marcada à mão** na tela de Grupos do Admin, num
desses seis, dura até o próximo deploy. Para valer, escreva-a em `setup_groups.py`. Grupo
customizado (criado fora dessa lista, como o "Supervisor" do exemplo acima) o comando
não toca.

---

## O elenco de dev/staging (idempotente)

```bash
python manage.py setup_operators --yes
```

Cria/atualiza as pessoas que operam a loja, **ligadas a grupos** — e limpa
qualquer permissão avulsa que alguém tenha dado à mão:

| Usuário | Grupo | Entra com |
|---|---|---|
| `admin` | **Dono** (+ superusuário) | senha `admin`, PIN `1234`, crachá emitido |
| `joyce` | **Gerente** | só PIN `1234` |
| `fran` | **Caixa** (loja) | PIN `1234`, crachá emitido |
| `diofer` | **Cozinha** (produção) | PIN `1234`, crachá emitido |

Serve para **consertar acesso no staging sem rodar o `seed`**, que recriaria
catálogo e milhares de pedidos falsos. Não toca em nenhum dado de negócio.

### O crachá NÃO se testa digitando

O leitor é um teclado: ele "digita" o token depressa e termina com Enter. A tela
só aceita **12 hexadecimais com menos de 120ms entre teclas**. As duas regras
existem para que teclas soltas ao longo do turno não se somem num token falso.

⚠️ **Consequência: não dá para testar digitando nem colando.** Dedo humano não
chega a 120ms por tecla, e colar (`Ctrl+V`) não gera evento de tecla nenhum —
o leitor não vê nada. Quem tentar vai concluir que está quebrado.

### Por que 12 caracteres, e não mais

O comprimento do crachá é o mesmo orçamento que a **largura da barra impressa**, e
quem manda nesse orçamento é a etiqueta.

Com 24 caracteres, o Code 128 só cabia num crachá tamanho cartão (85,6mm) usando
barras de **0,25mm** — o piso do padrão. Numa impressora de 300dpi um ponto mede
0,0847mm, então 0,25mm são **2,95 pontos**: cada barra é arredondada para 3 ou 2
conforme onde cai na grade. O Code 128 é lido pela RAZÃO entre barra e espaço, e
esse arredondamento desregula a razão. O símbolo fica perfeito no arquivo e
ilegível no papel. Foi exatamente o que aconteceu.

Com 12 caracteres a barra sobe para **0,4233mm**, que são 5 pontos exatos a
300dpi e 10 a 600dpi, numa largura de 79,2mm — praticamente a mesma etiqueta de
antes, com barra 70% mais grossa.

⚠️ **"Formato mais simples" não resolveria.** Code 39 é menos denso que Code 128:
o mesmo dado sairia num símbolo ainda mais largo, forçando barra ainda mais fina.
O caminho é encurtar o dado, não trocar a simbologia.

O que se perde: o token cai de 96 para 48 bits. São 281 trilhões de combinações
contra um alvo que só vale dentro da loja, é comparado por digest e morre no
instante em que alguém emite outro. Não há aqui força bruta que justifique gastar
largura de barra.

**Como testar de verdade:** imprima o crachá em *Operadores → Crachá do
operador* e passe no leitor. O token de dev é derivado do username, então é
estável: o crachá impresso ontem continua valendo depois de rodar o comando de
novo.

O comando imprime os tokens na saída, para conferência e para gerar o código de
barras.

### Herança da identidade antiga

O comando **absorve** contas anteriores: `marina` → `joyce`, `ana` → `fran`,
`joao` → `diofer`. Todo o histórico (turnos, livro-caixa, movimentos de estoque,
fechamentos) é reatribuído à pessoa nova e a conta antiga é apagada.

Apagar direto jogaria fora o passado; manter as duas deixaria uma conta ativa
sem grupo, que é acesso que ninguém explica. ⚠️ Isso vale para dev/staging: em
produção, identidade que operou o caixa **não** se reescreve — o caminho lá é
desativar a conta, não fundi-la.

O `--yes` é obrigatório porque a senha e o PIN são de desenvolvimento: é uma
frase que alguém digita de propósito, não algo que um job de release dispare
sozinho.

⚠️ **Permissão avulsa é apagada.** O grupo passa a ser a única resposta para
"por que essa pessoa consegue fazer isso?". Antes o `seed` dava sete permissões
copiadas à mão para a gerente, que imitavam o "Gerente" sem serem ele — a tela
de Grupos do Admin mostrava gente sem grupo nenhum operando o sistema inteiro.

---

## Comportamento de enforcement

| Cenário | Resposta |
|---------|----------|
| Não autenticado → URL protegida | Redirect `/admin/login/?next=<url>` |
| Staff sem perm → URL protegida | HTTP 403 "Você não tem permissão para esta ação." |
| Staff com perm → URL protegida | HTTP 200 (acesso concedido) |
| Superuser → qualquer URL | HTTP 200 (acesso total) |

### Admin (Unfold)

Regra geral: **ver** é a permissão do Django (`view_<model>`); **escrever** é a
permissão custom quando existe uma. As exceções, que gateiam até o ver:

- `KDSInstanceAdmin`: visível apenas para usuários com `backstage.operate_kds`
- `DayClosingAdmin`: visível apenas para usuários com `backstage.perform_closing`
- `POSTabAdmin`: visível apenas para usuários com `cashman.operate_pos`
- `ShiftAdmin` (cashman): visível apenas para usuários com `cashman.audit_shift` — **não** `operate_pos`: a tela mostra esperado, contado e diferença, que é o gabarito da contagem cega
- Operadores (`admin_console`): `cashman.manage_operators`
- `RuleConfigAdmin`: editar exige `shop.manage_rules` (WP-GAP-06); abrir a lista exige `shop.view_ruleconfig`

Menu e dashboard não repetem nenhuma dessas regras: perguntam à própria tela
(`admin/gates.py`), e um link só aparece se a porta abriria. O contrato está em
`shopman/backstage/tests/test_admin_reachability.py`, que pede cada link
oferecido e exige 200.

---

## Fora do escopo deste WP

- 2FA / MFA
- Auth provider externo (OAuth, SAML)
- Object-level permissions (django-guardian)
- Multi-tenant (único tenant por instalação)
