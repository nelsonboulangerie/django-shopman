# Auditoria adversarial de go-live — 01/09/2026

Varredura das três superfícies (Admin, backstage, storefront) mais o núcleo de
dinheiro, o seed e os artefatos de deploy. Oito frentes em paralelo, cada uma
lendo o código e afirmando só o que conferiu na fonte.

**Escopo declarado como exceção pelo dono:** Focus NFe segue em homologação, Pix
em mock e Stripe em modo de teste. Tudo o mais foi auditado como se fosse subir
para produção amanhã.

## Os relatórios

| # | Frente | P0 | O que cobre |
|---|---|---|---|
| [01](01-security.md) | Segurança e autenticação | 3 | OTP, PIN, crachá, IDOR, webhooks, rate limit, segredos, BFF |
| [02](02-storefront-contract.md) | Contrato da loja | 5 | 45 rotas × consumidores Nuxt, dialeto de erro, dinheiro fim-a-fim |
| [03](03-backstage-contract.md) | Contrato do operador | 11 | projections, ações, idempotência, SSE, concorrência entre operadores |
| [04](04-storefront-ux.md) | UX e copy do cliente | 5 | 20 telas × estados × personas, acessibilidade, omotenashi |
| [05](05-operator-ux.md) | UX do operador | 12 | 9 superfícies, rede instável, ações destrutivas, contexto físico |
| [06](06-admin.md) | Admin/Unfold | 4 | permissões, ações em massa, integridade, gate canônico |
| [07](07-money-lifecycle.md) | Dinheiro e lifecycle | 0 | pagamento, estoque, holds, directives, livro-caixa, concorrência |
| [08](08-seed.md) | Seed e identidade | 2 | suficiência por tela, realismo, resíduo de teste |
| [09](09-deploy-blueprint.md) | Blueprint de deploy | 0 | topologia, envs, observabilidade |
| [10](10-notifications.md) | Notificações | 1 | remetente, custo de SMS, markup entre canais, omotenashi da mensagem |

## Como ler

Cada relatório separa **CONFIRMADO** de **SUSPEITO**, e termina com uma seção
**Verified-safe** — o que foi conferido e está certo. Essa seção não é enfeite:
ela diz onde NÃO gastar a próxima rodada.

## Correções ao que a casa já acreditava

A auditoria corrigiu cinco pontos de `docs/plans/fallbacks-perigosos-go-live.md`,
que envelheceu:

- **Item 4 (adapter de e-mail)** — já corrigido; `_BACKENDS_INERTES` existe e funciona.
- **Metade runtime do item 18** — as mutações de caixa passaram a ter replay real.
- **Tier 4, E001 `SECRET_KEY` e E002 `ALLOWED_HOSTS`** — o documento afirma que
  há buraco de runtime. **Não há**: `config/settings.py` tem `assert` no import do
  módulo de settings, e não existe `-O`/`PYTHONOPTIMIZE` em lugar nenhum. Fica
  uma fresta só: o assert é `!= ["*"]`, então `"*,api.x"` passa.
- **`webhook_idempotency::_acquire`** — já corrigido. O irmão no Payman, não.

Quem for atacar a lista de fallbacks deve começar por esta seção, senão gasta
uma rodada consertando o que já está de pé.
