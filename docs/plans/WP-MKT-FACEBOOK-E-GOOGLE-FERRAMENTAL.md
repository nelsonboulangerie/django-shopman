# WP-MKT-FACEBOOK-E-GOOGLE-FERRAMENTAL

Pedido do dono em 25/09/2026, logo depois do primeiro post do Google Meu Negócio sair
pelo app de Marketing (anúncio 32, alpha). São **duas frentes, uma por PR**:

- **Frente A — Facebook:** ligar a publicação na Página pelo app de Marketing.
- **Frente B — Google:** dar ao Google tudo que a API oferece e o app ainda não usa:
  botões, tipos de postagem e as travas de qualidade antes de publicar.

Leitura obrigatória antes de mexer: [marketing-surface-contract.md](../reference/marketing-surface-contract.md)
(o contrato factual do Marketing; `make marketing-docs` impede deriva),
[marketing-publication-canary.md](../operations/marketing-publication-canary.md) e
[data-schemas.md](../reference/data-schemas.md).

## O que já foi medido (25/09/2026)

- **Consumers globais do Marketing LIGADOS no alpha** (`SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED`
  e `..._DELIVERY_CONSUMER_ENABLED` = `true`, por causa do WhatsApp). Consequência: ligar a flag
  de uma plataforma faz o fluxo normal publicar tudo que estiver elegível para ela. **Antes de
  ligar**, conte (só leitura, conexão direta `25060`) `shop_announcement`, `shop_marketingoutbox`
  e `shop_deliverytarget` da plataforma. `NOT_ATTEMPTED` vira `FAILED_RETRYABLE`: destino que
  falhou por "plataforma desligada" **sai sozinho** quando a flag liga.
- **A flag vive só no app VIVO.** O spec versionado fica `false`:
  `test_deploy_templates_never_prearm_publication_canary` reprova `true` ali. Mudar o vivo =
  contexto doctl `shopman-spec-update`, sempre a partir de `doctl apps spec get` desse contexto
  (o spec lido pelo contexto de deploy vem SEM os detalhes dos bancos e derrubaria Postgres e
  cache). Conferir depois: contagem de `type: SECRET` igual e `cluster_name` presentes.
- **Nada público sai sem o "pode publicar" do dono**, com prévia (foto, texto, destino) na mão.
  O ensaio é uma campanha manual com **só** aquela plataforma (nenhum contato), revisão ligada.
- A prévia da revisão mostrava link de produto de exemplo que não ia no post — corrigido no
  PR #1157. Confirme que ele está no `main` antes de validar prévias.

## Frente A — Facebook

**Estado:** `shopman/shop/adapters/marketing_delivery_facebook.py` (+ `marketing_delivery_meta.py`)
existe e tem teste; no alpha, `META_PAGE_ID=764222643620409` (GENERAL) e `META_PAGE_ACCESS_TOKEN`
(SECRET) já estão no app vivo; `SHOPMAN_MARKETING_FACEBOOK_PUBLICATION_ENABLED` não existe no
vivo (= `false`). O Facebook nunca foi ensaiado (pedido do dono desde 17/09).

1. **Provar o token sem publicar.** O console da DO **não recebe** envs SECRET, então a prova
   não é por lá. Caminho: o dono abre o token no Graph API Explorer / Access Token Debugger
   (logado na conta dele) e confirma: tipo **Page**, Página = `764222643620409`, escopos
   `pages_manage_posts` + `pages_read_engagement`, e **validade** (token de usuário vence em
   ~60 dias; o certo é token de Página derivado de usuário de sistema do Business Manager, que
   não vence). Token errado ou que vence → gerar o certo e o dono cola no painel da DO (segredo
   não se digita por agente).
2. **Contar o que sairia** (ver acima) e só então ligar a flag no vivo.
3. **Ensaio:** campanha manual "Ensaio Facebook", só Facebook, texto e foto neutros aprovados
   pelo dono (o post do Google serve de base: fachada `img.nelsonboulangerie.com.br/home/facade2.jpg`
   e o texto com horário e endereço). Publicar só com o "pode publicar".
4. **Conferir no mundo:** recibo `accepted` no ledger **e** o post visível na Página.
5. Atualizar o contrato (linha 203 do marketing-surface-contract) e a memória do projeto.

## Frente B — Google Meu Negócio: botões, tipos e travas

**Estado:** `shopman/shop/adapters/marketing_delivery_google.py` publica só `topicType: STANDARD`
e põe `callToAction: ORDER` **sempre que há link** — rótulo que mente quando o link não é de
compra. Projeto `528240639893`, conta `115642419325714529817`, local `16932843135625825567`,
cota 300 QPM.

1. **Botão escolhível e explícito** (no modelo e na revisão do anúncio), com o rótulo que o
   Google MOSTRA em pt-BR, nunca o nome da API:
   Reservar (`BOOK`), Pedir on-line (`ORDER`), Comprar (`SHOP`), Saiba mais (`LEARN_MORE`),
   Inscrever-se (`SIGN_UP`), **Ligar agora** (`CALL`, sem URL: usa o telefone do perfil) e
   **Nenhum** (padrão). `ORDER`/`SHOP` só com link de produto ou oferta. Sem link implícito
   virando botão. Decisão do dono (25/09): "Ligar agora" ou nenhum para posts institucionais;
   "Como chegar" não existe na API (o perfil já tem "Rotas").
2. **Tipos de postagem:** `EVENT` (título, início e fim) e `OFFER` (título, período, cupom,
   link de resgate, termos). A oferta deve nascer do que o shop já tem (`Promotion`/`Coupon`,
   ex.: "Semana do Pão"), sem cadastro paralelo. `ALERT` fica de fora.
3. **Travas antes de aprovar**, na prévia, com a mensagem no campo (dialeto `{detail, field,
   errors}`): foto **JPEG ou PNG** (o WebP da loja não serve), dimensão e peso dentro do que o
   Google aceita, texto dentro do limite do `summary`, e **sem telefone no texto** (a política de
   posts do Google recusa). Conferir cada limite na documentação oficial antes de codificar.
4. **Prévia fiel:** o Google recorta a foto do post (a arte com texto sobreposto perdeu as
   laterais em 25/09). A prévia mostra o recorte, e texto dentro da imagem é desaconselhado na
   tela.
5. **Depois de publicar:** consultar `localPosts.get` para o estado real (`LIVE`, `REJECTED`,
   `PROCESSING`) e registrar no ledger, em vez de parar em `accepted`. A foto aparece ~1–2 min
   depois do texto; isso é `PROCESSING`, não falha. Apagar um post é **nova ação pública**:
   botão explícito, com confirmação, nunca automático.
6. Contratos: `contracts/marketing/*`, `contracts/openapi/marketing_v2.openapi.json`, o
   marketing-surface-contract e `data-schemas.md` (novas chaves de `platform_content`),
   com `make marketing-docs` verde.

## Pronto quando

- **A:** um post do Facebook publicado pelo app, conferido na Página, com o token provado de
  validade longa; flag ligada só no vivo; contrato atualizado.
- **B:** um post do Google com botão escolhido pelo operador e um com tipo `EVENT` ou `OFFER`,
  publicados só depois do "pode publicar" e conferidos no perfil; testes do adapter para cada
  `actionType`/`topicType`; travas cobertas por teste; `make marketing-docs` e a cadeia completa
  do Marketing verdes.
