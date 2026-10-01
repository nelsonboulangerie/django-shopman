# Escopo do go-live: decisão do dono (01/10/2026)

> **Decisão registrada, não mais proposta.** O nome do arquivo ficou por causa dos
> links antigos (#1336, D28). Ledger: [D-017](../coordination/DECISIONS.md).
> Estado comercial, owners e evidência continuam na
> [matriz canônica](GO-LIVE-READINESS-PLAN.md).
>
> Legenda: **[FATO]** = medido no código, no spec ou em saída de comando, com
> caminho:linha ou PR. **[INFERÊNCIA]** = leitura minha a partir dos fatos.
> **NÃO VERIFICADO** = não medi.

## A decisão em uma frase

A proposta de corte de 01/10 (#1336), que deixava fora entrega própria, WhatsApp
conversacional, catálogos externos e media persistente, foi **RECUSADA** pelo
dono na noite de 01/10/2026. **Ficam fora do go-live só o Marketing e o B.I.**
Entra todo o resto, e duas frentes foram nomeadas explicitamente:

- **Entrega por parceiro** (TaOn sobre a Machine, adaptador
  `shopman/shop/adapters/courier_machine.py`);
- **Concierge**, com a razão do dono: *"a equipe está defasada e a triagem das
  mensagens será muito útil"*. A visão do Concierge está registrada no plano
  canônico, [WHATSAPP-CONCIERGE-PLAN](WHATSAPP-CONCIERGE-PLAN.md#visão-do-dono-01102026).

O que a proposta recusada dizia continua no histórico do git (`dc265f2cd`).

## As 11 frentes depois da decisão

Medido em 01/10/2026 sobre `origin/main` em `1f1ff5afb`.

| # | Frente | No go-live? | Estado medido | Prova |
|---|---|---|---|---|
| 1 | Gestor de pedidos | DENTRO | Código no ar; QA autenticado depois das mudanças de setembro: NÃO VERIFICADO | #1231, #1258, #1328 |
| 2 | Loja online (retirada) | DENTRO | No ar; condição real é o ensaio do Pix real (D-016) | #1329, D-016 |
| 3 | PDV / balcão | DENTRO | No ar; impressão, gaveta e som pendentes de QA física | `.do/app.alpha-subdomains.yaml:36` |
| 4 | Entrega (endereço + entregador parceiro) | **DENTRO (voltou)** | Ver custo abaixo | abaixo |
| 5 | WhatsApp conversacional = **Concierge** | **DENTRO (voltou)** | Ver custo abaixo e o plano canônico | abaixo |
| 6 | Catálogos externos (Google/Meta) | **DENTRO (voltou)** | Ver custo abaixo | abaixo |
| 7 | Media persistente | **DENTRO (voltou)** | Ver custo abaixo | abaixo |
| 8 | Shelf life perecível | ENTREGUE | Janela rígida desligada por padrão (só aviso) | `config/settings.py:1607` |
| 9 | Revisão reversa do PDV | ENTREGUE | Reconciliação concluída em 29/09 | `docs/plans/POS-FASE-C-REVISION.md:7-9` |
| 10 | Surface convergence | ENTREGUE | Convergência completa | `docs/plans/completed/SURFACE-CONVERGENCE-PLAN.md:13-16` |
| 11 | Playwright E2E como gate | ENTREGUE | Check obrigatório de `main` | `.github/required-status-checks.json` |
| · | iFood, fiscal (NFC-e) | DENTRO ("todo o resto") | Custo não medido nesta rodada: NÃO VERIFICADO | matriz, linha "Escopo v1" |
| · | Marketing | **FORA** | Decisão do dono | D-017 |
| · | B.I. | **FORA** | Decisão do dono | D-017 |

## Custo e dependência externa de cada frente que voltou

### 4. Entrega: endereço na loja + entregador parceiro (TaOn/Machine)

**Endereço e taxa na loja.**

- [FATO] Código existe: busca Places com fallback ViaCEP, mapa, pin e taxa por
  faixa de distância (`surfaces/storefront-nuxt/app/components/AddressPicker.vue`,
  `shopman/shop/services/delivery_distance.py`).
- [FATO] As duas chaves do Maps estão declaradas como SECRET no spec
  (`.do/app.alpha-subdomains.yaml:785-790`). Valor e cota no vivo: NÃO VERIFICADO.
- **Custo:** QA de um pedido de entrega de ponta a ponta no ambiente vivo
  (NÃO VERIFICADO até hoje). Nenhum código novo identificado.
- **Dependência externa:** chave do Google Maps com cota no projeto do dono.

**Entregador parceiro (Machine).**

- [FATO] Integração construída em 07/07/2026: despacho por diretiva, status por
  webhook e por polling, ações do operador no Gestor
  (`docs/plans/DELIVERY-EXTERNAL-LOGISTICS-PLAN.md:15`, `:20-50`).
- [FATO] O spec versionado não tem **nenhuma** variável da Machine:
  `grep -c MACHINE .do/app.alpha-subdomains.yaml` devolve `0`; também falta
  `SHOPMAN_COURIER_ADAPTER`. Sem credencial com o adaptador ligado, o deploy-check
  `SHOPMAN_E011` bloqueia (`shopman/shop/checks.py:380`).
- [FATO] O endereço padrão da API no código é o de produção
  (`config/settings.py:925`, `https://api.taximachine.com.br/api/integracao`). A
  homologação é `https://api-vendas.taximachine.com.br/api/integracao` (informação
  do dono). **Outra sessão corrige os endereços do adaptador em PR próprio**; este
  PR não toca o código do courier.
- **Custo (trabalho restante):** os quatro passos de
  `DELIVERY-EXTERNAL-LOGISTICS-PLAN.md:51-61`: (1) credenciais no painel da DO;
  (2) ligar `SHOPMAN_COURIER_ADAPTER` e `fulfillment.courier="auto"` no canal de
  entrega; (3) registrar o webhook (`manage.py machine_register_webhook`, com
  `MACHINE_WEBHOOK_TOKEN`) e observar o primeiro evento real, cujo payload não é
  documentado; (4) confirmar com a central a forma de pagamento
  (`MACHINE_FORMA_PAGAMENTO`, default `F`) e o motivo de cancelamento
  (`MACHINE_CANCEL_REASON_ID`). Mais a correção de endereços da outra sessão e um
  ensaio em homologação antes de apontar para produção.
- **Dependência externa:** API Key do painel da Machine + usuário Gestor (hoje a
  Joyce) com permissão **API Corrida/Entrega** (`MACHINE_API_USER`,
  `MACHINE_API_PASSWORD`, `MACHINE_API_KEY`, `config/settings.py:927-929`).
  **Ressalva:** se a Joyce trocar a senha, a entrega para. Um usuário dedicado à
  integração evitaria isso. [INFERÊNCIA] Como o adaptador autentica por HTTP Basic
  com esse usuário (`courier_machine.py:10-11`), a troca de senha derruba o
  despacho sem aviso prévio; o primeiro sinal seria o erro 4xx na diretiva.

### 5. Concierge (WhatsApp conversacional)

Detalhe item a item em
[WHATSAPP-CONCIERGE-PLAN, "Distância até a visão"](WHATSAPP-CONCIERGE-PLAN.md#distância-até-a-visão-medida-em-01102026).
Resumo:

- [FATO] Código no ar e **desligado**: `SHOPMAN_CONCIERGE_ENABLED='false'`
  (`.do/app.alpha-subdomains.yaml:550-553`), `CONCIERGE_READ_ONLY='true'`
  (`:568-571`) e `CONCIERGE_OPERATION_MODE=observe` (`:617-620`), que guarda as
  mensagens sem responder.
- [FATO] FAQ, horários e catálogo respondem pela ferramenta `search_storefront`
  (`shopman/storefront/concierge/tools.py:449`). Montar e fechar pedido existe no
  código (`set_item`, `set_fulfillment`, `review_order`, `place_order`), mas
  **não roda pelo ManyChat**: sem identificador de mensagem, todo turno fica só
  leitura por construção (`service.py:835-839`; guia
  `docs/guides/whatsapp-concierge.md:118-141`).
- [FATO] A triagem como o dono descreveu não existe. Há um classificador de
  regex com quatro causas que só decide o handoff
  (`shopman/storefront/concierge/handoff.py:16-49`) e um piloto que mede
  classificadores sobre doze intenções, sem rotear nada
  (`intent_pilot.py:61-91`). A proposta de triagem é a D32.
- **Custo (trabalho restante, nosso):** triagem (classificar toda mensagem,
  resumo para a equipe, onde a equipe vê); identidade do cliente ligada
  (`CONCIERGE_IDENTITY_LINK_ENABLED`) para consultar pedido; retorno da equipe ao
  bot (`CONCIERGE_HUMAN_RETURN_ENABLED`); e a decisão de como fechar pedido sem
  identificador de mensagem.
- **Dependência externa:** ManyChat (flow com External Request em toda mensagem,
  não só no `#c`; campo `concierge_handoff`; continuidade entre mensagens ainda
  a confirmar no grafo do flow, guia `:112-116`); Meta (templates aprovados para
  qualquer aviso fora da janela de 24 horas, 24 a 48 horas por rodada,
  `docs/reference/whatsapp-templates-meta.md:16-18`); chave da Anthropic
  (`AI_ASSIST_API_KEY`, `.do/app.alpha-subdomains.yaml:545-547`, valor no vivo
  NÃO VERIFICADO).

### 6. Catálogos externos (Google Merchant, Meta, WhatsApp Catalog)

- [FATO] Feed pull Google/Meta e push Meta implementados; push Meta só com
  `META_CATALOG_PROJECTION=1` (`docs/plans/CATALOG-SYNC-EXTERNO-PLAN.md:7-9`;
  #1255, #957). A variável não está no spec versionado
  (`grep META_CATALOG .do/app.alpha-subdomains.yaml` sem resultado).
- **Custo (nosso):** declarar a variável no spec e conferir o feed com o catálogo
  vivo. Nenhum código novo identificado.
- **Dependência externa:** homologação do catálogo na Meta, vínculo do catálogo
  ao número do WhatsApp, cadastro e verificação no Google Merchant Center, todos
  nas contas do dono.

### 7. Media persistente (arquivos enviados pelo Admin)

- [FATO] Mudou desde a proposta: o código do Cloudflare R2 está pronto e
  desligado (#1337, D-010). `STORAGES["default"]` vem de `media_storage()`
  (`config/settings.py:577-585`) e só usa o R2 com `SHOPMAN_MEDIA_STORAGE=r2`.
  Nenhuma variável `R2_*` no spec versionado.
- **Custo (nosso):** ligar `SHOPMAN_MEDIA_STORAGE=r2` e conferir um upload que
  sobreviva a um deploy.
- **Dependência externa:** o dono cria o bucket privado e o token R2 e cola as
  quatro chaves como segredo no painel da DO (D30,
  `docs/runbooks/r2-passo-a-passo-do-dono.md`).

## O que a decisão NÃO resolve

Seguem abertos na matriz, com ou sem escopo: perfil comercial do runtime, drift
do spec vivo, credenciais externas (Efí, Stripe, Focus), ensaio de restore pelo
fork (D29), `production-readiness` no ambiente alvo, QA física,
impressão/gaveta/som e o GO/NO-GO assinado.

## NÃO VERIFICADO

- Valores de env no app vivo da DO (Concierge, Maps, Machine,
  `META_CATALOG_PROJECTION`, R2): só o spec versionado foi lido.
- QA autenticado do Gestor depois das mudanças de setembro.
- Pedido com entrega de ponta a ponta no ambiente vivo; corrida real na
  homologação da Machine.
- Custo restante de iFood e fiscal (entram por "todo o resto"; não medidos aqui).
