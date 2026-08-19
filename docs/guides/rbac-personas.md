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

Criados automaticamente por `make migrate`. Nenhum usuário é atribuído por default.

| Grupo | Permissões | Persona típica |
|-------|-----------|----------------|
| **Caixa** | `cashman.operate_pos`, `shop.manage_orders` | Atendente de balcão / PDV |
| **Cozinha** | `backstage.operate_kds`, `shop.manage_production` | Cozinheiro / preparador |
| **Gerente** | `shop.manage_orders`, `cashman.operate_pos`, `cashman.adjust_shift`, `cashman.manage_operators`, `backstage.perform_closing`, `backstage.view_production_reports`, `shop.manage_customers` | Gerente de turno |
| **Admin de Catálogo** | `manage_catalog`, `manage_rules` | Responsável por produtos e regras |
| **Rules Managers** | `manage_rules` | Segurança (WP-GAP-06, sem membros por default) |
| **Dono** | `cashman.audit_shift` | Quem vê dinheiro. Portão, não persona — some com "Gerente" quando a pessoa faz as duas coisas |

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

O comando recria/atualiza todos os grupos padrão com as permissões corretas. Seguro para rodar múltiplas vezes.

---

## O elenco de dev/staging (idempotente)

```bash
python manage.py setup_operators --yes
```

Cria/atualiza as pessoas que operam a loja, **ligadas a grupos** — e limpa
qualquer permissão avulsa que alguém tenha dado à mão:

| Usuário | Grupo | Entra com |
|---|---|---|
| `admin` | **Dono** (+ superusuário) | senha `admin` e PIN `1234` |
| `joyce` | **Gerente** | só PIN `1234` |
| `fran` | **Caixa** (loja) | só PIN `1234` |
| `diofer` | **Cozinha** (produção) | só PIN `1234` |

Serve para **consertar acesso no staging sem rodar o `seed`**, que recriaria
catálogo e milhares de pedidos falsos. Não toca em nenhum dado de negócio.

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

- `KDSInstanceAdmin`: visível apenas para usuários com `shop.operate_kds`
- `DayClosingAdmin`: visível apenas para usuários com `shop.perform_closing`
- `ShiftAdmin` (cashman): visível para usuários com `cashman.operate_pos` ou `cashman.audit_shift`
- `RuleConfigAdmin`: visível apenas para usuários com `shop.manage_rules` (WP-GAP-06)

---

## Fora do escopo deste WP

- 2FA / MFA
- Auth provider externo (OAuth, SAML)
- Object-level permissions (django-guardian)
- Multi-tenant (único tenant por instalação)
