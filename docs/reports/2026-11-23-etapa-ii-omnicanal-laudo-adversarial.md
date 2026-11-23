# Excelência Comercial Omnicanal, Etapa II: laudo adversarial

> **Data:** 23/11/2026. **Base:** `origin/main` `0644992aa`. **Estado:** PROPOSTA PARA APROVAÇÃO. Nenhum código, configuração, ADR ou documento existente foi alterado.
> **Compromisso:** `DEV-2026-085`.
> **Documento irmão (especificação e plano para o agente de implementação):** [2026-11-23-etapa-ii-omnicanal-espec-e-plano.md](2026-11-23-etapa-ii-omnicanal-espec-e-plano.md).
> **Relatórios de origem (preservados, não editados, lidos na íntegra):** branch `docs/storefront-excellence-omnicanal-20261123`, commit `dbf912118`:
> - Relatório I: `docs/plans/STOREFRONT-EXCELENCIA-AB-CONTINUIDADE-OMNICANAL-2026-11-23.md`
> - Relatório II: `docs/reports/2026-11-23-continuidade-comercial-omnicanal-expansao.md`

## Como ler as evidências

Cada achado traz o grau de prova:

- **[V]** verificado por mim no código, com `path:linha`;
- **[A]** lido no código por um agente de investigação desta rodada e não reverificado linha a linha por mim (as afirmações de maior gravidade foram todas reverificadas e estão marcadas [V]);
- **[M]** medido ao vivo na loja (`www.nelsonboulangerie.com.br`, ambiente de testes, 23/11 entre 22h e 23h, loja fechada, visitante anônimo em 375 px no navegador embutido; um olhar logado no Chrome do dono em desktop, só leitura, nenhum pedido criado);
- **[H]** hipótese ou inferência ainda não demonstrada.

Limites declarados: não houve WhatsApp real, pagamento real, leitor de tela real, dispositivo físico, nem pedido criado. A navegação foi noturna, com a loja fechada; jornadas de compra com itens disponíveis não foram percorridas ao vivo.

---

## 1. Diagnóstico executivo

### 1.1 Situação

O Shopman já tem quase tudo o que os dois relatórios propõem construir. O que falta não é arquitetura nova: são **quatro costuras** mal fechadas e **um punhado de defeitos de verdade e de segurança** que a navegação e a leitura revelaram.

O que já existe e funciona, e que os relatórios ou não citaram ou trataram como hipótese:

1. **A sessão comercial pré-pedido tem dono e é robusta.** `Orderman.Session` é única por `(channel_ref, session_key)` e por handle aberto no canal, tem `rev`, `edit_policy`, `commit_token`, commit idempotente por `IdempotencyKey` e selo `CommitSeal(expected_revision, expected_total_q)` que reprova termos defasados [A: `packages/orderman/shopman/orderman/models/session.py:209-216`, `services/commit.py:51-60,84-89,354-364,369,446`].
2. **A "intenção comercial" já existe duas vezes, com o mesmo significado:** o orçamento vigente da Nice (`Conversation.quote`, token = hash de sessão, `rev`, linhas, recebimento e pagamento) [A: `shopman/storefront/concierge/tools.py:372-397`] e o par `expected_revision`/`expected_total_q` exigido pelo checkout web [A: `shopman/storefront/api/serializers.py:83-84`]. São o mesmo conceito, "termos revisados", em duas formas. O próprio `Channel.CommercePolicy` reservou e recusou o valor `intent` até haver implementação [V: `shopman/shop/models/channel.py:27-38`].
3. **A transferência de sacola entre canais já existe**, como cópia reconciliada: `send_web_link(destination="checkout")` → `_copy_cart_to_web` copia as linhas para uma sessão web, re-reserva pelo serviço de carrinho, abandona a origem e recusa se o total mudou ou se já há sacola web aberta [A: `tools.py:1843-1976`]. Está **desligada** por padrão (`CONCIERGE_TRANSFER_ENABLED=False`) [V: `config/settings.py:1674`] e nenhuma intenção viva a chama [A].
4. **O pedido já é canal-agnóstico.** Instrução de pagamento em `order.data["payment"]`, projetada por `shop/projections/order_tracking.py`; Storefront e Nice leem a mesma projeção [A: `order_tracking.py:206-240`; `tools.py:1719-1736,1764-1772`].
5. **Pagamento é íntegro por construção:** intent só existe depois do commit, chave determinística, Pix pago após cancelamento é estornado automaticamente com alerta, Stripe anula autorização tardia [A: `payman/models/intent.py:123,161-170`; `shop/services/payment.py:3482-3514`; `pix_confirmation.py:298-401`; `webhooks/stripe.py:150-175`].
6. **A Nice já conduz quase toda a compra na conversa:** descoberta, sacola, recebimento e horário, revisão, confirmação por código (ADR-050), pedido idempotente, status, autocancelamento e acréscimo [A: inventário em §2.4].
7. **Há uma metodologia de rollout candidata/baseline já escrita e revisada adversarialmente:** o perfil Continuum 0.2 define atribuição *sticky* server-side, kill switch que incrementa geração, sete guardrails quantitativos, amostra mínima e "telemetria ausente é inconclusiva e não promove" [V: `docs/specs/continuum-0.2.md:138,1835-1880`]. Nenhum dos relatórios a citou.
8. **A decisão sobre seleção de versões já foi tomada:** WP-RELEASE-01 D5 e ADR-043 fixam seleção server-side, aderente à sessão, coortes nomeadas, kill switch e configuração em `RuleConfig`, proibindo cookie/query como controle e um segundo control plane [V: `docs/plans/WP-RELEASE-01-versoes-de-apps-sem-quebra.md:140-163,217-218`].

### 1.2 Principais descobertas novas (não presentes nos relatórios)

| # | Achado | Grau | Severidade |
|---|---|---|---|
| S1 | Todo link de aviso de pedido (acompanhar, pagar, repetir) nasce com `source="manychat"` e, ao ser trocado, dá **identidade forte e confiança no dispositivo por 180 dias**. O próprio código diz que link que a casa empurra não deve confiar, "mensagem se encaminha". Um aviso encaminhado e aberto em até 5 min entrega a conta. | [V] `shopman/shop/services/access_urls.py:73-97`; `notification.py:838-840`; `shopman/storefront/api/auth.py:332-349` | **P0 segurança** |
| S2 | Acesso a pedido por **telefone** vale mesmo quando o pedido tem `customer_ref` de outra pessoa. Novo titular de um número reciclado vê pedidos e dados do anterior. | [V] `shopman/shop/services/customer_orders.py:100-125` | **P1 privacidade** |
| S3 | Número reciclado herda a conta: o identificador ManyChat sobrevive à troca de telefone e reencontra o cliente antigo; não há frescor de verificação. | [V] `guestman/contrib/identifiers/signals.py:32-36`; `contrib/manychat/service.py:118-126` | P1 (raro, grave) |
| S4 | Contato **não verificado** (ex.: telefone digitado no balcão) abre a conta a quem passar OTP naquele número. | [A] `guestman/adapters/auth.py:28-53` | P2 |
| S5 | Todo link mágico é sessão completa; audiência nunca é aplicada; API S2S aceita TTL ilimitado. | [A] `doorman/gates.py:61`; `shop/services/access.py:23-27`; `doorman/services/access_link.py:109` | P2 |
| T1 | Edição de copy no Admin **não chega à loja até o próximo deploy**: o cache de copy é global de processo, sem TTL, invalidado só no processo que salvou; o Admin roda em `web-operator` e a API da loja em `web-storefront`. | [V] `shopman/shop/omotenashi/copy.py:2237-2267`; `.do/app.subdomains.yaml:124-152` | **P1** (bloqueia qualquer isolamento de copy por variante) |
| T2 | Na Nice, "Copiar código Pix" aponta para a página web do pedido: a ação `copy_pix` não tem `href` e a Nice cai no link de acompanhamento. O rótulo promete o código e entrega um link. | [V] `shopman/shop/projections/order_tracking.py:1215-1224`; `concierge/tools.py:2176-2186` | **P1** (quebra a jornada Nice-only) |
| T3 | No caminho do motor do framework, o código Pix do pedido recém-feito é **descartado**: só `framework.text` sai. Latente enquanto `conversational_live_order=False`; morde no dia em que ligar. | [V] `concierge/service.py:1078`; `extra_replies` só no caminho legado | **P1 latente** |
| T4 | Avisos proativos (pago, aceito, pronto, saiu) saem por um pipeline à parte e **não entram na transcrição**: a Nice não sabe o que o cliente já recebeu. | [A] `shop/services/notification.py`, `handlers/notification.py` (sem referência a `Conversation`) | P1 continuidade |
| T5 | Links de aviso valem **5 min** (TTL padrão de troca, sem override); o cliente que lê "pedido pronto" uma hora depois cai numa página "o link pode ter expirado" **sem dizer qual pedido**. | [V] `doorman/conf.py:24`; `doorman/services/access_link.py:104-107`; `surfaces/storefront-nuxt/app/pages/a.vue:141` | P1 UX |
| U1 | Às 22h, com a loja fechada, **0 de 31** itens podem ir à sacola, mas o topo diz "Você já pode finalizar o pedido" e a sacola diz "Você pode encomendar para o próximo dia". A frase é constante no código, sem condição. | [M] + [V] `surfaces/storefront-nuxt/app/presentation/home.ts:5-9` | **P1 verdade** |
| U2 | O rótulo decisivo "Indisponível", a descrição do produto e os rótulos da barra inferior saem em 12 px. | [M] | P2 a11y |
| U3 | A home lista 34 perguntas frequentes, com duplicata exata ("Posso encomendar para outro dia?") e pares quase iguais. | [M] | P2 |
| U4 | "Respondemos rápido, de pessoa para pessoa" no mesmo número que atende o login automático e onde a Nice responde. | [V] `shopman/shop/omotenashi/copy.py:409-414` | P2 verdade [H: depende de a Nice estar viva no número] |
| U5 | Cache público de `home/shell/catalog/products` é por URL e o Cloudflare ignora `Vary`: qualquer variante por sessão vazaria entre visitantes anônimos. | [A] `shopman/storefront/api/public_cache.py:3-5,31-33` | restrição de desenho |
| U6 | A política de privacidade promete três cookies, todos necessários. Um cookie de atribuição A/B novo exigiria mudar a promessa. | [A] `surfaces/storefront-nuxt/app/pages/privacidade.vue:183-185` | restrição de desenho |

### 1.3 Recomendação arquitetural

**Nenhum domínio novo, nenhuma entidade "Intenção Comercial", nenhum Omniman, nenhum control plane novo de experimentação.** A menor arquitetura que preserva a jornada entre canais é a que existe, com uma regra de ouro e quatro costuras:

> **Regra de ouro: antes do pedido, a sacola se TRANSFERE (uma só viva por vez); depois do pedido, todos os canais LEEM o mesmo pedido.**

1. **Pré-pedido = transferência reconciliada, nunca sessão compartilhada.** Extrair o que já existe (`_copy_cart_to_web`, `_adopt_carried_cart`) para um serviço único do orquestrador, simétrico (web→chat também), idempotente e com recibo. A origem é abandonada: dois canais nunca editam a mesma sacola, e o conflito do cenário J9 deixa de ser possível por construção.
2. **Pós-pedido = referência ao `Order`.** A Nice precisa entregar Pix e cartão como ações de conversa de primeira classe e saber o que os avisos já disseram (gravar os avisos na transcrição).
3. **Identidade = Guestman (posse) + Doorman (sessão e força) + vínculo da conversa (garantia do transporte).** Fechar S1 a S5. O Guestman ganha só o que é identidade (frescor da verificação, evento de número reatribuído), não continuidade comercial.
4. **Experimentação = executar o R4 do WP-RELEASE-01** (o resolvedor server-side já decidido), com o Storefront como primeiro consumidor, configuração em `RuleConfig`, atribuição guardada na sessão de servidor que já existe (nenhum cookie novo) e metodologia de promoção herdada do Continuum. Copy por variante só quando uma mudança concreta exigir, e depois de corrigir T1.

---

## 2. Análise adversarial do código

### 2.1 Orderman: o estado pré-pedido

| Pergunta | Resposta | Evidência |
|---|---|---|
| A sessão é por canal? | Sim. Única por `(channel_ref, session_key)`; uma aberta por handle **dentro do canal**. O mesmo telefone pode ter uma sacola web e uma de WhatsApp ao mesmo tempo. | [A] `session.py:209-216` |
| Há controle de concorrência? | Sim. `modify_session` com `select_for_update` e `expected_revision` opcional; `rev += 1` a cada mudança; resultados de checagem de `rev` velha são descartados. | [A] `modify.py:71,81,168-172`; `write.py:52` |
| O commit é idempotente? | Sim, em duas camadas na web (recibo de mutação + `IdempotencyKey` do commit) e duas na Nice (`concierge.purchase:` + chave derivada do token do orçamento), com endpoint de recuperação. | [A] `commit.py:84-89,256-268`; `api/views.py:251-319,762-805`; `tools.py:1532-1567,1655-1665` |
| Termos defasados são recusados? | Sim. `revision_changed`, `hold_expired`, total esperado. | [A] `commit.py:369-446` |
| Troca de identidade invalida a revisão? | **Não.** `assign_customer`/`assign_handle` salvam sem incrementar `rev`. O commit trava cliente→sessão e recusa `customer_identity_changed` durante o commit, mas não compara com a identidade que estava na revisão. | [V] `shopman/shop/services/sessions.py:338` (save só de `data`) |
| Expiração? | Não há `expires_at`. Hold web expira em 30 min (`hold_ttl_minutes`); sessão sem pedido é apagada após 48 h de inatividade. | [A] `availability.py:997-1004`; `cleanup_stale_sessions.py:43-71` |
| Mesclagem anônimo + conta? | Não existe. No login a sacola do navegador é reprecificada; na troca de link, a sacola carregada **substitui** a local. | [A] `storefront/cart.py:148-178`; `api/auth.py:314-317,368-396` |
| iFood? | Cria `Order` direto, sem `Session`. | [A] `ifood_ingest.py:81-84,195-202` |

**Consequência adversarial.** O par `Session` (por canal) + `Order` (canal-agnóstico) já é a fronteira certa. Uma sessão compartilhada entre canais exigiria um selo de commit multicanal, holds com dono duplo e política de preço/pagamento/confirmação ambígua (cada canal tem seu `ChannelConfig`). Não há ganho que pague esse custo.

**Defeito menor:** como `assign_customer` não incrementa `rev`, um orçamento revisado anonimamente continua válido depois da identificação. O risco real é baixo (o login reprecifica via `modify_session`, que incrementa `rev` [H: confirmar em teste que todo caminho de identificação passa por reprecificação]).

### 2.2 Identidade e titularidade (Guestman, Doorman, vínculo da conversa)

O que está bem [A]: posse de contato única e travada (`contact_point.py:102-112`), conflito falha fechado (`identity.py:46-92,171-172`), fusão com evidência, auditoria e janela de desfazer (`contrib/merge/service.py:103-150`), expurgo LGPD com lápide HMAC que impede a volta pelo ManyChat (`erasure_tombstone.py:44-95`), tokens guardados como HMAC, uso único e troca sob trava (`doorman/models/access_link.py:26-31`; `services/access_link.py:236-272`), pedido anônimo por `/pedido/<ref>` recusado [M].

O que está mal, em ordem de gravidade:

- **S1 [V].** `build_tracking_access_url`, `build_payment_access_url` e `build_reorder_access_url` têm `source="manychat"` como padrão (`access_urls.py:73-97`), e `notification.py:838-840` os chama sem sobrescrever. Na troca, `source == "manychat"` grava `IDENTITY_DEVICE` e chama `trust_device` (`api/auth.py:338-349`). O comentário logo acima diz: "Link que NÓS empurramos (`internal`, campanha) não confia: mensagem se encaminha." O código contradiz a regra que ele mesmo escreveu. Mitigação parcial existente: quando o aviso sai por *flow* do ManyChat, o link pessoal é trocado pelo público (`adapters/notification_manychat.py:686-715`); quando sai como texto livre, o token vai inteiro.
- **S2 [V].** `order_matches_customer_identity` aceita casamento por telefone (`handle_ref`, `customer.phone`, `customer_phone`) mesmo quando `customer_ref` existe e é de outra pessoa (`customer_orders.py:117-123`). O histórico usa o mesmo filtro por telefone [A: `:773-783`].
- **S3 [V].** O sinal que aposenta identificadores de login ao trocar de telefone deixa ManyChat, Instagram, CPF e iFood intactos (`signals.py:32-36`); `sync_subscriber` acha o cliente pelo `manychat_id` (`manychat/service.py:118-126`). No WhatsApp, o assinante é o número; quem herda o número herda a conta [H: depende de o ManyChat manter o `subscriber_id` para o mesmo `wa_id`, o que é o comportamento documentado do provedor, não verificado aqui].
- **S4 [A].** `IdentityResolver.resolve()` não filtra `is_verified`.
- **S5 [A].** Todo link é `login()` completo; não há concessão restrita a um pedido; `required_audience` nunca é passado.
- **Resíduo de dispositivo compartilhado [A]:** o logout preserva `cart_session_key` com `data["customer"]` do cliente anterior até outro login reprecificar (o próximo anônimo vê o preço de grupo do anterior [H]); o rascunho do checkout fica no `localStorage`.

**Achado arquitetural importante:** já existe a peça que resolve S1 e T5 com elegância. `request_can_access_order` concede acesso a um pedido quando a **referência foi concedida à sessão atual** (até 20 refs) [A: `customer_orders.py:73-81`]. Um link de aviso pode, portanto, conceder **só aquele pedido** (ver e pagar), sem login, por mais tempo, e o encaminhamento deixa de entregar a conta. Ver WP OC-01 no plano.

### 2.3 Storefront: experiência real

Medições [M] (anônimo, 375 px, 22h, loja fechada):

- **U1. Promessa sem lastro.** Catálogo com 31 itens, todos `availability: "unavailable"`, `can_add_to_cart: false`, `promise: null` (resposta de `/api/v1/storefront/catalog/`). Ao mesmo tempo: topo "Fechado agora. Abrimos amanhã às 9h. Você já pode finalizar o pedido, e conferimos quando abrirmos."; sacola "Já fechamos por hoje. Você pode encomendar para o próximo dia."; home "Encomendas com até 30 dias de antecedência". A página de produto oferece só "Me avise sempre". O visitante não tem como encomendar nada e é informado de que pode. Causa provável: o ambiente de testes não tem fornada planejada para amanhã (dado), e a encomenda depende da fornada planejada (`presentation/promise.py`, `PLANNED_OK`), o que está correto pela regra do dono ("encomenda mede só a fornada da data"). O defeito é a frase: `CLOSED_HERO_HINT` é constante e incondicional [V: `home.ts:5-9`].
  **Correção de enquadramento (dono, 23/11):** comprar com a loja fechada é um regime previsto e decidido, não um furo. Pela [ADR-036](../decisions/adr-036-loja-online-paga-ao-pedir.md) (14/10, emenda de 09/11), o cliente paga ao pedir; o cartão é autorizado no pedido e capturado no aceite (Stripe, captura manual); o Pix é pago no pedido e estornado sozinho se a casa recusar ou deixar vencer; o prazo de aceite é de 60 min de loja aberta para encomenda e para pedido feito com a casa fechada. A fila da fornada (`waitlist.charge_at = "confirmation"`) só cobra quando o cliente confirma a vaga. U1 continua valendo no recorte certo: naquela noite **nenhum item** podia entrar nesse regime no ambiente de testes, e a frase não confere isso. Antes de corrigir a frase, o agente confere no ambiente de testes por que até os itens de revenda (ex.: água mineral) estavam sem disponibilidade às 22h [H: fornada não planejada e estoque de revenda zerado].
- **U2.** 19 elementos de texto abaixo de 14 px na home, incluindo "Indisponível" (12 px), descrições (12 px) e a barra inferior (12 px).
- **U3.** 34 perguntas na home; duplicata exata; "Como posso pagar?" × "Quais formas de pagamento vocês aceitam?"; "Os produtos têm alérgenos?" × "Vocês têm opções sem glúten? E quanto a alérgenos?". Causa [V]: `build_public_faq` soma as respostas operacionais (tiradas da configuração) e as curadas (`FAQEntry`) sem deduplicar (`shopman/storefront/presentation/public_information.py:206-235`). Não é só excesso: são **duas respostas para a mesma pergunta, de fontes diferentes**, que podem se contradizer.
- **U6 vitrine.** "Do nosso cardápio · Disponibilidade em tempo real" abre com três itens indisponíveis.
- **Semântica.** O `h1` da home é "Boa noite." (saudação, não o propósito da página). Pontinhos do carrossel com 20 px de largura (abaixo do mínimo de 24 px do critério 2.5.8, salvo exceção de espaçamento).
- **Dado divergente do seed.** A descrição do Jambon-Beurre no ar tem travessão ("o clássico parisiense" após `—`); o seed já foi corrigido para dois-pontos [V: `config/management/commands/seed.py:2320`]. O banco do ambiente de testes está atrás do seed.
- **Logado (Chrome do dono, desktop):** faixa "Em Preparo, Pedido NB-261117-R44" num pedido de 17/11 [H: pedido parado no ambiente de testes ou ref que não é data]; o cartão "Quer repetir seu último pedido" aparece duas vezes.

O que está bom [M]: entrada pelo WhatsApp sem senha e sem código (três passos, SMS como alternativa discreta); página 404 útil; acompanhamento anônimo recusado com orientação clara; carregamento progressivo do cardápio com aviso textual; promessa de prontidão escrita no servidor numa função só (`presentation/promise.py`), o que elimina a classe de defeitos "cada tela diz uma hora".

O plano de excelência de 16/11 tem 11 de 12 WPs no `main` (L10, agenda das fornadas, adiado pelo dono) [A]. Os achados acima são posteriores ou não cobertos por ele.

### 2.4 Nice: a jornada inteira na conversa

| Etapa | Estado | Evidência | Lacuna |
|---|---|---|---|
| Informação, FAQ, horário | Na conversa | [A] `intents.py:1487-1490`, `faq_answer`, `verification` | Fato desconhecido vira "vou verificar" com a equipe (correto) |
| Descoberta e disponibilidade | Na conversa | [A] `search_storefront`, `allergens` | `notify_when_available` registrado, não ligado a intenção |
| Sacola | Na conversa, valor absoluto (ADR-050) | [A] `set_item`, `view_cart` | |
| Retirada/entrega, data, horário | Na conversa | [A] `order_closing.py:466-570` | Entrega pelo motor em PR #3409 |
| Revisão dos termos | Na conversa | [A] `review_order`, `tools.py:2150` | |
| Confirmação expressa | Na conversa | [A] `_confirmation`, `_code_confirmation` (`tools.py:1374-1459`) | Código de 4 dígitos obrigatório enquanto o id de evento não é verificado |
| Pedido | Na conversa, idempotente | [A] `tools.py:1462-1716` | |
| **Pix copia-e-cola** | **Parcial** | [V] `tools.py:1723-1725`; `order_tracking.py:1219-1224`; `tools.py:2183` | Só no mesmo turno do pedido; consulta posterior devolve link rotulado "Copiar código Pix" (T2); motor descarta (T3) |
| **Cartão** | Só na consulta de status | [A] `order_tracking.py:1288-1295`; `render_result` omite `checkout_url` | Não aparece no pedido |
| Estado do pagamento | Sob demanda | [A] `order_status` | A Nice não sabe quando o pagamento caiu (T4) |
| Avisos proativos (pago, aceito, pronto, saiu) | Fora da Nice, pelo pipeline de notificação | [A] `lifecycle.py:644-657`; `adapters/notification_manychat.py:405-415` | Fora da transcrição; texto livre só dentro da janela de 24 h |
| Alterações pós-pedido | Parcial | [A] `cancellation.py`, `order_addition.py` | Sem remover item, remarcar, trocar endereço ou forma de pagamento (vai à equipe) |
| Reclamação | Encaminhada | [A] `intents.py:1462-1477` | Sem resolução na conversa (correto como primeira versão) |
| Atendimento humano | Live Chat do ManyChat | [A] `mark_handoff`, `transport.py:552` | Sem caixa de entrada no Shopman; mensagens da equipe invisíveis |
| Volta à Nice | Atrás de chave | [A] `return_to_concierge`; `HUMAN_RETURN_ENABLED=False` | Memória apagada na volta (`service.py:1820`) |

**Duplicação de verdade comercial [A]:** `place_order` revalida encomenda, horário e janela importando o privado `_validate_preorder` do storefront (`tools.py:1580-1608`); a regra "assumir a única forma de pagamento" existe em dois lugares (`tools.review_order` e `commerce_read._fulfillment_conditions`); `commerce_read` importa privados (`_hour_pair`, `_window_start`, `_channel_hold_ttl_minutes`); taxa e interpretação de endereço vivem em `concierge/address.py`. Nenhuma diverge hoje [H], mas cada uma é uma segunda autoridade em potencial.

**Resposta à pergunta 1 do Relatório II** ("hoje é possível finalizar J1 sem Storefront?"): **com Pix, sim, quando o código existe no mesmo turno do pedido** (canal WhatsApp é `payment.timing: at_commit` [A: `config/instances/nelson.json`]); se o código chegar depois, ou se o cliente perguntar mais tarde, a Nice entrega um link para o site. **Com cartão, não pela Nice no momento do pedido** (o link do gateway só aparece na consulta de status). O aviso de pagamento do pipeline de notificação leva o Pix no texto (`notification_copy.py:190-195`), então o cliente não fica sem o código, mas ele chega por outro caminho que a Nice não enxerga.

### 2.5 Experimentação, copy e Projections

- **Nenhum resolvedor de variante existe** em nenhuma superfície [A]. R0 a R2 do release estão entregues; R3 em diante (incluindo coortes V1/V2) não existe [V: `WP-RELEASE-01…md:3-9`; A: `release-contract.md:8-9`].
- **Copy:** `OmotenashiCopy` única por `(key, moment, audience)`, com `simple_history` [A: `omotenashi_copy.py:18-56`]; defaults em `shop/omotenashi/copy.py` (2.331 linhas); resolução no servidor dentro das projeções. **Parte relevante da copy da loja está no código Nuxt** (`presentation/*.ts`, `utils/operationalCopy.ts`) [V/A]. Isso muda a natureza do problema de isolamento: o que é copy de código fica naturalmente isolado pela própria variante de código.
- **T1** (cache por processo) é pré-requisito de qualquer coisa que dependa de copy editada no Admin.
- **Contratos:** três snapshots de projeção compartilhados entre backend e Nuxt (`contracts/projections/storefront_{catalog,product_detail,site}.json`), comparados byte a byte [A]; contêm copy resolvida (`"availability_label": "Indisponível"`). Tipos TypeScript escritos à mão (1.561 linhas). Versão de API só no major.
- **Telemetria:** só erro de cliente e eventos de endereço (enum fechado, sem PII) [A: `api/telemetry.py:40-133`]. Nenhum evento de exposição, funil ou Web Vitals.
- **Governança em atrito:** o Continuum lê `kill_switch` e flags de `settings`/env [V: `shopman/storefront/continuum.py:43-50`], contra a regra do contrato de release de que flag mora em `RuleConfig`, nunca em env [A: `release-contract.md:212-220`]. Pré-existente; não bloqueia, mas não deve ser copiado.

### 2.6 Framework de comércio conversacional

O núcleo é puro e provado (K38, wheel sem Django, conformidade como segunda implementação) [V: ADR-049]. F0 a F10 e N2 a N9b estão no `main`; F11 (conformidade) sem fechamento [A]. O motor está ligado por classe (`conversational_live_inform/handoff/order`, todas `False` por padrão) e embrulha as ferramentas da Nice em vez de substituí-las [A: `effect_site.py:1-25,230-287`]. PRs em voo (#3399 pagamento, #3409 entrega, #3411 recusa, #3414 porteiro) acrescentam lances do motor, não capacidade nova de pagamento [A]. **T3 deve ser corrigido nessa frente antes de ligar `conversational_live_order`.**

---

## 3. Análise adversarial dos relatórios

Legenda: **Mantida** · **Aprimorada** · **Qualificada** · **Refutada** · **Substituída** · **Descartada**.

### 3.1 Relatório I

| Proposta | Veredito | Fundamento |
|---|---|---|
| Baseline A congelada, candidata B, A protegida, promoção por evidência | **Mantida** | Coincide com ADR-043/WP-RELEASE-01. |
| E1–E10 (invariantes) | **Aprimorada** | Corretos, mas não verificáveis como escritos. O plano os converte em invariantes com teste ou gate nomeado (Contrato de Excelência, plano §6). |
| "Experience Registry" como camada própria | **Substituída** | É o resolvedor R4 já decidido, configurado em `RuleConfig`. Uma camada nomeada nova seria o segundo control plane que o contrato de release proíbe. |
| "Mecanismo permanente, variantes temporárias" | **Mantida e reconciliada** | Não conflita com o invariante 14 do release ("V1/V2 permanente é dívida"): o resolvedor é permanente, cada experimento carrega `remove_after` com CI que reprova o vencido. Não precisa emendar ADR. |
| Registro de experimento com ~20 campos | **Aprimorada (enxugada)** | Metade dos campos já existe em outro lugar (release_id em `X-Shopman-Release`; contrato de projeção nos snapshots). Ficam: ref, superfície, variantes, coortes, alocação, sal, dono, hipótese, métricas, `remove_after`. |
| Copy Profiles: perfil + revisão publicada imutável + rascunho no Admin | **Substituída** | (a) Boa parte da copy da loja está no código Nuxt e já fica isolada pela variante de código. (b) O rascunho já é dado pela coorte: copy de B só é vista pela coorte `internal` enquanto B não for promovida, então "editar B" já é editar um rascunho. (c) `simple_history` já dá auditoria e reversão por linha. Proposta: uma quarta dimensão `experience` na cascata existente, **criada só quando a primeira mudança concreta de B exigir copy de servidor diferente**, e só depois de corrigir T1. Nenhum modelo de publicação novo. |
| Duas classes de comparação (teste controlado de UX × experimento de política) | **Mantida** | |
| Matriz de mudança de Projections | **Mantida** | Aplicada no plano com os snapshots existentes. |
| L1/L2/L3 para mudanças visuais | **Mantida** | Nenhuma mudança proposta aqui é L3. |
| QA comparável "dois endpoints ou coortes de um deploy" (D3) | **Decidida** | Coortes de um deploy (D5 do release). Dois endpoints contradizem build-once. |
| Shadow só leitura | **Mantida** | |
| H1 Guestman ampliado | **Refutada** como dono de continuidade comercial; **mantida** no recorte de identidade (frescor, reatribuição). | |
| H2 Orderman + Guestman + composição | **Mantida e concretizada** | É a recomendação, com o serviço de transferência (§1.3). |
| H3 capacidade fina de coordenação | **Descartada como camada; mantida como função** | Uma função de serviço (`session_transfer`) no orquestrador, sem modelo próprio. |
| H4 domínio novo | **Descartada** | Nenhuma lacuna que exija. |
| Cenário de referência "conversa no WhatsApp, fotos no site, volta, finaliza no site" | **Qualificado** | Com transferência, a sacola vai ao site e a conversa passa a apontar para ela (a Nice diz "sua sacola está no site agora"), e não fica editável nos dois lados. Se o cliente voltar a pedir pela conversa, a sacola volta pelo mesmo mecanismo. |

### 3.2 Relatório II

| Proposta | Veredito | Fundamento |
|---|---|---|
| Jornada 100 % Nice como requisito de primeira classe | **Mantida** | Lacunas reais: T2, T3, T4, alterações pós-pedido, volta do humano. |
| "Retomada, espelhamento, transferência reconciliada, sessão compartilhada são alternativas" | **Decidida** | Pré-pedido: só transferência reconciliada. Pós-pedido: só referência. Espelhamento de sacola e sessão compartilhada **descartados**: criariam duas autoridades sobre um estado mutável. |
| Contrato de transição em 9 passos (identify…observe) | **Aprimorado** | Cinco dos nove já existem (`AccessLink` de uso único, `_copy_cart_to_web`, recusa por total mudado, abandono da origem, recibo do link). O plano reduz a 4 operações reais de um serviço: `offer`, `accept`, `apply_once`, `receipt`. |
| Não criar "sacola universal" nem entidade "Intenção Comercial" | **Mantida e provada** | §1.1 itens 2 e 3. |
| Guestman pode guardar ponte de continuidade? | **Refutada** | A ponte é o `AccessLink` (Doorman, já carrega `cart_session_key` em metadata) e `Conversation.session_key`. O Guestman fica com pessoa, contato, consentimento e linha do tempo. |
| Matriz N01–N25 e C01–C10 | **Mantida, priorizada** | O plano marca quais viram teste automatizado (harness com os fakes do framework), quais E2E com navegador, e quais exigem provedor real. |
| J9 "vários canais em paralelo, controle otimista" | **Substituída** | Com transferência, não há edição paralela da mesma sacola. Duas sacolas em canais diferentes são legítimas (duas compras); o risco é o cliente não perceber. Solução: aviso de sacola aberta em outro canal na revisão (OC-12), não sincronização. |
| J10 "múltiplos assuntos" | **Qualificada** | Uma conversa tem uma sacola pré-pedido por vez (modelo atual); assuntos sobre pedidos feitos são endereçados por referência do pedido. Não há necessidade comprovada de vários episódios comerciais simultâneos na mesma conversa. |
| "Link de acompanhamento é opcional; responder na conversa é obrigatório" | **Mantida** | T2/T3 são as violações. |
| Fase R1 primeiro (provar Nice-only antes da ponte) | **Mantida** | A ordem do plano respeita: Nice-only (fase 2) antes de ligar a transferência (fase 3). Correções de segurança (fase 0) vêm antes de tudo. |
| Lista de 12 riscos | **Mantida**, e acrescida de S1–S5, T1, T5, U5, U6 | Os relatórios não encontraram nenhum dos achados da tabela §1.2. |

### 3.3 Onde os relatórios erraram por omissão

1. Não leram o Continuum 0.2, que já resolve a metodologia de promoção.
2. Não encontraram a transferência de sacola existente nem o handoff web→web.
3. Trataram copy como problema só de Admin; metade é código.
4. Não olharam a borda (cache público por URL, cookies prometidos na privacidade), que restringe qualquer A/B em anônimos.
5. Não olharam os links de aviso, que são a principal porta entre canais hoje, e a mais insegura.

---

## 4. Respostas às 12 perguntas obrigatórias do Relatório II

1. **J1 sem Storefront:** Pix sim, se o código sair no mesmo turno; depois disso, não (T2). Cartão, não no pedido. Correção: OC-07.
2. **Quando `tracking_url`/`payment_url` é necessidade:** sempre que o cliente pede o Pix depois do pedido, ou paga com cartão. Alternativa: ação de conversa com o próprio código; link do gateway direto para cartão.
3. **Quem comunica pagamento e aceite:** o pipeline de notificação (ManyChat → SMS → e-mail), fora da Nice e fora da transcrição. Texto livre só dentro de 24 h; fora dela, só *flow* aprovado.
4. **Correções antes e depois do commit:** antes, tudo na conversa; depois, só cancelar (enquanto `new`/`accepted`) e acrescentar; o resto vai à equipe. OC-14 leva remarcar, remover item e trocar endereço para a conversa usando o `order_edit` que o balcão já usa.
5. **Posse de intenção fora de `Conversation` e `Session`:** não existe e não é necessária (§1.1).
6. **Guestman:** identidade e relacionamento; nada de ponte comercial (§3.2).
7. **Reservas e preços ao cruzar canal:** recriar pelo domínio do destino (reprecificar e re-reservar), mostrar diferença, abandonar a origem. É o que `_copy_cart_to_web` já faz.
8. **Atuação simultânea:** sacola: impossível por construção (uma viva). Pedido: `order_edit` e `cancellation` já serializam sob trava; a Nice só age com autoridade de turno revalidada dentro do commit.
9. **Experimento de UI não contamina a Nice:** a Nice não consome o resolvedor do Storefront; a variante muda apresentação, nunca projeção de fato; contratos de projeção travados na variante padrão.
10. **Gates que faltam:** listados no plano §9.
11. **Domínio novo:** não há motivo comprovado.
12. **Relatório I:** ver §3.1.

---

## 5. Decisões que só o dono pode tomar

Ver [plano §10](2026-11-23-etapa-ii-omnicanal-espec-e-plano.md#10-decisões-pendentes-do-dono). São seis; todo o resto é mecânica ou óbvio de omotenashi.
