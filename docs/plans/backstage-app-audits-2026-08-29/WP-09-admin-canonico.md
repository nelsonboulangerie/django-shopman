# WP-09 - Admin Canonico / Unfold

**Status:** pronto para implementacao  
**Superficie:** Django Admin/Unfold, `admin_console`, package-level ModelAdmins  
**Objetivo:** manter o Admin como superficie canonica de cadastro, configuracao, auditoria e correcao assistida, sem actions perigosas invisiveis, PII exportavel sem controle ou drift de Unfold.

## Fronteira Natural

Admin guarda decisoes de baixo ritmo e alta responsabilidade: quem pode operar, o que a loja vende, regra fiscal, estoque auditavel, custos, aliases, referencias e trilhas. Operacao ao vivo pertence a POS, KDS, Gestor, Producao, Compras, BI e Marketing.

Este WP deve seguir `Unfold Canonical Gate`:

- `docs/engineering/unfold_admin_page_playbook.md`
- `docs/engineering/unfold_canonical_policy.md`
- `docs/reference/unfold_canonical_inventory.md`
- validacao final: `make admin`

## Evidencias Principais

- Gate atual passa: `make admin` reportou `229 passed` e `Admin canonico`.
- Surface registry reconhece Admin e runtimes: `scripts/check_unfold_canonical.py:112`, `:232`.
- `package-admin-unfold` nao cobre plenamente `packages/*/shopman/*/admin.py`: `scripts/check_unfold_canonical.py:253`.
- `table_badge` reconstrui badge por classes: `packages/utils/shopman/utils/contrib/admin_unfold/tables.py:38`, `:47`, `:100`.
- `BaseModelAdmin` injeta `style`: `packages/utils/shopman/utils/contrib/admin_unfold/base.py:77`, `:93`.
- `PaymentIntentAdmin` read-only expoe refund: `packages/payman/shopman/payman/contrib/admin_unfold/admin.py:154`, `:202`, `:212`, `:226`, `:263`.
- Reset PIN mostra temporario em mensagem: `shopman/backstage/admin/operators.py:119`, `:130`.
- Token do POS agent aparece em HTML: `shopman/backstage/admin_console/pos_counter_agent.py:56`.

## Achados Priorizados

### P0 - Refund mutante em Admin descrito como read-only

`PaymentIntentAdmin` bloqueia add/change/delete, mas expoe refund selected/row/detail sem permissao dedicada clara nem step-up.

Proposta:

- Criar permissao dedicada `payman.refund_paymentintent`.
- Remover row action direta de reembolso total.
- Usar dialog action com `BaseDialogForm`: saldo, valor, pedido, gateway, motivo, confirmacao.
- Step-up 2FA recente para refund.
- Gerar `LogEntry`/dossie de acao.

Aceite:

- Usuario view-only nao executa refund.
- Refund sem motivo/step-up nao passa.
- Row action direta deixa de existir.

Estado (19/10/2026, frente 11):

- [x] Permissao dedicada `payman.refund_paymentintent` (`PaymentIntent.Meta.permissions`, migracao `payman.0007_permissao_de_estorno`), exigida nas duas acoes pelo metodo `has_refund_permission` (forma curta `"refund"`; a pontuada faz o check do Unfold consultar o banco e quebrava o contrato de producao). Concedida ao grupo **Dono** no descritor (`config/instances/nelson.json`), nunca ao Gerente: dinheiro e do Dono (`docs/guides/rbac-personas.md`). Paridade em `test_group_permission_parity.py`.
- [x] Usuario view-only nao executa refund: 403 nas duas URLs (`test_payman_admin_refund.py`, `test_admin_state_actions_gate.py`).
- [x] Segunda confirmacao: as duas acoes (`refund` total e `refund-amount`) sao dialog actions oficiais do Unfold com `BaseDialogForm` e marca obrigatoria "Confirmo o estorno, que nao tem desfazer". A pagina propria `payment_refund.html` saiu; o valor e o disponivel vivem no dialogo.
- [x] Estorno em lote (`refund_selected`) removido: acao de lote do Django roda sem dialogo (laudo 01/09, 06-admin P0-1, opcao b).
- [ ] Motivo, step-up 2FA e dossie: nao feitos.
- [x] Estorno do Admin devolve o dinheiro pelo gateway (decisao do dono, 20/10/2026; verify-02-06 §6). As duas acoes chamam `PAYMAN["REFUND_BACKEND"]` (contrato `shopman.payman.protocols.RefundBackend`, lido em `shopman.payman.conf`), apontado para `shopman.shop.adapters.payman_refund.GatewayRefundBackend`, que delega a `services.payment.refund_intent_at_gateway`: o mesmo adapter da rota gravada na cobranca (`_adapter_for_persisted_intent`, Efi ou Stripe) que o estorno do pedido usa. O Core nao importa o shop; sem backend configurado o Admin recusa em vez de gravar so no livro.
  - Parcial: Efi (devolucao Pix com `valor`) e Stripe (`Refund` com `amount`) aceitam; o "Estornar um valor" passa o valor, o total passa o disponivel (capturado menos estornos e chargebacks).
  - Idempotencia: cada dialogo aberto carrega `refund_key` (uuid, campo oculto); a chave `admin-refund:<ref>:<refund_key>` vai ao gateway (chave do `Refund.create` na Stripe; `dev_id` deterministico na Efi) e o Payman deduplica pelo id da devolucao. Duplo clique = uma devolucao.
  - Falha: recusa do gateway volta com a mensagem dele dentro de uma frase em portugues, e nada e gravado; timeout/5xx da Efi (ambiguo) nao grava, abre alerta `payment_refund_failed` critico e manda conferir o painel antes de tentar de novo; dinheiro que saiu sem registro (drift) e dito como tal ("Nao estorne de novo").
  - Cobranca sem gateway (dinheiro, maquininha, externa, Pix/cartao atestado no balcao, em conta) e recusada com o caminho certo (gaveta do PDV; "Estornei na maquininha"): o Admin nao afirma devolucao que nao fez.
  - Auditoria: o motivo da transacao de estorno (imutavel) e "Estorno no Admin por <usuario>", e a acao grava `LogEntry` do Django. O cliente recebe o aviso `payment_refunded` do pedido, como no estorno do pedido.
  - Copy do dialogo: o dinheiro volta ao cliente pelo mesmo meio; Pix em instantes, cartao em alguns dias conforme o banco do cartao.
  - Testes: `shopman/backstage/tests/test_payman_admin_refund.py` (dubles da Stripe e da Efi: sucesso, falha, timeout, duplo clique, parcial, sem gateway, sem backend, auditoria).

### P1 - Gate nao cobre claramente fallback `packages/*/admin.py`

Ha HTML/estilo cru em fallbacks vanilla, enquanto escopo de produto considera Admin canonico.

Proposta:

- Decidir: incluir `packages/*/shopman/*/admin.py` no gate ou declarar explicitamente fora da instalacao canonica.
- Preferencia: gate cobre qualquer Admin carregado em `INSTALLED_APPS`.

Aceite:

- Novo HTML cru em package admin carregado falha ou tem excecao documentada.

### P1 - Helpers Unfold sao contornados

`table_badge` reconstrui badge; textarea recebe `style`; templates usam campo/link manual em pontos isolados.

Proposta:

- `table_badge()` delega para helper canonicamente aceito.
- Remover `style` de widgets ou registrar waiver estreito.
- Migrar `payment_refund.html` para `unfold/helpers/field.html` e dialog action.
- Trocar links crus por `unfold_link()`.

Aceite:

- `make admin` inclui guardrails para `style`, badge manual e field helper.

### P1 - PIN temporario e token de agente expostos sem step-up

Reset de PIN aparece em message storage; token de instalacao do agente aparece no comando.

Proposta:

- PIN temporario em pagina one-time, sem mensagem acumulavel.
- Token do agente revelado apenas apos step-up e com log de visualizacao/copia.

Aceite:

- Message framework nao contem PIN temporario.
- Visualizar token gera trilha.

### P1 - Import/export e PII sem permissao fina

Import de catalogo altera publicacao/venda/preco em massa; cliente exporta PII por action normal.

Proposta:

- Permissao dedicada para import de catalogo, export PII e actions de massa.
- Dry-run com diff humano.
- Mascaramento por padrao e razao LGPD obrigatoria.

Aceite:

- Usuario sem permissao dedicada nao exporta PII nem importa catalogo.

### P2 - Settings hub mostra cards sem filtrar permissao

Cards podem levar a 403, diferente do dashboard/menu.

Proposta:

- Projection recebe `request/user` ou aplica `admin.gates`.
- Card sem acesso aparece apenas quando ha motivo operacional para explicar bloqueio.

Aceite:

- Usuario ve somente portas acessiveis ou bloqueios explicitamente uteis.

### P2 - 2FA Admin default off

2FA existe, mas deploy pode subir sem exigir.

Proposta:

- Check de deploy falha em producao sem `SHOPMAN_ADMIN_REQUIRE_2FA=true` e `SHOPMAN_ADMIN_HOST` configurado.

Aceite:

- `manage.py check --deploy` falha em producao insegura.

## Melhorias UX

1. **RiskActionMixin:** preview, motivo, step-up, permissao dedicada, LogEntry e tabela de impacto.
2. **Radar downstream no ProductAdmin:** fiscal, imagem, preco, estoque, publicacao, ficha tecnica, alergênicos.
3. **Dossie de acao:** refund, merge, revoke, release hold e import com antes/depois.
4. **Modo privacidade de cliente:** listas mascaradas; revelar/exportar exige motivo.
5. **Import de catalogo com diff humano:** “12 precos sobem, 3 despublicam, 2 sem NCM”.
6. **Hub de permissoes por pessoa:** grupos + acoes criticas efetivas.
7. **Terminal/agent health:** token visto, ultimo doctor, ultima impressao, ultima gaveta.

## Testes

- View-only nao executa refund/release/recalculate/export PII.
- Actions criticas exigem step-up.
- `packages/*/admin.py` entra ou sai explicitamente do gate.
- `table_badge` nao contem classes de badge reconstruidas.
- Widgets nao recebem `style`.
- Settings hub nao lista portas sem permissao.
- Import de Product nao publica item fiscalmente incompleto.
- TrustedDevice nao pode ser deletado diretamente.
- `make admin` final obrigatorio.

## Fora De Escopo

Operacao ao vivo de POS/KDS/Pedidos/Producao, fechamento de caixa no balcao, telas runtime headless, dashboards analiticos longos, revisao operacional de campanha quando vive no app dedicado, fluxos que dependem de scanner/impressora/refresh continuo.

## Prompt Para Agente Executor

```text
Execute WP-09 Admin Canonico / Unfold.

Leia obrigatoriamente:
- docs/plans/backstage-app-audits-2026-08-29/WP-09-admin-canonico.md
- .codex/skills/unfold-admin-canonical/SKILL.md
- docs/engineering/unfold_admin_page_playbook.md
- docs/engineering/unfold_canonical_policy.md
- docs/reference/unfold_canonical_inventory.md
- packages/payman/shopman/payman/contrib/admin_unfold/admin.py
- packages/utils/shopman/utils/contrib/admin_unfold/*
- shopman/backstage/admin/operators.py
- shopman/backstage/admin_console/pos_counter_agent.py

Fases:
1. Fechar refund com permissao dedicada, dialog e step-up.
2. Ampliar/explicitar gate para package admins.
3. Remover drift Unfold: badge/style/field/link.
4. Proteger PIN temporario e token do agente.
5. Permissoes finas para import/export/PII.
6. Settings hub permission-aware.

Rode `make admin` ao final. Nao crie console operacional no Admin.
```

