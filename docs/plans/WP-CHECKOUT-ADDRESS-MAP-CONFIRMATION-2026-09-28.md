# WP-CHECKOUT-ADDRESS-MAP-CONFIRMATION — confirmação visual do ponto de entrega

> **Status:** READY — autocontido, pronto para execução
>
> **Data da especificação e do benchmark:** 2026-09-28
>
> **Superfície principal:** `surfaces/storefront-nuxt`, checkout mobile-first
>
> **Prioridade sugerida:** P1 de conversão/confiabilidade, executável sem mudança de domínio
>
> **Risco:** médio (permissão, Google Maps, endereço e cálculo de entrega)
>
> **Rollout:** protegido por kill switch; sem migração e com fallback para o fluxo atual
>
> **Dependências já disponíveis:** Places, reverse geocode, `AddressPicker`, mapa/pin, cálculo canônico de zona

## 1. Resultado esperado

Quando a pessoa tocar em **“Usar minha localização”**, o checkout deve responder
imediatamente, resolver sua posição e abrir uma confirmação visual acolhedora:
mapa claro, pouco saturado, pin da marca, resumo textual e a pergunta inequívoca
**“É aqui que vamos entregar?”**. A pessoa pode mover o mapa para corrigir o ponto,
confirmar ou voltar para a busca — sem perder o que já fez.

Uma sugestão de busca que trouxer coordenadas deve passar pela mesma confirmação
visual antes dos campos de número, complemento e instruções. Endereço salvo continua
em um toque: não se força mapa em toda recompra.

O mapa é uma camada de confiança sobre o contrato existente; **não vira fonte de
verdade paralela**. Endereço, coordenadas, taxa e cobertura continuam fluindo pelo
contrato canônico `delivery_address_structured` e pelo motor de entrega do Core.

## 2. Bootstrap obrigatório do executor

Antes de editar:

1. Criar worktree própria a partir de `origin/main`; nunca escrever no checkout principal.
2. Ler integralmente:
   - `CLAUDE.md`;
   - este WP;
   - `docs/plans/ADDRESS-UX-PLAN.md` (spec canônica de endereço);
   - `docs/plans/DELIVERY-GEOCODING-AND-FEEDBACK-PLAN.md`;
   - `docs/reference/data-schemas.md`, especialmente `delivery_address_structured`;
   - `surfaces/storefront-nuxt/app/components/AddressPicker.vue`;
   - `surfaces/storefront-nuxt/app/presentation/address.ts`;
   - `surfaces/storefront-nuxt/app/composables/useGoogleMaps.ts`;
   - `surfaces/storefront-nuxt/app/components/BottomSheet.vue`;
   - `shopman/storefront/api/geocode.py`;
   - `shopman/shop/services/geocoding.py`;
   - o passo de endereço e `applyDeliveryDraft()` em
     `surfaces/storefront-nuxt/app/pages/finalizar.vue`.
3. Verificar novamente se existe `AGENTS.md` no caminho entre a raiz e os arquivos.
   Na auditoria de 2026-09-28 não existia nenhum; `CLAUDE.md` era a regra aplicável.
4. Não “atualizar” este WP para combinar com uma implementação divergente. Divergência
   relevante pede decisão explícita no PR ou follow-up, não alteração silenciosa do contrato.

## 3. Escopo

### In

- confirmação em mapa para **“Usar minha localização”** no checkout;
- confirmação em mapa para sugestão do Places que contém lat/lng;
- reaproveitamento do mapa, pin e reverse geocode existentes;
- mapa dessaturado alinhado aos tokens semânticos da marca;
- correção do ponto no mapa e persistência da coordenada efetivamente confirmada;
- estados de permissão, precisão, loading, timeout, erro e fallback;
- preservação dos campos e do cálculo canônico de área/taxa;
- acessibilidade por teclado, leitor de tela, zoom e mobile;
- observabilidade sem coordenadas, endereço, query ou `place_id`;
- testes unitários, de componente, integração, E2E, a11y e visuais;
- kill switch, rollout, smoke e rollback;
- atualização das specs e do aviso de privacidade afetados pela entrega.

### Out

- pedir GPS automaticamente ao abrir home, checkout ou app;
- exigir mapa para endereço salvo já escolhido;
- substituir Google Maps/Places ou criar abstração multi-provedor “para o futuro”;
- criar cálculo de distância, zona ou taxa no cliente;
- criar nova tabela/modelo/migração de endereço;
- guardar `accuracy`, histórico de movimentos do pin ou permissão no banco/localStorage;
- redesenhar toda a conta de endereços;
- copiar ilustração, vermelho, iconografia ou identidade visual do iFood;
- reproduzir testes A/B do iFood sem necessidade local;
- rastreamento do entregador ou alteração de endereço após o pedido;
- resolver neste WP a cascata Google → BrasilAPI → Nominatim do plano de geocoding.

## 4. Invariantes

1. `delivery_address_structured` segue como endereço estruturado canônico de sessão e pedido.
2. A `DeliveryZoneRule`/Core segue como autoridade de cobertura e taxa. O mapa não decide zona.
3. Reverse geocode enriquece partes textuais; **não pode deslocar o ponto confirmado**.
4. Nenhuma permissão de localização é pedida antes de gesto explícito.
5. Falha, recusa de permissão ou ausência do Maps nunca bloqueia busca/manual/retirada.
6. O browser key é público e restrito por domínio; o server key nunca vai ao cliente.
7. Endereço salvo permanece rápido; não transformar recompra em ritual repetitivo.
8. Complemento e instruções escritos pela pessoa nunca são apagados por geocoder.
9. Acessibilidade não depende de enxergar nem arrastar o mapa.
10. Rollback do recurso não muda nem invalida endereços já salvos.

## 5. Auditoria do estado atual (baseline em `origin/main` `2f207410e`)

| Área | Estado verificado | Consequência para este WP |
|---|---|---|
| Componente | `AddressPicker.vue` é compartilhado entre checkout e conta. | Evoluir o componente canônico; não duplicar picker no checkout. |
| Busca | Places com `includedRegionCodes=['br']`, `pt-BR` e bias da loja; ViaCEP é fallback silencioso para CEP. | Preservar ordem e sessão do autocomplete. |
| Sugestão | Places preenche rascunho e vai direto ao formulário. | Inserir a confirmação de mapa entre sugestão e formulário quando houver coordenadas. |
| GPS | `getCurrentPosition(enableHighAccuracy: true, timeout: 10000)` → reverse geocode → banner “Você está aqui?”. | Trocar o banner por mapa confirmável; tratar `accuracy` e códigos de erro. |
| Coordenada GPS | `mergeReverseGeocode` adota lat/lng do resultado Google. | Risco de trocar o GPS cru pelo centróide do geocoder; corrigir no contrato. |
| Mapa | Bottom-sheet de `85dvh`, `zoom: 17`, UI reduzida e `Marker` arrastável; abre apenas em “Ajustar no mapa”. | Reusar lifecycle e sheet, antecipar o mapa e melhorar interação/estilo. |
| Estilo | Mapa usa estilo Google padrão; pin não consome tokens da marca. | Aplicar basemap neutro/dessaturado e pin/controles semânticos. |
| Reverse geocode | `POST /api/v1/geocode/reverse/`, público, 30/min, server key, cache 24h. | Contrato suficiente; não criar endpoint concorrente. |
| Persistência | `AddressSelection` alimenta `delivery_address_structured`; lat/lng/place_id já chegam ao pedido/endereço salvo. | Estender apenas o vocabulário existente (`coordinates_source`), sem novo store. |
| Zona | `applyDeliveryDraft()` envia endereço ao Core e mostra verificando/atende/fora da área + retirada. | Preservar; disparar só após endereço textual válido e ponto confirmado. |
| Endereço salvo | Pré-seleção e escolha em um toque; edição reaproveita o picker. | Não forçar nova confirmação cartográfica em toda compra. |
| A11y | `BottomSheet` já herda foco, Esc e scroll lock da primitiva Reka. O ajuste espacial depende do drag do marker. | Oferecer operação por teclado e alternativa textual equivalente. |
| Testes | Há testes puros de address, guardrails e jornada alpha, mas não há suíte dedicada ao mapa/permissão. | Criar cobertura determinística e não depender de tiles reais nas baselines. |
| Observabilidade | Falhas do Google já viram evento/alerta operacional; cliente só possui canal de erro sanitizado. | Acrescentar eventos allow-listed; não abusar do canal de erros. |
| Privacidade | A política pública cita Google Fonts/Sentry, mas não explica Maps/Places/geolocalização. | Atualização do aviso é gate de rollout, não follow-up opcional. |

### Lacunas que este WP não deve mascarar

- `ADDRESS-UX-PLAN.md` diz “mapa sob demanda”, mas também ilustra mapa após seleção;
  este WP refina a decisão: “sob demanda” continua verdadeiro porque o mapa só carrega
  depois de GPS explícito ou escolha de sugestão, nunca na abertura do checkout.
- ViaCEP não fornece coordenada no cliente. Sem lat/lng, não inventar um pin: seguir ao
  formulário e deixar o backend geocodificar para a taxa como já faz.
- `is_verified` tem semântica histórica própria. Este WP não a redefine.

## 6. Benchmark iFood atual

### 6.1 Método e escala de confiança

O iFood é a principal referência comportamental brasileira, não uma especificação a ser
copiada. A auditoria registra superfície, data e nível de confiança para evitar que uma
tela antiga vire “verdade atual”.

- **Alta:** observação direta na superfície indicada ou declaração oficial recente e explícita.
- **Média:** fonte oficial recente descreve o comportamento, mas a etapa não foi observada diretamente.
- **Baixa/inferência:** dedução coerente a partir de sinais atuais; nunca tratada como fato de tela.

Não foi aceita permissão de localização, não foi salvo endereço e nenhum pedido foi criado
durante a observação. Dados de endereços já presentes na sessão foram deliberadamente
omitidos deste documento.

### 6.2 Evidências

| Evidência | Data/superfície | O que sustenta | Confiança |
|---|---|---|---|
| Observação direta de [`ifood.com.br/inicio`](https://www.ifood.com.br/inicio) | 2026-09-28, web desktop responsivo | modal, busca, sugestões, busca pelo mapa, mapa/pin, campos e retorno | Alta |
| [Bastidores: como funciona um pedido do iFood](https://institucional.ifood.com.br/institucional/como-funciona-um-pedido-do-ifood/) | publicado 2025-07-11, app | último endereço + posição GPS e aviso quando divergem | Alta para o princípio; média para a UI atual |
| [Comércio perto de mim](https://institucional.ifood.com.br/clientes/comercio-perto-de-mim/) | publicado 2026-02-27, app Android/iOS | permissão, localização precisa e alternativa manual | Alta para comportamento descrito |
| [Gerenciamento de conta e cadastro](https://institucional.ifood.com.br/ajuda/conta-e-cadastro-ifood/) | publicado 2026-04-01, app | pedido de permissão de localização na entrada do app | Alta para onboarding do app; não transplantar automaticamente |
| [Entrega rápida perto de mim](https://institucional.ifood.com.br/clientes/entrega-rapida-perto-de-mim/) | conteúdo oficial rastreado em 2026, app | endereço no topo, “Usar Localização Atual” e endereços anteriores em um toque | Média-alta |
| [Política de privacidade do cliente](https://ifood-privacy-assets.ifood.com.br/cms/Cliente_3_Versao_db8af35585.pdf) | versão histórica disponível, política | localização manual ou por GPS/rede, confirmada pela pessoa | Alta para o princípio; não prova layout atual |
| [Boas práticas de Shipping](https://developer.ifood.com.br/pt-BR/docs/guides/modules/shipping/best-practices-troubleshooting/boas-praticas-e-troubleshooting/) | documentação técnica rastreada em 2026 | cobertura, divergência regional e necessidade de validar coordenadas | Alta para domínio; não prova UX do cliente |

Telas de tutoriais de 2021–2023 foram encontradas, mas **não usadas como evidência da UI
atual**. O próprio iFood declara que opções variam por localização e versão; a jornada pode
estar em A/B.

### 6.3 Jornada web diretamente observada

1. **Entrada/seleção:** modal central com pergunta “Onde você quer receber seu pedido?”,
   busca e, conforme a sessão, endereços salvos com ações. Em outra carga do mesmo fluxo,
   “Usar minha localização” apareceu logo abaixo da busca.
2. **Busca:** campo “Buscar endereço e número”; sugestões Google mostram linha principal
   e bairro/cidade/UF/país. A query permanece ao voltar.
3. **Escape da busca:** ao fim das sugestões há “Não achei meu endereço” com ação
   “Buscar pelo mapa”.
4. **Seleção:** escolher sugestão com número **não abre o formulário primeiro**. Abre um
   mapa claro, com pin central, título “ENDEREÇO”, pergunta “Você está aqui?” e instrução
   “Ajuste a localização”.
5. **Decisão:** CTA destacado “Confirmar localização”; voltar retorna à busca e preserva
   o texto/sugestões.
6. **Detalhes:** depois de confirmar o ponto, a mesma superfície mostra endereço resumido,
   número preposto, complemento com helper “Apartamento/Bloco/Casa”, ponto de referência,
   favoritos Casa/Trabalho e “Salvar endereço”.
7. **Edição/retorno:** voltar do formulário retorna ao mapa; voltar do mapa retorna à
   busca. O endereço não foi salvo na auditoria.

### 6.4 Jornada app — verificado versus inferido

| Etapa | Evidência atual | Classificação |
|---|---|---|
| Endereço atual no topo e troca por toque | Fonte oficial 2025–2026 | Verificado por fonte oficial |
| Lista de endereços anteriores em um toque | Fonte oficial 2026 | Verificado por fonte oficial |
| Ação “Usar Localização Atual” | Fonte oficial 2026 + CTA equivalente observado na web | Verificado por fonte oficial; UI nativa não observada |
| Prompt do sistema operacional | Fonte oficial 2026 | Verificado para app; texto exato pertence ao SO |
| Checagem último endereço × GPS | Fonte oficial 2025 | Verificado como comportamento; microcopy/layout atuais desconhecidos |
| GPS conduz ao mesmo mapa/pin observado na web | Coerente com a arquitetura e a política, mas não observado nesta auditoria | Inferência — não copiar como fato |
| Erro de fora de área aparece antes do carrinho | Lojas são filtradas pela região nas fontes oficiais; tela de erro não observada | Inferência parcial |
| Edição mantém carrinho e retorna ao checkout | Comportamento esperado de produto; não observado no app | Inferência — requisito local, não benchmark factual |

### 6.5 Princípios aproveitáveis — sem copiar identidade

1. **Localização é uma proposta, não uma decisão silenciosa.** O mapa torna a proposta
   legível antes de salvá-la.
2. **Ordem das decisões:** encontrar endereço → confirmar ponto → completar detalhes →
   salvar/usar. Não pedir tudo de uma vez.
3. **O mapa é uma etapa de confiança**, não decoração permanente do formulário.
4. **Busca e GPS convergem** para um mesmo ponto confirmável.
5. **Voltar não apaga intenção.** Query e contexto sobrevivem.
6. **Há saída quando o catálogo geográfico falha:** busca pelo mapa/manual.
7. **Último endereço é conveniência, não presunção.** Divergência merece aviso, não troca automática.
8. **Cobertura deve aparecer cedo**, antes da cobrança.

Não copiar: vermelho iFood, mascote, ilustração, composição pixel a pixel, nomes de
componentes ou microcopy integral. A Nelson usa seus tokens, seu tom e sua hierarquia.

## 7. Comparação passo a passo e decisões do WP

| Etapa | iFood atual/evidência | Shopman hoje | Decisão obrigatória |
|---|---|---|---|
| Entrada | Busca, salvos e localização como escolhas claras | Mesmo repertório | Manter; não pedir GPS sozinho. |
| Busca | Sugestões em duas linhas + escape “buscar pelo mapa” | Sugestões em duas linhas; manual como escape | Manter manual e acrescentar acesso claro ao mapa quando houver ponto inicial. |
| Sugestão com coords | Mapa antes dos detalhes | Formulário antes; mapa opcional depois | Abrir confirmação de mapa primeiro. |
| GPS | Localização atual é ação explícita | Ação explícita + banner textual | Abrir mapa com ponto GPS, accuracy e reverse em paralelo. |
| Pin | Ponto central e mapa ajustável | Marker arrastável | Mapa se move sob pin central; manter alternativa por teclado. |
| Pergunta | “Você está aqui?” | Banner usa a mesma pergunta, mapa não | Usar copy própria: “É aqui que vamos entregar?” |
| Número | Depois do ponto; já vem preenchido quando disponível | Foco guiado já faz isso | Preservar; se vazio, focar número após mapa. |
| Complemento/referência | Campos separados | Complemento + `delivery_instructions` | Não criar `reference`; renomear/apresentar o campo canônico como “Referência e instruções”. |
| Favorito | Casa/Trabalho antes de salvar | Etiqueta depois de salvar/pedido | **Não copiar.** Manter etiqueta pós-salvamento conforme spec canônica. |
| GPS × salvo | iFood declara comparar e pedir revisão | Sem leitura passiva no checkout | Não acessar GPS passivamente; futuro só com opt-in claro. |
| Fora da área | Região filtra oferta; detalhes da tela não verificados | Core verifica cedo e oferece retirada | Manter solução local, que já é mais explícita e recuperável. |
| Voltar | Busca ↔ mapa ↔ detalhes preservam contexto | Sheet fecha; fluxo não tem mapa intermediário | Implementar back determinístico sem zerar rascunho. |
| Falha Maps | Alternativa manual recomendada oficialmente | Busca/manual e fallback já existem | Nunca bloquear; cair no formulário atual com explicação acionável. |

## 8. Fluxo-alvo

### 8.1 “Usar minha localização”

1. Gesto no CTA.
2. Estado imediato “Pedindo sua localização…”; somente então chamar Geolocation API.
3. Em sucesso, preservar `{latitude, longitude, accuracy}` **transitoriamente**.
4. Em paralelo:
   - importar biblioteca Maps;
   - chamar reverse geocode para obter o endereço candidato.
5. Abrir o sheet assim que o mapa puder representar o ponto; o texto pode aparecer como
   skeleton até o reverse terminar.
6. Centralizar no GPS cru. Mostrar círculo de precisão e mensagem proporcional à accuracy.
7. Perguntar “É aqui que vamos entregar?” e oferecer:
   - `Confirmar este ponto` (primário);
   - `Voltar e buscar endereço` (secundário);
   - `Tentar localizar novamente` quando a precisão for baixa.
8. Mover o mapa move o ponto sob o pin central; não chamar reverse a cada frame.
9. Ao confirmar, executar no máximo um reverse geocode para o centro final se o ponto mudou.
10. Mesclar partes textuais, mas gravar lat/lng do centro confirmado, não o centróide devolvido.
11. Ir ao formulário; focar número se ausente, complemento se número já existir.
12. Confirmar endereço → `AddressSelection` → draft do checkout → Core calcula cobertura/taxa.

### 8.2 Endereço selecionado na busca

1. Places devolve partes, `place_id` e lat/lng.
2. Se ambos lat/lng existem, abrir o mesmo sheet centrado no resultado.
3. Se a pessoa não mover o mapa, confirmar preserva as partes do Places e a coordenada
   apresentada; reverse adicional é dispensável.
4. Se mover, reverse geocode uma vez no centro final e aplicar a regra do ponto confirmado.
5. Se a sugestão não tem coordenadas (incluindo ViaCEP), seguir ao formulário atual; não
   inventar mapa nem endpoint forward público neste WP.

### 8.3 Endereço salvo

- Seleção continua imediata e dispara a cotação atual.
- “Editar” pode usar o mapa existente quando há coordenadas.
- Não ler GPS só para comparar com o salvo.
- Se a pessoa voluntariamente escolher “Usar minha localização”, isso inicia endereço novo;
  nunca sobrescreve um salvo sem a confirmação e o save já existentes.

### 8.4 Fora da área

Após confirmação do formulário:

1. mostrar “Verificando se entregamos aqui…” enquanto `applyDeliveryDraft()` roda;
2. se coberto, mostrar taxa/distância atuais;
3. se fora e houver retirada, oferecer “Mudar para retirada” em um toque;
4. se fora e sem retirada, oferecer outro endereço e WhatsApp;
5. nunca desenhar ou inferir a zona no mapa do cliente;
6. editar o pin/endereço limpa a resposta anterior e cota novamente pelo Core.

### 8.5 Retorno e cancelamento

| Origem do mapa | Voltar/Esc | Confirmar |
|---|---|---|
| GPS a partir da busca | volta à busca, preservando estado anterior | vai ao formulário |
| Sugestão Places | volta à lista com query e sugestões | vai ao formulário |
| “Ajustar no mapa” do formulário | volta ao formulário sem aplicar ponto novo | atualiza o mesmo rascunho |
| Edição de salvo | volta à edição sem persistir | atualiza o rascunho; só “Salvar alterações” persiste |

Fechar nunca envia PATCH/POST de endereço. Somente o CTA explícito aplica o ponto.

## 9. Estados e transições

Estados mínimos, explícitos e testáveis:

```text
saved | search | form
  └─ location_permission_pending
       ├─ location_resolving
       │    ├─ map_loading + reverse_loading
       │    │    ├─ map_ready
       │    │    └─ map_fallback
       │    └─ location_error
       └─ permission_denied

search suggestion with coords ──> map_loading ──> map_ready ──> form
form “ajustar” ──> map_ready ──> form
form confirm ──> zone_quote_pending ──> zone_ok | zone_out | quote_deferred
```

Regras:

- cada operação assíncrona tem texto/loader visível em menos de um frame;
- respostas antigas de search/reverse/quote não vencem a operação mais recente;
- botão primário fica idempotente durante pending;
- fechar sheet cancela/ignora resultado tardio e remove listeners;
- nenhum estado de erro elimina query, rascunho, carrinho ou opção de retirada.

## 10. Precisão e divergência

`GeolocationCoordinates.accuracy` é sinal de incerteza; não é garantia de que a porta
correta foi encontrada. Usar faixas configuradas numa função pura, não números espalhados:

| Accuracy | Tratamento |
|---|---|
| `<= 80 m` | “Localização com boa precisão”; círculo discreto. |
| `> 80 m` e `<= 250 m` | aviso “O ponto pode estar alguns metros fora. Confira no mapa.” |
| `> 250 m` | aviso forte + `Tentar novamente` + busca como alternativa; não bloquear confirmação. |
| ausente/não finita | tratar como baixa precisão, sem expor número inventado. |

Opções recomendadas do request: `enableHighAccuracy: true`, `timeout: 10000`,
`maximumAge: 30000`. Uma segunda tentativa só acontece por gesto em “Tentar novamente”; não
manter `watchPosition` contínuo.

### GPS cru versus reverse geocode

- O pin inicial é o GPS cru.
- O endereço textual vem do reverse.
- A geometria devolvida pelo provedor pode ser rooftop/centróide e serve como evidência,
  **não como substituta silenciosa do pin**.
- Se a distância entre GPS cru e geometria do reverse exceder `max(accuracy, 120 m)`, mostrar
  “O endereço encontrado não parece bater exatamente com o ponto. Confira antes de continuar.”
- A distância é calculada no cliente apenas para feedback de consistência, nunca para taxa/zona.
- Para busca, não pedir GPS para comparar. Comparar apenas coordenada da sugestão com eventual
  novo centro movido pela pessoa.

Não persistir accuracy, distância de ajuste ou a trilha de posições. Telemetria usa somente
faixas (`good`, `medium`, `low`, `unknown`; `0_50`, `50_200`, `200_plus`).

## 11. Contratos e fonte de verdade

### 11.1 Contrato persistido

Continuar usando `AddressDraft` → `AddressSelection` → `StructuredAddressProjection` →
`delivery_address_structured`. Não criar `mapAddress`, `gpsAddress` ou store global paralelo.

Reutilizar o vocabulário já documentado em `data-schemas.md`:

```ts
type CoordinatesSource = 'pin' | 'geocoded' | 'saved'
```

- endereço salvo: `saved`;
- ponto visualmente confirmado, vindo de GPS ou busca: `pin`;
- coordenada obtida apenas por geocoding textual: `geocoded`;
- sem coordenada: campo ausente.

Adicionar `coordinates_source` aos tipos/allow-lists atuais que ainda não o transportam.
Não alterar significado de `is_verified` neste WP.

### 11.2 Reverse geocode

Manter request e response atuais:

```http
POST /api/v1/geocode/reverse/
{"lat": -23.31, "lng": -51.16}
```

O endpoint continua sendo enriquecedor textual. No cliente, criar função pura equivalente a:

```ts
mergeReverseAtConfirmedPoint(draft, reverseResult, confirmedPoint)
```

Ela preserva complemento/instruções, aplica partes textuais e termina forçando
`latitude/longitude = confirmedPoint`. Um reverse atrasado não pode mover o pin.

### 11.3 Estado transitório do mapa

Pode existir dentro do componente/composable, nunca persistido:

```ts
interface MapConfirmationDraft {
  origin: 'geolocation' | 'places' | 'adjust'
  initialPoint: { lat: number, lng: number }
  centerPoint: { lat: number, lng: number }
  accuracyM: number | null
  addressCandidate: AddressDraft
  moved: boolean
}
```

### 11.4 Chaves e provedores

- `useGoogleMaps()` continua carregando o browser key, restrito por domínio no Google Cloud.
- `server_api_key()` continua exclusivo do backend.
- Não colocar chave em evento, log, screenshot ou fixture.
- Preservar atribuição/termos Google visíveis; estilo não pode ocultá-los.

## 12. Especificação visual

### 12.1 Composição

- Reusar `BottomSheet`, `85dvh` no mobile e largura máxima coerente no desktop.
- Header: título **“Confirme o ponto da entrega”**; descrição curta e orientada à ação.
- Mapa ocupa a área flexível; nenhum formulário longo por cima dele.
- Pin visual fixo no centro; mapa se move por baixo.
- Card/resumo textual persistente junto ao rodapé, sem cobrir atribuição Google.
- Footer: CTA full-width “Confirmar este ponto”; ação secundária de voltar/buscar.
- Loading mantém dimensões estáveis para não saltar layout.

### 12.2 Cores e tokens

- Basemap usa estilo JSON embutido, neutro, com cores absolutas e baixa saturação; não
  depender de configuração manual em Google Cloud para o primeiro rollout.
- Reduzir ruído de POIs (`simplified`/`off` onde irrelevante), mantendo ruas, parques,
  água, hospitais e labels legíveis.
- Não aplicar `filter: grayscale()`/`saturate()` ao canvas: isso também degrada labels,
  controles e atribuição.
- Pin, accuracy ring, botões, foco e card usam `--primary`, `--primary-foreground`,
  `--background`, `--card`, `--border`, `--ring`, `--muted` e `--muted-foreground`.
- Pin precisa de contorno/halo; não depender só da cor para ser encontrado.
- Fornecer estilos light e dark explícitos. Se o mapa dark não estiver validado no primeiro
  slice, manter mapa claro dentro de superfície clara intencional — nunca inverter via filtro.

A API oficial do Google permite JSON styles por `featureType`/`elementType` e recomenda não
misturar estilo embutido com cloud styling. Referência:
[Style Reference for Maps JavaScript API](https://developers.google.com/maps/documentation/javascript/style-reference).

### 12.3 Movimento

- Respeitar `prefers-reduced-motion`.
- Sem bounce obrigatório do pin.
- Pan iniciado pela pessoa não dispara reverse continuamente.
- Ao confirmar, feedback “Confirmando o ponto…” permanece no CTA/sheet.

## 13. Acessibilidade

Alvo: WCAG 2.2 AA, inclusive teclado, foco não obscurecido e alternativa ao gesto de drag.
Referência normativa: [WCAG 2.2](https://www.w3.org/TR/wcag/).

Requisitos:

1. Foco entra no título/resumo, não é sequestrado pelo canvas.
2. Mapa recebe nome acessível: “Mapa para ajustar o ponto de entrega”.
3. Teclado consegue focar o mapa, mover com setas e sair com Tab/Shift+Tab; nenhuma trap.
4. Zoom `+/-` permanece operável; Esc volta sem aplicar.
5. Para quem não usa mapa, resumo textual + busca/manual produzem resultado equivalente.
6. Texto `aria-live="polite"` anuncia: localização encontrada, baixa precisão, ponto ajustado,
   endereço confirmado e falha recuperável; não anunciar cada pixel de pan.
7. Pin decorativo é `aria-hidden`; o centro atual é descrito pelo texto.
8. CTAs próprios têm pelo menos 44×44 CSS px, foco visível e contraste AA.
9. Accuracy não é comunicada só por círculo/cor.
10. Sheet funciona a 200% e 400% de zoom, orientação landscape e teclado virtual.
11. VoiceOver iOS, TalkBack Android e navegação só por teclado entram na matriz manual.
12. Labels e atribuições Google não podem ser ocultadas pelo footer.

## 14. Privacidade, permissão e segurança

- Just-in-time: chamar `navigator.geolocation` apenas no CTA.
- Antes do prompt, explicar o benefício: confirmar onde entregar; não usar copy coercitiva.
- `PERMISSION_DENIED`: “Não conseguimos acessar sua localização. Você pode buscar o endereço
  ou preencher manualmente.” Se o browser permitir, incluir ajuda curta para liberar nas configurações.
- `POSITION_UNAVAILABLE`: oferecer nova tentativa e busca.
- `TIMEOUT`: oferecer nova tentativa sem loop automático.
- Nenhum log/evento contém lat/lng, endereço, CEP, query, `place_id`, complemento ou instruções.
- Accuracy fica em memória e é descartada ao fechar/confirmar.
- Coordenadas só entram no rascunho canônico depois da confirmação explícita do ponto.
- Não guardar uma cópia extra no localStorage; o draft existente do checkout continua sendo o único.
- Atualizar `app/pages/privacidade.vue` e o snapshot/versionamento legal para explicar, com clareza,
  que Places/Maps recebem requisições de mapa/busca e o IP, e que a localização só é usada após gesto.
- Revisar a restrição HTTP referrer e quotas do browser key antes do rollout; nunca compensar uma
  chave mal restrita escondendo-a no bundle (browser key é publicável por natureza).

## 15. Fallbacks e kintsugi

| Falha | Comportamento obrigatório |
|---|---|
| Geolocation API ausente | explicar e manter busca/manual em foco |
| Permissão negada | nenhuma repetição automática do prompt; busca/manual |
| Timeout/posição indisponível | tentar novamente por gesto ou buscar |
| Maps script falha | card textual atual + formulário; coordenada preservada se obtida |
| Reverse falha após GPS | manter ponto; pedir partes manuais e explicar que o endereço não foi identificado |
| Reverse falha após Places sem movimento | usar partes Places já obtidas |
| Reverse falha após ajuste | não perder o ponto; manter valores anteriores e exigir revisão dos campos |
| Sugestão sem lat/lng | formulário atual, sem mapa forjado |
| Baixa precisão | mapa + círculo + aviso + retry; não bloquear |
| Rate limit 429 | mensagem calma; permitir formulário sem martelar endpoint |
| Fora da área | solução canônica de retirada/outro endereço/WhatsApp |
| Feature flag off | fluxo atual, sem resíduo visual/contratual |

## 16. Microcopy proposta

Copy é proposta de implementação e deve passar pelo gate Omotenashi existente:

| Estado | Copy |
|---|---|
| CTA | Usar minha localização |
| Permissão/pending | Pedindo sua localização… |
| GPS obtido | Encontramos seu ponto. Confira antes de continuar. |
| Título do sheet | Confirme o ponto da entrega |
| Pergunta | É aqui que vamos entregar? |
| Instrução | Mova o mapa até o pin ficar no ponto certo. |
| Boa precisão | Localização com boa precisão. Mesmo assim, confira o pin. |
| Média/baixa | O ponto pode estar alguns metros fora. Confira no mapa. |
| Divergência | O endereço encontrado não parece bater exatamente com o ponto. Confira antes de continuar. |
| CTA confirmar | Confirmar este ponto |
| Voltar | Voltar e buscar endereço |
| Reverse pending | Encontrando o endereço deste ponto… |
| Reverse falhou | Encontramos o ponto, mas não o endereço. Complete os campos para continuar. |
| Campo canônico | Referência e instruções de entrega |
| Helper | Portaria, interfone ou um ponto próximo que ajude a encontrar você. |

Evitar “GPS exato”, “localização perfeita” ou qualquer promessa de precisão que o browser não dá.

## 17. Observabilidade e eventos

### 17.1 Eventos de produto

Adicionar boundary first-party allow-listed no módulo de telemetria existente; não enviar eventos
de produto para `/client-error/`. Não persistir linhas em banco: log estruturado agregado é suficiente.

| Evento | Quando | Propriedades permitidas |
|---|---|---|
| `address.location.requested` | gesto no CTA | `context`, `permission_state` |
| `address.location.resolved` | posição disponível | `accuracy_bucket`, `latency_bucket` |
| `address.location.failed` | erro do browser | `reason=denied|unavailable|timeout|unsupported` |
| `address.map.opened` | sheet visível | `origin=geolocation|places|adjust`, `theme` |
| `address.map.ready` | mapa interativo | `origin`, `latency_bucket` |
| `address.map.fallback` | mapa não abre | `origin`, `reason` allow-listed |
| `address.map.adjusted` | confirmação após movimento | `origin`, `distance_bucket` |
| `address.map.confirmed` | confirmação | `origin`, `accuracy_bucket`, `moved:boolean` |
| `address.map.cancelled` | volta/fecha | `origin`, `stage` |
| `address.zone.result` | Core responde | `result=covered|uncovered|deferred`, `source` |

`context` só pode ser `checkout|account`; nenhuma propriedade livre. Endpoint público deve ser
rate-limited, sanitizar chaves/valores e descartar desconhecidas. O logger não recebe sessão,
customer ref ou payload de endereço.

### 17.2 Sinais operacionais

- Manter `integration.failed` existente para Google Geocoding.
- Acrescentar sucesso/latência em buckets no reverse sem coordenadas no log.
- Dashboard/runbook do rollout deve observar:
  - taxa de falha Maps/reverse;
  - permissão negada e recuperação por busca;
  - mapa aberto → confirmado/cancelado;
  - tempo até mapa pronto;
  - confirmação → zona coberta/fora/deferred;
  - regressão de abandono no passo endereço.
- Alertar somente em falha material sustentada; permissão negada é comportamento normal, não alerta.

## 18. Arquivos prováveis

### Alterar

- `surfaces/storefront-nuxt/app/components/AddressPicker.vue`
- `surfaces/storefront-nuxt/app/presentation/address.ts`
- `surfaces/storefront-nuxt/app/composables/useGoogleMaps.ts`
- `surfaces/storefront-nuxt/app/types/shopman.ts`
- `surfaces/storefront-nuxt/app/pages/finalizar.vue` (somente integração/telemetria necessária)
- `shopman/storefront/api/telemetry.py`
- `shopman/storefront/api/urls.py`
- `shopman/storefront/api/serializers.py`
- `shopman/storefront/api/views.py` e/ou `surface.py` para transportar `coordinates_source`
- `shopman/shop/projections/types.py` se o runtime flag entrar em `public_config`
- `shopman/storefront/presentation/home.py` para o runtime flag
- `surfaces/storefront-nuxt/app/pages/privacidade.vue`
- snapshot legal correspondente em `surfaces/storefront-nuxt/public/documentos-legais/privacidade/`
- `docs/plans/ADDRESS-UX-PLAN.md`
- `docs/reference/data-schemas.md`

### Criar, se mantiver a divisão de responsabilidade simples

- `surfaces/storefront-nuxt/app/components/AddressConfirmationMap.vue`
- `surfaces/storefront-nuxt/app/presentation/addressMap.ts`
- `surfaces/storefront-nuxt/app/composables/useStorefrontTelemetry.ts`
- `surfaces/storefront-nuxt/tests/components/AddressPickerMapConfirmation.test.ts`
- `surfaces/storefront-nuxt/tests/addressMapPresentation.test.ts`
- `surfaces/storefront-nuxt/tests/e2e/addressMap.spec.ts`
- `surfaces/storefront-nuxt/tests/e2e/addressMap.visual.spec.ts`
- teste de API de eventos no diretório `shopman/storefront/tests/api/`

Não criar pacote npm de mapas, provider interface genérica ou store global. Se a extração do
componente deixar mais indireção que clareza, manter o mapa dentro do picker e extrair só a lógica pura.

## 19. Plano de implementação

### Fase 0 — caracterização e fences

- congelar comportamento atual com testes de search/GPS/map/saved/zone;
- registrar payload real de `delivery_address_structured` sem PII;
- provar que feature flag off mantém o DOM/fluxo existente;
- confirmar keys Google, referrer restrictions e quota no ambiente alvo.

### Fase 1 — contrato puro

- introduzir state machine/funções puras de accuracy, distância e merge no ponto;
- transportar `coordinates_source` pelo contrato canônico;
- adicionar estilos de mapa puros light/dark;
- testes unitários completos antes de tocar UI.

### Fase 2 — mapa confirmável

- reusar loader e sheet;
- implementar pin central, círculo de accuracy, resumo e CTAs;
- integrar GPS e Places com o mesmo fluxo;
- garantir cleanup, race cancellation e back determinístico;
- preservar caminho `Ajustar no mapa` existente.

### Fase 3 — falhas, a11y e privacidade

- estados permission/timeout/provider/reverse;
- teclado, screen reader, zoom, reduced motion e touch targets;
- telemetria allow-listed;
- atualização legal e docs canônicas.

### Fase 4 — integração e cobertura

- confirmar Core/zone/retirada;
- unit/component/API/E2E/a11y/visual;
- QA real em Chrome Android e Safari iOS;
- performance e quota.

### Fase 5 — rollout

- alpha/staging com flag on;
- produção inicialmente flag off após deploy;
- smoke real com chave e endereço de teste autorizado;
- ligar em janela de menor tráfego;
- observar pelo menos um ciclo operacional definido pelo owner antes de remover vigilância;
- manter kill switch por no mínimo um release completo.

## 20. Plano de testes

### 20.1 Unitários

- accuracy buckets e valores não finitos;
- haversine/divergência e boundaries;
- merge do reverse mantém coordenada confirmada;
- complemento/instruções/número não são apagados;
- source `pin|geocoded|saved` roundtrip;
- reducer/state machine ignora resposta stale;
- estilos light/dark não ocultam labels/atribuição por configuração;
- telemetria descarta PII e propriedades desconhecidas.

### 20.2 Componentes

Mockar Geolocation API, Maps e `$fetch`:

- permissão granted + boa/média/baixa precisão;
- denied/unavailable/timeout/unsupported;
- GPS abre mapa, não banner antigo;
- Places com coords abre mapa; ViaCEP sem coords abre formulário;
- mapa loading/ready/failure;
- movimento + confirm chama reverse uma vez;
- sem movimento vindo do Places não faz chamada redundante;
- fechar/voltar não aplica ponto;
- back preserva query e rascunho;
- Enter duplo não duplica reverse/save;
- account context não sofre regressão;
- flag off reproduz o comportamento anterior;
- foco inicial, Esc, Tab e live region.

### 20.3 Backend/API

- regressão completa de `/geocode/reverse/` (400/429/502/sucesso/chave não vaza);
- allow-list de `coordinates_source` nos drafts/checkout;
- valores fora do enum recusados ou descartados de forma explícita;
- endpoint de eventos aceita apenas nomes/propriedades previstos, rate-limit e não loga PII;
- checkout/persistência usam lat/lng confirmadas;
- zona segue resolvida pelo Core.

### 20.4 E2E

- Chromium mobile com `context.setGeolocation()` e permissão concedida;
- permissão negada recupera pela busca;
- busca → sugestão → mapa → ajuste → número/complemento → zona;
- busca → mapa → voltar → mesma query;
- GPS → mapa → fora da área → retirada;
- Maps/reverse interceptados em falha → manual → checkout continua;
- salvo continua um toque;
- reload/draft não perde seleção confirmada;
- nenhum pedido é criado pelos testes de seleção; jornada completa usa idempotency existente.

### 20.5 Visuais

Baselines determinísticas usam um fake map local, nunca tiles remotos mutáveis:

- 390×844 e 375×812 (mobile), 768×1024 (tablet), 1280×800 (desktop);
- light e dark;
- loading, ready/boa precisão, baixa precisão, ajustado, denied, reverse-fallback e zone-out;
- 200% zoom e landscape mobile;
- verificar que footer não cobre attribution placeholder.

Além das baselines, fazer smoke manual com Google Maps real e registrar screenshots de review,
sem endereço pessoal e sem commitar tiles/licenças como asset permanente.

### 20.6 Comandos mínimos de gate

```bash
cd surfaces/storefront-nuxt
npm run test:unit
npm run test:component
npm run lint
npm run typecheck
npm run build
npm run test:e2e

cd ../..
make test-storefront
make storefront-e2e args="tests/e2e/alpha/specs/03-personas.spec.ts"
```

Rodar também o gate Omotenashi aplicável e os testes focados de API/serviço alterados.

## 21. Performance e orçamento

- Google Maps continua lazy: nenhum download de tiles/library na abertura do checkout ou na
  escolha de endereço salvo.
- Clique recebe pending visual em até 100 ms.
- Import do Maps e reverse rodam em paralelo no GPS.
- No máximo um reverse inicial e um no confirm após movimento; nunca por evento de drag/idle contínuo.
- Cancelar/fechar remove listeners e referências de Map/marker.
- Nenhuma dependência npm nova.
- O bundle próprio adicional do slice deve permanecer abaixo de 15 KiB gzip; reportar delta real no PR.
- Em staging, medir p75/p95 de `address.map.ready`; p95 acima de 4 s exige análise/fallback, não spinner mudo.
- Timeout de geolocation/reverse permanece finito; nenhuma promise bloqueia o checkout.

## 22. Feature flag, rollout e rollback

### Kill switch

Adicionar boolean runtime `address_map_confirmation_enabled` ao `public_config`, derivado de uma
configuração canônica do servidor. Default `false` em ausência. Não usar query param secreto,
localStorage ou flag duplicada no Nuxt.

Com flag off:

- GPS volta ao candidato textual atual;
- sugestão volta direto ao formulário;
- “Ajustar no mapa” atual continua disponível;
- contratos extras opcionais são ignorados sem quebrar payloads.

### Gates de ativação

- todos os testes verdes;
- revisão de segurança das keys;
- texto de privacidade publicado/versionado;
- smoke Maps/Places/reverse/zone em alpha;
- zero PII em log/eventos, verificado por teste e inspeção;
- owner de checkout aprova screenshots mobile/light/dark;
- não há rollout concorrente do storefront.

### Rollback

1. Desligar `address_map_confirmation_enabled`.
2. Confirmar que busca, GPS textual, manual e salvo funcionam.
3. Não apagar endereços nem coordenadas: o formato persistido continua canônico.
4. Se falha for Maps/reverse, manter fallback e investigar sem bloquear pedidos.
5. Reverter código só se a flag não isolar a regressão; não há migração a desfazer.

## 23. Critérios de aceite

- [ ] **AC-01** — Nenhuma permissão é pedida antes do toque em “Usar minha localização”.
- [ ] **AC-02** — GPS concedido abre mapa confirmável, não preenche/salva silenciosamente.
- [ ] **AC-03** — Accuracy aparece em linguagem humana e baixa precisão tem retry + busca.
- [ ] **AC-04** — Sugestão Places com coordenadas abre o mesmo mapa antes do formulário.
- [ ] **AC-05** — ViaCEP/sugestão sem coordenadas continua pelo formulário sem mapa falso.
- [ ] **AC-06** — Ponto confirmado persiste exatamente o centro/pin escolhido; reverse não o desloca.
- [ ] **AC-07** — Mover/cancelar/confirmar tem back behavior definido e não perde query/rascunho.
- [ ] **AC-08** — Número, complemento e instruções sobrevivem a todo reverse/ajuste.
- [ ] **AC-09** — Endereço salvo permanece em um toque e account picker não regride.
- [ ] **AC-10** — Zona/taxa continuam exclusivamente no Core e aparecem antes do commit.
- [ ] **AC-11** — Fora da área oferece retirada/outro endereço/WhatsApp conforme capacidade atual.
- [ ] **AC-12** — Mapa é dessaturado, legível, light/dark, com pin/CTA da marca e attribution visível.
- [ ] **AC-13** — Teclado, leitor de tela, Esc, zoom, foco e alternativa textual passam a matriz.
- [ ] **AC-14** — Permissão negada, timeout, Maps/reverse/429 falham com saída acionável.
- [ ] **AC-15** — Nenhum evento/log contém endereço, query, CEP, lat/lng, `place_id` ou dados do cliente.
- [ ] **AC-16** — Browser/server keys respeitam boundary e restrições; nenhuma chave privada vaza.
- [ ] **AC-17** — Política de privacidade e specs canônicas refletem o comportamento antes do Live.
- [ ] **AC-18** — Flag off restaura o fluxo anterior sem deploy destrutivo nem migração.
- [ ] **AC-19** — Unit, component, API, E2E, a11y, visual, lint, typecheck e build estão verdes.
- [ ] **AC-20** — PR reporta bundle delta, latências, screenshots e evidência do smoke real.

## 24. Definition of Done

O WP só está concluído quando:

1. 100% dos critérios de aceite têm evidência anexada ao PR.
2. O diff não cria fonte de verdade, cálculo de zona cliente ou dependência nova desnecessária.
3. Há testes de regressão que falham na implementação anterior para os gaps centrais.
4. A experiência foi validada em Android Chrome e iOS Safari reais/em device farm confiável.
5. Screenshots light/dark × mobile/desktop foram revisados.
6. VoiceOver/TalkBack/teclado passaram checklist manual documentado.
7. Privacidade, keys e telemetria passaram review.
8. Flag on e off foram exercitadas no mesmo artefato de build.
9. Alpha/staging completou busca, GPS, pin, zona, retirada e fallback.
10. `ADDRESS-UX-PLAN.md` e `data-schemas.md` refletem a entrega real.
11. Não há mudança de identidade visual copiada do iFood.
12. Handoff contém commits, arquivos, testes, métricas, screenshots, riscos e rollback ensaiado.

## 25. Prompt de execução

```text
Execute docs/plans/WP-CHECKOUT-ADDRESS-MAP-CONFIRMATION-2026-09-28.md integralmente.

Antes de editar, crie worktree própria a partir de origin/main e leia CLAUDE.md,
ADDRESS-UX-PLAN.md, DELIVERY-GEOCODING-AND-FEEDBACK-PLAN.md e os contratos citados.
Implemente por fases, mantendo AddressPicker/delivery_address_structured/Core como fontes
canônicas. Não peça GPS passivamente, não copie identidade do iFood, não envie PII em
telemetria e não crie cálculo de zona no frontend. Preserve o fluxo atual atrás do kill
switch. Verifique cada AC e a Definition of Done; UI exige screenshots e QA mobile/a11y.

Entregue branch/commits, arquivos, tabela AC × evidência, testes, métricas de performance,
screenshots, resultado do smoke, estado da flag e rollback ensaiado. Não faça deploy sem
coordenação explícita do owner de release.
```
