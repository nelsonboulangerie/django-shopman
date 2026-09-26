# Marketing V2 — Capability Composer

Status: proposta de arquitetura pronta para execução incremental

Data da pesquisa: 2026-09-26

Branch: `codex/marketing-v2-20260926`

Base: `origin/main` em `dc2b90687c6305c436827aa22f775c1bddd5ed19`

## 1. Decisão executiva

O Marketing V2 deve permitir uma única intenção de campanha com várias consequências, sem fingir que as plataformas têm o mesmo produto.

O operador informa uma vez:

- o objetivo;
- a oferta, promoção ou cupom;
- a mensagem-base;
- a audiência, quando houver mensagem direta;
- a janela de publicação.

Depois escolhe destinos concretos, por exemplo:

- Instagram `@conta` / Feed / Carrossel;
- Instagram `@conta` / Story;
- Facebook `Página Centro` / Feed;
- Google `Loja Jardins` / Oferta;
- WhatsApp `Conta Principal` / Template aprovado.

Cada destino é um **placement** independente. Ele tem campos, mídia, preview, validação, agendamento, idempotência e resultado próprios. O Marketing coordena placements; não reduz todos a um payload comum.

Isso preserva as vantagens de uma operação multiplataforma — uma intenção, uma oferta e uma revisão — sem nivelar a experiência pela plataforma mais limitada.

## 2. O que já existe e o que precisa mudar

### 2.1 Base valiosa a preservar

O sistema atual já possui componentes que não devem ser descartados:

- campanha e artefato selado;
- outbox durável;
- idempotência e ledger de entrega;
- adapters separados por plataforma;
- reconciliação e classificação de falhas;
- projeções para o Marketing Nuxt;
- domínio de `Promotion` e `Coupon` no orquestrador.

O problema principal não é a confiabilidade do disparo. É o modelo de capacidade e composição anterior ao disparo.

### 2.2 Limitações atuais

O catálogo atual representa, em essência, um formato por plataforma:

| Plataforma | Capacidade atualmente exposta |
|---|---|
| Instagram | uma imagem em Story ou Feed |
| Facebook | Feed com texto, link ou foto |
| Google Business Profile | Standard, Event ou Offer com uma foto |
| WhatsApp | um fluxo global do ManyChat |
| TikTok | adapter de foto dormente, sem seleção operacional |

Além disso:

- `Campaign.platforms: list[str]` não representa dois formatos na mesma plataforma;
- a configuração supõe um único Page ID, Instagram account ou Google location;
- CTA é tratado como se fosse uma propriedade uniforme, mas não é;
- promoção é selecionável, porém cupons não fazem parte do fluxo;
- o composer não distingue capacidade da plataforma, capacidade implementada, capacidade da conta conectada e validade do conteúdo;
- o operador descobre restrições tarde demais.

## 3. Inventário de capacidades das plataformas

Esta seção separa o que a API oferece do que o adapter atual já executa. Limites voláteis devem ser consultados da conta quando a plataforma oferecer um endpoint próprio; números documentais não devem virar constantes permanentes no frontend.

### 3.1 Instagram Content Publishing API

#### Formatos oferecidos

- publicação com uma imagem;
- publicação com um vídeo;
- Reel;
- Story com imagem ou vídeo;
- carrossel com até 10 itens, misturando imagens e vídeos.

#### Campos e opções relevantes

- legenda;
- texto alternativo para imagem;
- localização e marcação de usuários, quando aceitas pelo formato/conta;
- capa e posição de capa para vídeo/Reel;
- `share_to_feed` para Reel;
- colaboração;
- trial Reel, quando elegível;
- indicação de conteúdo gerado por IA;
- parceria paga e patrocinadores, quando elegíveis.

#### Restrições que impactam UX

- publicação é para contas profissionais; Story via API tem elegibilidade mais restrita;
- imagens publicadas pelo endpoint são JPEG;
- mídia precisa estar acessível pela plataforma ou ser enviada pelo fluxo suportado;
- containers expiram; a preparação de mídia não pode ser tratada como rascunho eterno;
- o limite deve ser lido pelo endpoint `content_publishing_limit` quando possível;
- a documentação consultada contém referências divergentes a 50 e 100 publicações em 24 horas. O produto deve mostrar o valor vivo da conta, não escolher uma dessas cifras como verdade fixa.

#### CTA

O endpoint orgânico não oferece um botão CTA genérico equivalente ao Google Business Profile. Link em legenda não deve ser apresentado como botão clicável garantido. O composer pode sugerir ação em linguagem natural, mas o preview deve mostrar a consequência real.

#### Gap do app

O app implementa apenas imagem única no Feed/Story. Vídeo, Reel, carrossel e os campos avançados ainda não existem no adapter nem no schema operacional.

### 3.2 Facebook Pages API e Video/Reels API

#### Formatos oferecidos

- post de texto;
- post com link;
- foto;
- vídeo;
- Reel;
- publicação imediata, rascunho ou agendada, conforme o endpoint;
- segmentação geográfica de Page post, quando suportada.

#### Campos e opções relevantes

- mensagem;
- link;
- mídia;
- título e descrição nos endpoints de vídeo/Reel;
- colaborador em Reel, quando elegível;
- estado de publicação de Reel: rascunho, agendado ou publicado.

#### Restrições que impactam UX

- um usuário pode administrar várias Pages; a conexão deve descobrir e armazenar todas as Pages autorizadas;
- Reels de Page publicados por esse fluxo são públicos;
- o limite documentado de Reels é 30 em 24 horas;
- upload e publicação de vídeo são etapas separadas e exigem acompanhamento de estado.

#### CTA

Page feed orgânico não oferece, nesse fluxo geral, o mesmo conjunto de botões CTA do Google. Link é uma propriedade de conteúdo, não um botão arbitrário. CTAs de anúncios ou outros produtos não devem vazar para o composer orgânico.

#### Gap do app

O app tem Feed com texto/link/foto em uma única Page. Faltam múltiplas Pages, vídeo, Reel, rascunho/agendamento nativo e opções específicas.

### 3.3 Google Business Profile Local Posts

#### Formatos oferecidos

- Standard;
- Event;
- Offer;
- Alert, sujeito à política e ao tipo elegível.

#### Campos e opções relevantes

- resumo de até 1.500 caracteres;
- evento com título e intervalo de datas/horas;
- oferta com título, datas, `couponCode`, `redeemOnlineUrl` e `termsConditions`;
- CTA `BOOK`, `ORDER`, `SHOP`, `LEARN_MORE`, `SIGN_UP`, `CALL` ou nenhum;
- mídia;
- `scheduledTime` quando suportado pelo recurso;
- listagem, edição, exclusão e insights.

#### Restrições que impactam UX

- CTA é ignorado em `OFFER`; as ações da oferta vêm de seus próprios campos;
- Product posts não podem ser criados por essa API;
- o operador pode ter várias locations;
- listagem de locations é paginada, com `pageSize` máximo 100;
- capacidades e políticas podem variar por location e categoria.

#### Gap do app

O adapter já cobre Standard/Event/Offer e os CTAs principais, mas:

- usa uma única location;
- não envia `couponCode`, `redeemOnlineUrl` nem `termsConditions`;
- proíbe uma oferta com cupom apesar de a API comportá-la;
- não expõe edição, remoção ou insights no produto;
- não trata paginação/discovery de locations.

### 3.4 WhatsApp por ManyChat

#### Formatos oferecidos no caminho seguro de campanha

Fora da janela de atendimento de 24 horas, a mensagem precisa usar template aprovado. O template pode conter:

- cabeçalho de texto, imagem, vídeo ou arquivo;
- corpo com variáveis;
- rodapé;
- um botão de URL **ou** até três botões de resposta, sem misturar os dois grupos;
- categoria Marketing ou Utility.

Dentro da janela de 24 horas existem mensagens livres e outros elementos, mas uma campanha em massa não deve depender de cada destinatário possuir uma janela aberta.

#### Restrições que impactam UX

- o contato precisa ter opt-in;
- o template deve estar aprovado;
- variáveis e mídia precisam obedecer ao template aprovado;
- templates são criados e aprovados no ecossistema ManyChat/Meta, não inventados pelo composer no momento do envio;
- tokens e identificadores de fluxo pertencem a uma conta/bot específicos;
- custos, categorias e políticas podem variar e devem aparecer antes da confirmação quando conhecidos.

#### CTA

O CTA é propriedade do template aprovado. O operador preenche variáveis; não deve ser induzido a pensar que pode trocar os botões livremente.

#### Gap do app

O app executa um único `flow_ns` global por contato. Faltam:

- catálogo sincronizado de templates/flows aprovados;
- múltiplas contas;
- schema de variáveis e mídia por template;
- preview fiel;
- custo/categoria e readiness por conta/template.

### 3.5 TikTok Content Posting API — candidato, não conexão ativa

O repositório contém adapter de foto, mas ele está dormente. TikTok só deve aparecer quando conexão, escopos, auditoria e feature flag estiverem ativos.

Capacidades relevantes para uma futura ativação:

- publicação direta de fotos, com até 35 URLs;
- capa selecionável;
- título de foto até 90 unidades UTF-16;
- descrição de foto até 4.000 unidades UTF-16;
- publicação direta de vídeo;
- legenda/título de vídeo até 2.200 unidades UTF-16;
- privacidade retornada dinamicamente pela consulta de creator info;
- escolhas explícitas para comentários, duet, stitch, conteúdo comercial e IA;
- limite documentado de 6 requisições por minuto por token de usuário no endpoint de direct post;
- auditoria necessária para publicação pública.

O frontend nunca deve codificar opções de privacidade: deve usar exatamente as opções devolvidas para o creator conectado.

## 4. Modelo de capacidade em quatro camadas

O novo catálogo precisa responder quatro perguntas distintas.

| Camada | Pergunta | Exemplo |
|---|---|---|
| Provider | O que a API permite em tese? | Instagram permite carrossel de até 10 itens |
| Connector | O que nosso adapter implementa? | carrossel ainda está em desenvolvimento |
| Connection | O que esta conta/location permite agora? | Story indisponível para esta conta; quota restante 7 |
| Placement | Este conteúdo concreto é válido? | terceiro vídeo excede duração; CTA incompatível |

### 4.1 Regra de exposição

O operador pode conhecer todas as capacidades relevantes, mas só pode selecionar uma consequência executável.

Uma opção não implementada ou bloqueada deve aparecer desabilitada com:

- motivo exato;
- ação possível, quando houver;
- distinção entre “não implementado”, “falta conectar”, “sem permissão”, “quota”, “mídia incompatível” e “não permitido pela plataforma”.

Não esconder silenciosamente evita que o limite do app pareça limite da plataforma.

### 4.2 Schema sugerido

O backend deve publicar um catálogo versionado semelhante a:

```json
{
  "schema_version": 2,
  "providers": [
    {
      "provider": "instagram",
      "connections": [
        {
          "connection_id": "...",
          "label": "@nelson",
          "account_capabilities_checked_at": "...",
          "placements": [
            {
              "delivery_kind": "public_post",
              "format": "carousel",
              "implementation_state": "ready",
              "readiness": {"state": "ready", "reasons": []},
              "quota": {"used": 12, "limit": 100, "source": "live"},
              "fields": [],
              "media_slots": [],
              "compatibility_rules": [],
              "preview_kind": "instagram_carousel"
            }
          ]
        }
      ]
    }
  ]
}
```

Campos, escolhas, limites e requisitos condicionais precisam vir desse contrato. O Nuxt renderiza o schema; não mantém uma segunda matriz manual.

### 4.3 Identidade estável

A identidade mínima de uma consequência passa a ser:

```text
{connection_id, platform, delivery_kind, format}
```

Isso permite, na mesma campanha, Instagram Feed + Story, duas Facebook Pages ou três Google locations sem colidir idempotência nem auditoria.

## 5. Novo domínio

### 5.1 PlatformConnection

Representa uma conexão autorizada e descobrível.

Campos essenciais:

- `id` estável interno;
- provider;
- owner/account externo;
- nome amigável;
- Page, professional account, location ou bot externo;
- escopos/permissões observados;
- status e motivo de degradação;
- capability snapshot e timestamp;
- referência segura a credenciais, sem segredo na projeção.

As configurações escalares atuais devem migrar para registros. Durante a transição, uma conexão default pode ser derivada das settings existentes.

### 5.2 CampaignPlan

É a intenção comum do operador:

- objetivo;
- brief e mensagem-base;
- promoção e cupom opcionais;
- janela desejada;
- autoria, aprovação e estado do plano.

Não é uma promessa de payload idêntico.

### 5.3 CampaignPlacement

É uma consequência selecionada:

- identidade `{connection, platform, delivery_kind, format}`;
- campos específicos;
- referências de mídia e transforms;
- audiência, quando aplicável;
- horário efetivo;
- versão do capability snapshot usado;
- preview e validation snapshot;
- lifecycle independente.

### 5.4 CampaignBundle e dispatch

Uma publicação multiplataforma cria um bundle e N lanes independentes. A aceitação interna do bundle é transacional; os efeitos externos não são.

Estados do bundle:

- draft;
- ready;
- accepted;
- processing;
- completed;
- completed_with_failures;
- cancelled_before_effects.

Estados por placement:

- draft;
- invalid;
- ready;
- queued;
- preparing_media;
- publishing;
- succeeded;
- failed_retryable;
- failed_terminal;
- unknown_reconciling;
- cancelled.

Se Facebook publicar e Instagram falhar, Facebook não é “despublicado” como rollback implícito. O bundle termina com falhas e oferece retry apenas das lanes seguras. Resultado desconhecido exige reconciliação antes de repetir.

## 6. Experiência do operador

### 6.1 Quatro páginas no produto

1. **Hoje** — readiness, campanhas agendadas/em curso e pendências que exigem ação.
2. **Campanhas** — drafts, agenda, histórico e botão de nova campanha.
3. **Ofertas** — promoções, cupons, vigência e uso.
4. **Plataformas** — conexões, contas/Pages/locations, permissões, quotas e diagnóstico.

Templates deixam de ser uma página principal. Eles aparecem onde são escolhidos: no placement de WhatsApp ou como presets de composição. Histórico vira visão da campanha/bundle, não um silo separado.

### 6.2 Entrada por objetivo

O primeiro clique não deve perguntar “qual API?”. Deve oferecer:

- **Divulgar novidade** — publicação pública;
- **Lançar oferta** — promoção/cupom + publicações/mensagem;
- **Enviar mensagem** — WhatsApp e audiência;
- **Repetir campanha** — duplica intenção e placements, revalida tudo;
- **Começar em branco**.

### 6.3 Wizard em cinco passos curtos

#### Passo 1 — Objetivo e oferta

- nome interno sugerido automaticamente;
- objetivo;
- criar ou selecionar promoção;
- opcionalmente criar/selecionar cupom;
- resumo humano do que acontecerá.

#### Passo 2 — Onde publicar

Cards por conta concreta, não apenas por logotipo da plataforma:

```text
Instagram · @nelson
  [x] Feed — imagem
  [x] Story — imagem
  [ ] Carrossel — disponível
  [ ] Reel — precisa de vídeo vertical

Google · Loja Jardins
  [x] Oferta
```

Cada card mostra readiness, quota e impedimento. Um preset “Replicar onde fizer sentido” seleciona apenas placements compatíveis com os assets atuais; nunca inventa transformação destrutiva.

#### Passo 3 — Conteúdo

O operador escreve um brief/mensagem-base uma vez. O sistema preenche versões iniciais por placement, respeitando limites e convenções. Em seguida mostra abas por consequência:

- texto e campos próprios;
- mídia/crop próprios;
- CTA real;
- contador no limite da plataforma;
- preview fiel;
- diferenças em relação ao texto-base.

Editar uma versão não altera silenciosamente as demais. O operador pode reaplicar a base de forma explícita.

#### Passo 4 — Público e momento

- publicações orgânicas mostram “público da conta/plataforma”; não fingem segmentação;
- WhatsApp exige audiência e mostra opt-in, elegibilidade, exclusões e volume;
- agendamento comum é traduzido por lane;
- quando a plataforma não oferece agendamento confiável, o outbox do Shopman segura o efeito até a hora;
- diferenças de fuso e janelas são mostradas antes da revisão.

#### Passo 5 — Revisar e publicar

Uma linha por consequência, com preview e frase inequívoca:

```text
Instagram @nelson · Story · publicará 1 imagem agora
Facebook Página Centro · Feed · publicará imagem + link às 18:00
Google Loja Jardins · Oferta · válida até 30/09, cupom PRIMAVERA
WhatsApp Conta Principal · Template oferta_v3 · 842 contatos elegíveis
```

O botão principal diz exatamente o que fará: “Agendar 4 publicações e 842 mensagens”. Depois da aceitação, a tela acompanha cada lane independentemente.

### 6.4 Regras de facilidade

- caminho feliz com defaults seguros e sem campos irrelevantes;
- detalhes progressivos, nunca um formulário universal gigante;
- erro ao lado do placement e antes do disparo;
- autosave de draft;
- teclado e mobile utilizáveis;
- ausência de códigos internos na linguagem do operador;
- preview é evidência, não decoração;
- uma opção indisponível sempre explica por quê;
- nenhuma plataforma reduz as escolhas das demais.

## 7. Semântica de CTA

Pode existir um **objetivo semântico** comum — comprar, reservar, saber mais, responder — para ajudar a composição. A tradução final é explícita por placement:

| Objetivo | Instagram orgânico | Facebook orgânico | Google Business | WhatsApp template |
|---|---|---|---|---|
| Comprar | texto/asset; sem botão genérico garantido | post com link; sem botão genérico | `SHOP` ou Offer URL | botão URL predefinido no template |
| Reservar | texto/asset | post com link | `BOOK` | botão URL predefinido |
| Saber mais | texto/asset | post com link | `LEARN_MORE` | botão URL predefinido |
| Responder | comentários/DM fora deste efeito | comentários/mensagem fora deste efeito | não equivalente | até 3 reply buttons do template |

O sistema não deve chamar texto em legenda de “botão”, nem prometer clique onde a API não garante.

## 8. Promoções e cupons

### 8.1 Lugar correto no produto

Promoção e cupom continuam pertencendo ao domínio do orquestrador. O Marketing Nuxt ganha a operação diária em **Ofertas**; o Django Admin permanece como configuração canônica, auditoria e escape hatch, respeitando os componentes e tokens do Unfold.

### 8.2 O que já existe

`Promotion` já contém tipo percentual/fixo/frete grátis, valor, vigência, SKUs, coleções, pedido mínimo, fulfillment, segmentos, aniversário, canais e ativo.

`Coupon` já contém código, promoção, máximo de usos, contador e ativo.

### 8.3 Evolução necessária

O gerenciamento maduro precisa de:

- lifecycle explícito: draft, scheduled, live, paused, expired, archived;
- timezone e regras de borda de vigência;
- conflito/prioridade e possibilidade de combinação;
- limite total e limite por cliente;
- ledger de reserva, aplicação, cancelamento e estorno de cupom;
- lotes de códigos, quando necessário;
- origem da campanha e métricas de uso;
- URL de resgate/claim segura;
- preview da condição comercial em todos os placements;
- trilha de auditoria para mudança após uma campanha ser selada.

`uses_count` isolado não é suficiente para concorrência, uso por cliente e estorno.

### 8.4 Integração com campanha

O plano referencia promoção e, opcionalmente, um cupom. O artefato sela os fatos de apresentação no momento do disparo. Preço e disponibilidade ao clicar continuam sendo resolvidos pelo fluxo transacional atual, não congelados pelo post.

Para Google Offer, o adapter deve passar a suportar `couponCode`, `redeemOnlineUrl` e `termsConditions`. A proibição atual só pode ser removida quando o claim/redemption do cupom estiver seguro e testado ponta a ponta.

## 9. Arquitetura de execução

### 9.1 Fronteiras

- Marketing API: CRUD de plano, placements, previews e validação.
- Capability service: provider + connector + connection snapshots.
- Media pipeline: ingestão, inspeção, transforms não destrutivos e derivados por placement.
- Artifact sealer: payload imutável por lane.
- Outbox/dispatcher: efeito externo idempotente.
- Reconciler: resolve estados desconhecidos e importa estado remoto relevante.
- Projection: leitura agregada do bundle para o Nuxt.

### 9.2 Regra de agendamento

O operador escolhe uma janela comum, mas o sistema decide por adapter:

- usar agendamento nativo quando ele é confiável, cancelável e observável;
- ou reter no outbox local e publicar na hora.

A decisão fica gravada no placement. Nunca se mistura agendamento nativo e local sem mostrar qual sistema é a fonte de verdade.

### 9.3 Versionamento

Qualquer expansão do payload requer:

- nova versão de capability schema;
- nova versão de artifact schema;
- leitura compatível de artefatos antigos;
- fixture de golden contract;
- rollout por feature flag/connection;
- migração que não reenvia campanha antiga.

## 10. Plano de implementação

Cada pacote deve caber em PR pequeno, manter os efeitos atuais estáveis e passar seus gates antes do seguinte.

### WP-01 — Capability Registry V2

Área:

- `shopman/shop/services/marketing_capabilities.py`;
- nova representação tipada de provider/connector/connection/placement;
- projeção e contratos de teste.

Entrega:

- catálogo completo, versionado e server-driven;
- estado de implementação/readiness distinto;
- nenhuma nova publicação externa.

Fundação implementada nesta branch:

- inventário tipado e versionado em `marketing_provider_capabilities.py`;
- projeção aditiva `provider_capabilities` nas opções do composer;
- catálogo teórico separado da allow-list executável existente;
- TikTok documentado como `dormant`/`gated`, sem tornar-se destino válido;
- testes de formatos, mídia, CTA e não ampliação acidental dos efeitos externos.

### WP-02 — Conexões múltiplas

Área:

- modelo de conexão;
- discovery de Facebook Pages, Instagram accounts e Google locations com paginação;
- bridge das settings atuais para conexões default;
- tela Plataformas.

Entrega:

- seleção por conta concreta;
- health, permissões e última atualização de capabilities.

### WP-03 — Plano, placements e bundle

Área:

- modelos/migrations;
- API de draft e autosave;
- idempotency namespace por placement;
- projeção agregada.

Entrega:

- dois formatos da mesma plataforma e múltiplas contas na mesma campanha;
- estados independentes sem alterar adapters ainda.

### WP-04 — Media pipeline

Entrega:

- slots tipados;
- inspeção de formato/duração/dimensões;
- crops/derivados por placement;
- upload e lifecycle de container;
- preview usando o mesmo artefato que será selado.

### WP-05 — Instagram completo

Ordem segura:

1. vídeo único;
2. Reel;
3. carrossel;
4. Story em vídeo;
5. campos avançados elegíveis.

Cada formato entra com fixture, contract test, sandbox proof e feature flag própria.

### WP-06 — Facebook completo

Entrega:

- múltiplas Pages;
- vídeo e Reel;
- upload/status;
- rascunho/agendamento onde adotado;
- collaborator/targeting apenas quando confirmado para a conexão.

### WP-07 — Google Business completo

Entrega:

- múltiplas locations e paginação;
- Offer com cupom/URL/termos após gate transacional;
- mídia conforme capacidade real;
- edição/exclusão e insights como operações explícitas.

### WP-08 — WhatsApp templates

Entrega:

- catálogo de contas e templates/flows;
- schema de variáveis, header e botões;
- preview fiel;
- elegibilidade/opt-in e volume antes da aceitação;
- manutenção do envio idempotente por destinatário.

### WP-09 — Composer V2

Área:

- `surfaces/marketing-nuxt` sem alterar package manifests salvo necessidade aprovada;
- wizard de cinco passos;
- previews por placement;
- revisão exata e acompanhamento do bundle.

O rollout pode coexistir com o composer atual sob flag até a paridade de fluxos existentes.

### WP-10 — Ofertas

Entrega:

- página Ofertas no Nuxt;
- lifecycle de promoção;
- criação/pausa/duplicação;
- cupom, ledger e claim;
- integração com Google Offer e campanhas.

### WP-11 — Cutover e remoção

Somente após telemetria e paridade:

- migrar drafts válidos;
- manter leitura de histórico antigo;
- remover projeções e componentes obsoletos;
- apagar flags depois do período de rollback.

## 11. Gates de qualidade

### Backend

- contract/golden tests do catálogo;
- testes de compatibilidade de artifact antigo;
- testes de idempotência por placement;
- testes de partial success e reconciliação;
- testes de timezone e agendamento;
- testes concorrentes de cupom;
- `make test` nos pacotes afetados.

### Admin

Qualquer mudança em ModelAdmin/template do backstage deve passar:

- `make admin`;
- verificação de widgets, helpers e tokens do Unfold;
- viewport desktop e mobile;
- estados vazio, loading, erro e permissão negada.

### Marketing Nuxt

- lint/typecheck/test/build;
- axe/teclado nos cinco passos;
- provas visuais mobile e desktop;
- matriz de cada formato e estado de readiness;
- nenhuma opção ou copy crítica mantida em duplicidade com o backend.

### Sandbox/produção controlada

- conexão dedicada por provider;
- publicação canário por formato;
- confirmação no provider e no ledger;
- cancelamento/agendamento quando aplicável;
- métricas de erro, unknown state, latência e retries.

## 12. Métricas de sucesso

- tempo mediano até uma campanha pronta;
- número de correções depois da tela de revisão;
- taxa de abandono por passo;
- placements escolhidos por campanha;
- falhas detectadas antes do dispatch;
- partial failures e unknown outcomes por provider;
- tempo até recuperação/retry;
- adoção e conversão de ofertas/cupons;
- redução de operações manuais fora do Shopman.

## 13. Área assumida e sobreposição verificada

Nesta primeira entrega foi assumido somente:

- `docs/plans/MARKETING-V2-CAPABILITY-COMPOSER-2026-09-26.md`.

Nenhum arquivo do checkout principal foi editado. Nenhum código de produção, migration, template, manifest ou lockfile foi alterado.

Antes da edição foram verificados:

- todos os worktrees locais;
- os worktrees históricos `claude/wp-mkt-facebook-google`, `claude/marketing-previa-da-revisao-sem-exemplo` e `claude/mkt-facebook-frente-a`, todos limpos e sem diff próprio em relação ao `origin/main` atualizado;
- PRs abertos no GitHub, sem feature PR ativa de Marketing;
- PRs de dependências #968, #880 e #721, que tocam `surfaces/marketing-nuxt/package.json` e lockfile.

Por isso esta entrega evita manifests e lockfiles. Os próximos WPs devem repetir a checagem de sobreposição imediatamente antes de editar suas áreas.

## 14. Fontes oficiais consultadas

- Meta — Instagram Content Publishing API: <https://developers.facebook.com/documentation/instagram-platform/content-publishing>
- Meta — Instagram API workspace: <https://www.postman.com/meta/instagram/overview>
- Meta — Facebook Pages posts: <https://developers.facebook.com/documentation/pages-api/posts>
- Meta — Facebook Reels publishing: <https://developers.facebook.com/documentation/video-api/guides/reels-publishing>
- Meta — Facebook API workspace: <https://www.postman.com/meta/facebook/overview>
- Google — Create Posts: <https://developers.google.com/my-business/content/posts-data>
- Google — Local Posts resource: <https://developers.google.com/my-business/reference/rest/v4/accounts.locations.localPosts>
- Google — Locations list (Business Information v1): <https://developers.google.com/my-business/reference/businessinformation/rest/v1/accounts.locations/list>
- ManyChat — WhatsApp Message Templates: <https://help.manychat.com/hc/en-us/articles/14281326740124-How-to-use-WhatsApp-Messages-Templates-in-Manychat>
- ManyChat — API token and account parameters: <https://help.manychat.com/hc/en-us/articles/14959510331420-How-to-generate-a-token-for-the-Manychat-API-and-where-to-get-parameters>
- TikTok — Photo post: <https://developers.tiktok.com/docs/en/content-posting-api-reference-photo-post>
- TikTok — Direct post: <https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post>
