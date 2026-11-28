# WP — "Mudar número de telefone" (mantendo a conta) — ENTREGUE

> **Origem (Pablo, 2026-06-20):** na conta, o "Trocar telefone" de então era, na verdade,
> **trocar de conta** (login com outro número = outra identidade). Existiam DUAS features
> distintas: **trocar de conta** (tínhamos) e **mudar número mantendo a conta/histórico**
> (não tínhamos). Decisão: documentar como WP; só fazer após avaliação minuciosa do quanto
> o Core precisaria ser tocado.
>
> **Resolvido em 2026-09-08. O Core não foi tocado — nem o guestman, nem o doorman.**

## O que ficou de pé

- **Loja** (`/conta/seguranca`, seção "Seu número"): informar o número novo → código chega
  **nele** → confirmar. `surfaces/storefront-nuxt/app/pages/conta/seguranca.vue`.
- **API**: `POST /api/v1/account/phone/request/` e `POST /api/v1/account/phone/confirm/`
  (`shopman/storefront/api/account.py`).
- **Serviço**: `request_phone_change` / `confirm_phone_change` / `_set_primary_phone`
  (`shopman/shop/services/account.py`) — gêmeos do `_set_primary_email` do PR #553.
- **Composição do OTP**: `request_contact_verification_code` / `verify_contact_code`
  (`shopman/shop/services/auth.py`).
- **Testes**: `shopman/storefront/tests/api/test_troca_de_telefone.py`.

## As três perguntas que o plano deixou abertas, e as respostas medidas

### 1. "O guestman precisa mudar?" — Não. A API certa já existe.

O plano previa `customer.update(phone=…)` + `ensure_contact_point`. Esse caminho **estoura**:

```
IntegrityError: UNIQUE constraint failed:
customers_contact_point.customer_id, customers_contact_point.type
```

`Customer.save()` chama `_sync_contact_points()`, que cria o ContactPoint novo já
`is_primary=True` e só **depois** demove o antigo — dois primários do mesmo tipo por um
instante, e a constraint `customers_unique_primary_per_type` recusa.

A conclusão de que isso pede conserto no guestman é a leitura errada, e o docstring do
próprio módulo diz por quê: **`Customer.phone` é CACHE, o `ContactPoint` é a fonte da
verdade**. O `_sync_contact_points` é atalho para o PRIMEIRO contato, não API de troca.
Quem troca contato é **`ContactPoint.set_as_primary()`**, que já faz na ordem certa
(demove os outros primários do tipo → promove a si → sincroniza o cache por `.update()`,
sem reentrar no `save()`).

O teste `test_escrever_no_cache_e_salvar_estoura__por_isso_o_caminho_e_o_contact_point`
guarda essa lição no lugar onde ela seria reaprendida.

### 2. "O doorman precisa de um `verify_code` verify-only?" — Não. A finalidade já existe.

O plano tinha razão ao recusar o `verify_for_login` para o número NOVO: ele faz
`resolve_customer` + auto-create, então **pedir** o código nasceria um cadastro-fantasma
no número que o cliente quer adotar.

O que faltava enxergar é que o Core já separa isso por **`purpose`**. O
`VerificationCode.Purpose.VERIFY_CONTACT` existe desde a migração inicial, o
`AuthService.request_code` aceita `purpose` e **não passa por `resolve_customer`** — só
normaliza, checa as portarias e manda. Medido: pedir o código não cria `Customer` nenhum.

Não existe `AuthService.verify_contact()`, e isso não é lacuna a preencher: o que o
`verify_for_login` tem de reaproveitável — achar o código válido, conferir o HMAC, contar
a tentativa, carimbar — **já é API pública do modelo**, e o `VerificationCode.verify()` se
descreve como *"the canonical entry point for code verification"*. `verify_contact_code`
compõe sobre ela, com o mesmo `select_for_update` do Core.

Efeito colateral que vale de graça: o código de troca **não abre sessão** e o código de
login **não troca número**. São dois cofres, e o `purpose` é a parede entre eles.

### 3. "O que fazer com o número antigo?" — Sai do cadastro.

Aqui a decisão diverge do e-mail (#553, onde o antigo sai porque a tela tem um campo só),
e por um motivo mais forte: **o telefone é a identidade** — é por ele que se entra.
`get_by_phone` acha o cliente por **qualquer** ContactPoint de telefone, sem olhar
`is_primary`. Um número velho deixado como secundário continuaria abrindo esta conta por
OTP — e quem muda de número costuma mudar porque perdeu aquele, que a operadora recicla
para um estranho em poucos meses. Guardar o histórico não vale entregar a chave junto.

## Pendências

- **PDV**: ficou de fora. Quem está no balcão não tem como provar posse do número novo (o
  código chega no celular do cliente, não no terminal), e o gesto que o operador realmente
  faz — "este cadastro e aquele são a mesma pessoa" — é **unificação**, que já tem tela
  (`af607e313`). Vale como WP próprio se o balcão pedir.
- **Merge de cadastros** quando o número novo já é de outra conta: hoje a loja recusa e
  oferece "entrar naquela conta". Unificar exige decidir de quem é o histórico — é do
  operador, não do cliente.

## Relacionados

- PR #553 (`_set_primary_email`) — o precedente de forma.
- [[project_o_comprovante_pergunta_antes_de_virar_cadastro]] · `docs/reference/errors.md`.
