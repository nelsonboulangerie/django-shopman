# WP-CHECKOUT-ADDRESS-LOCATION-DIVERGENCE — conferir endereço × localização atual

> **Status:** READY — extensão dependente; executar depois da base de confirmação visual
>
> **Data da auditoria e do benchmark:** 2026-09-28
>
> **Superfície:** `surfaces/storefront-nuxt`, checkout mobile-first/PWA
>
> **Prioridade sugerida:** P1 de prevenção de entrega no endereço errado
>
> **Dependência funcional:** `WP-CHECKOUT-ADDRESS-MAP-CONFIRMATION-2026-09-28.md`
>
> **Rollout:** configuração pública canônica em `off | measure | visible`; default `off`
>
> **Risco:** médio — localização precisa é dado pessoal e GPS pode produzir falso positivo

Autoridade entre documentos:

| Tema | Documento canônico |
|---|---|
| mapa, ponto confirmado, reverse, contrato de coordenadas, envelope de eventos e privacidade geral | WP de confirmação visual |
| comparação endereço escolhido × posição atual, antifalso positivo, alerta e calibração | este WP |

Este documento especifica somente o delta. Em conflito, a base governa mapa/contratos e esta
extensão governa a política de divergência.

## 1. Resultado esperado

Depois que a pessoa escolhe um endereço de entrega — salvo ou vindo da busca — ela pode,
por gesto explícito, pedir que a loja confira esse destino com a localização atual do
aparelho. Quando a divergência for tecnicamente confiável, o checkout mostra um aviso
calmo e não bloqueante, preserva o endereço escolhido e oferece três decisões claras:

1. **Entregar neste endereço**;
2. **Usar minha localização**;
3. **Revisar no mapa**.

O sistema nunca troca o endereço sozinho, nunca lê GPS na abertura do site e nunca trata
uma posição imprecisa como prova de erro. Se não for possível comparar com segurança, a
pessoa continua normalmente com o endereço escolhido, pode tentar de novo ou revisar
manualmente.

O recurso é uma rede de segurança antes do pedido, não uma nova autoridade geográfica.
`AddressPicker` continua dono da interação, `delivery_address_structured` continua o
contrato canônico e o Core continua dono de cobertura, taxa e promessa.

## 2. Bootstrap obrigatório do executor

Antes de editar:

1. Criar worktree própria a partir de `origin/main` e verificar trabalho já em voo.
2. Ler integralmente:
   - `CLAUDE.md` e qualquer `AGENTS.md` aplicável;
   - este WP;
   - `docs/plans/ADDRESS-UX-PLAN.md`;
   - `docs/plans/WP-CHECKOUT-ADDRESS-MAP-CONFIRMATION-2026-09-28.md`;
   - `docs/reference/data-schemas.md`, especialmente `delivery_address_structured`;
   - `surfaces/storefront-nuxt/app/components/AddressPicker.vue`;
   - `surfaces/storefront-nuxt/app/presentation/address.ts`;
   - `surfaces/storefront-nuxt/app/pages/finalizar.vue`;
   - `shopman/storefront/presentation/address_privacy.py`;
   - `shopman/storefront/presentation/checkout.py`;
   - `shopman/shop/projections/customer_context.py`;
   - `packages/guestman/shopman/guestman/services/address.py`;
   - `shopman/storefront/api/geocode.py`;
   - `shopman/shop/services/delivery_distance.py`.
3. Confirmar se o WP de mapa já foi implementado. Se não, entregar primeiro os seus
   contratos compartilhados (ponto confirmado, `coordinates_source`, mapa e telemetria),
   sem duplicá-los neste slice.
4. Verificar que a comparação continua consultiva: nenhum resultado deste WP pode decidir
   taxa ou área de entrega no cliente.

Na auditoria de 2026-09-28 não havia `AGENTS.md`; `CLAUDE.md` era a regra aplicável.

## 3. Evidência do benchmark — o que sabemos e o que não sabemos

O iFood é a principal referência comportamental brasileira deste WP, mas não é fonte para
limiar, fórmula ou identidade visual.

### 3.1 Verificado

| Evidência | Data/superfície | Conclusão permitida | Confiança |
|---|---|---|---|
| [Bastidores: como funciona um pedido do iFood](https://institucional.ifood.com.br/institucional/como-funciona-um-pedido-do-ifood/) | publicado em 2025-07-11; descrição oficial do app | Na abertura, o app compara último endereço e GPS; se diferirem, sugere revisão. | Alta para o comportamento; não prova a UI atual. |
| [Entrega rápida perto de mim](https://institucional.ifood.com.br/clientes/entrega-rapida-perto-de-mim/) | fonte oficial consultada em 2026-09-28; app | Endereço ativo no topo, ação “Usar Localização Atual” e endereços anteriores. | Alta para o repertório; não prova os botões do alerta. |
| Observação direta de `ifood.com.br/inicio` | 2026-09-28; web desktop responsivo | Busca, “Usar minha localização” e, após Places, mapa com “Você está aqui?”, ajuste e confirmação. | Alta para a web observada. |
| [Comércio perto de mim](https://institucional.ifood.com.br/clientes/comercio-perto-de-mim/) | publicado em 2026-02-27; suporte app | Permissão/localização precisa podem ser revisadas; digitação manual é alternativa. | Alta para suporte; não prova recuperação inline. |
| [Gerenciamento de Conta e Cadastro](https://institucional.ifood.com.br/ajuda/conta-e-cadastro-ifood/) | publicado em 2026-04-01; app | O app pede permissão de localização no onboarding. | Alta para o app; não transplantar para web/PWA. |

### 3.2 Não verificado — não apresentar como “o iFood faz assim”

- distância ou fórmula usada para disparar a divergência;
- tratamento da precisão reportada pelo GPS;
- microcopy, layout ou botões exatos do alerta;
- comportamento inline quando a permissão é negada, GPS está desligado ou impreciso;
- se o alerta do app abre o mesmo mapa observado na web;
- se a pessoa precisa reconhecer o aviso antes de prosseguir.

O limite de **1 km** publicado para alteração pós-pedido no produto iFood Entrega Fácil
pertence a outro contrato e outro momento da jornada. **Não é evidência** para este alerta
de consumidor e não deve ser reutilizado.

### 3.3 Princípio transferido, mecanismo próprio

Transferir somente o princípio: quando endereço escolhido e posição atual parecem
incompatíveis, sugerir revisão antes que o erro vire entrega. No Storefront Web/PWA a
leitura será **opt-in e contextual**, diferente da checagem descrita na abertura do app
nativo. Limiares, fórmula, UX e copies abaixo são decisões Shopman, calibráveis e não
atribuídas ao iFood.

## 4. Auditoria técnica do estado atual (revalidada em `origin/main` `e3880d89d`)

O levantamento original nasceu em `79263250e`; a consolidação R4 revalidou contratos,
arquivos e riscos no baseline acima.

| Área | Estado verificado | Lacuna/decisão deste WP |
|---|---|---|
| GPS | `locateMe()` só existe no modo `search`; usa `getCurrentPosition(enableHighAccuracy: true, timeout: 10000)`. | Tornar a checagem disponível depois de endereço salvo ou buscado, sempre por gesto. |
| Precisão | `coords.accuracy` é descartado; `maximumAge` não é definido. | Preservar accuracy e timestamp apenas em memória; posição imprecisa nunca gera divergência. |
| Resultado GPS | O fluxo limpa query/sugestões, faz reverse e mostra candidato textual. | Checagem não pode destruir busca/seleção; só troca destino após decisão explícita. |
| Busca Places | Sugestão traz lat/lng/place id e vai ao formulário. | Comparar com o ponto da sugestão/confirmado sem chamada server desnecessária. |
| ViaCEP/manual | Não traz coordenadas no cliente; o Core pode fazer forward geocode para taxa. | Sem coordenada confiável, classificar `unavailable`; não usar a coordenada de precificação como prova silenciosa. |
| Salvos integrais | `SavedAddressProjection` normalmente leva lat/lng ao cliente. | Comparar localmente; o ponto já foi legitimamente projetado para uma sessão integral. |
| Salvos reduzidos | `address_privacy._reduced()` remove rua, número, complemento, lat/lng e `place_id`. | Nunca reexpor nem criar oráculo de proximidade. Sem ponto no cliente, não comparar; permitir iniciar novo destino por GPS. |
| Pré-seleção | `pickSaved()` emite imediatamente; `finalizar.vue` sincroniza e chama `applyDeliveryDraft()`. | Checagem não atrasa nem invalida cotação existente. Aviso é consultivo. |
| Sugestão inteligente | `suggest_address(customer_ref, location=None)` aceita location e raio, mas o checkout nunca passa localização. Default sempre vence geo. | Não reutilizar para trocar seleção; seu propósito é sugestão, não detecção de divergência. |
| Mapa | Bottom sheet já existe, mas o baseline atual é ajuste manual com marker arrastável. | Reusar/evoluir pelo WP de mapa; não criar segundo componente cartográfico. |
| Reverse | Endpoint público 30/min; resposta pode devolver centróide do Google. | Current fix continua sendo o ponto do GPS; reverse só descreve. |
| Contrato | `AddressSelection` não carrega accuracy/origem; schema documenta `coordinates_source` no concierge, mas storefront ainda não o transporta. | Reusar `coordinates_source` do WP de mapa; accuracy fica transitório e nunca no pedido. |
| Persistência de salvo | Checkout com `saved_address_id` dá precedência server-side ao salvo. | Ajustar pin de salvo sem salvar deve criar seleção nova (`savedAddressId=null`), nunca fingir que o salvo mudou. |
| Cobertura/taxa | `applyDeliveryDraft()` e Core calculam zona/distância. | Recalcular apenas depois de destino novo confirmado. Comparação não chama regra de zona. |
| Analytics | Existe `/storefront/client-error/` apenas para erros, com sanitização. | Criar/reusar boundary de eventos de produto do WP de mapa; não enviar eventos comuns como erro/Sentry. |
| Testes | Há testes puros de endereço e do serviço `suggest_address`, mas nenhum teste de componente para GPS/divergência. | Criar matriz determinística de cálculo, permissão, salvos reduzidos e ações. |

### 4.1 Riscos concretos que a implementação deve corrigir, não perpetuar

1. `mergeReverseGeocode()` hoje pode substituir GPS/pin pelo centróide do geocoder.
2. O estado GPS atual elimina a query antes de saber se a operação terá sucesso.
3. Um salvo reduzido não pode ser comparado no browser; um endpoint que devolvesse
   `diverged/compatible` também permitiria triangular o endereço com posições forjadas.
4. Alterar `AddressSelection.structured` mantendo `savedAddressId` pode ser ignorado pelo
   servidor, que reconstrói o endereço salvo.
5. Distância bruta sem `accuracy` produz falsos positivos em GPS por rede, ambientes
   internos, VPN não relevante à Geolocation API, prédios e condomínios grandes.

## 5. Escopo

### In

- GPS por opt-in para conferir endereço já selecionado;
- comparação geoespacial conservadora e limiar configurável;
- busca Places, endereço salvo integral e degradação segura para salvo reduzido;
- alerta não modal e não bloqueante;
- manter endereço, usar localização atual e revisar no mapa;
- precisão, expiração, corrida assíncrona, retry e antifalsos positivos;
- privacidade, acessibilidade, mobile, teclado e performance;
- eventos agregados sem PII;
- feature config, rollout, rollback e calibração;
- testes unitários, contrato, componente, API, E2E, a11y e visuais.

### Out

- pedir GPS automaticamente ao abrir home, checkout ou PWA;
- mudar silenciosamente endereço, salvo padrão, fulfillment ou zona;
- comparar IP/GeoIP com endereço de entrega;
- guardar accuracy, trilha de posições ou aceite do alerta no perfil/localStorage;
- mostrar distância exata ao cliente como acusação de erro;
- desenhar área de entrega no mapa;
- usar o limite de 1 km do Entrega Fácil;
- inferir endereço a partir de Wi-Fi, Bluetooth ou background location;
- alterar pedido depois de criado;
- criar nova fonte de verdade de endereço ou novo provedor de mapas;
- recalibrar automaticamente o limiar com dados individuais.

## 6. Invariantes adicionais da extensão

Herdam-se integralmente as invariantes de contrato, Core, reverse, fallback, chave e
telemetria do WP base. Este slice acrescenta apenas:

1. Endereço escolhido continua ativo até uma nova confirmação explícita.
2. A divergência nunca bloqueia avanço, pagamento ou pedido.
3. Permissão negada/timeout/baixa precisão preservam seleção, carrinho e cotação.
4. GPS só é lido depois de gesto claro; não memorizar a decisão para leituras futuras.
5. Accuracy é parte obrigatória da decisão. Sem precisão confiável, não há alerta.
6. Coordenadas reduzidas de um salvo nunca descem ao cliente e nenhum status de
   proximidade cria um canal lateral equivalente.
7. Fechar/ignorar o alerta equivale a manter o endereço; nada é persistido.
8. Uma resposta assíncrona antiga nunca se aplica a outra seleção.

## 7. Onde e quando oferecer a checagem

### 7.1 Endereço salvo

Depois que um salvo estiver selecionado, apresentar ação secundária discreta
**“Usar minha localização”** junto ao resumo. A ação:

1. explica que a localização será usada uma vez para conferir a entrega;
2. chama a permissão do browser somente após o toque;
3. compara localmente quando a projeção integral já contém o ponto do salvo;
4. preserva o `savedAddressId`, a cotação e o avanço enquanto calcula;
5. só abre o aviso quando o resultado for `diverged`.

Em sessão reduzida, não há comparação: o card explica apenas que a localização pode ser
usada como **novo destino**, sem dizer se está perto/longe do salvo. Tocar na ação abre o
fluxo canônico de localização/mapa. Reautenticar para uma sessão integral é a única forma
de habilitar comparação com o salvo; nunca criar endpoint que responda proximidade para um
alvo oculto.

Não executar automaticamente para o salvo pré-selecionado. Isso diverge deliberadamente do
app nativo descrito pelo iFood: no web/PWA do Shopman, ausência de consentimento prévio
específico vence conveniência.

### 7.2 Endereço selecionado na busca

Depois de Places e da confirmação visual definida no WP de mapa:

- oferecer a mesma ação opt-in no resumo/formulário;
- comparar localmente o GPS com a coordenada confirmada;
- não fazer novo reverse só para calcular distância;
- se a origem não tem coordenadas (ViaCEP/manual), não inventar alvo: informar que a
  conferência espacial não está disponível e manter o fluxo atual.

Se a pessoa iniciou pelo CTA “Usar minha localização”, já está escolhendo o ponto atual;
não comparar esse ponto com ele mesmo nem mostrar alerta redundante.

### 7.3 Endereço editado

Qualquer mudança em rua, número, CEP ou pin invalida o resultado anterior. A checagem pode
ser oferecida novamente por gesto, mas não roda automaticamente. Mudanças só em complemento
ou instruções não invalidam o ponto confirmado.

## 8. Fluxo do aviso de divergência

Quando a comparação retornar `diverged`, renderizar card inline perto do resumo do destino,
sem modal, sem overlay e sem desabilitar o CTA do checkout.

### 8.1 Conteúdo

- título factual;
- endereço de entrega atual, com a mesma regra de redução já aplicada à sessão;
- “Sua localização atual” com resumo do reverse quando disponível, ou apenas “Ponto
  encontrado”;
- três ações explícitas;
- alternativa de continuar/fechar, que mantém o destino.

### 8.2 Ações

#### Entregar neste endereço

- mantém exatamente o `AddressSelection` atual;
- mantém a cotação existente;
- fecha o aviso e anuncia a decisão;
- não grava “exceção”, coordenada GPS ou consentimento permanente;
- não volta a alertar sem novo gesto ou mudança do endereço nesta montagem do picker.

#### Usar minha localização

- não substitui o endereço imediatamente;
- abre o fluxo canônico de mapa no fix GPS cru, com círculo de precisão;
- reverse geocode preenche um candidato textual sem trocar a coordenada confirmada;
- após confirmar mapa e campos, produz nova `AddressSelection` com
  `coordinates_source='pin'` e `savedAddressId=null`;
- só então `applyDeliveryDraft()` recalcula cobertura/taxa;
- nunca sobrescreve o endereço salvo de origem.

#### Revisar no mapa

- abre o mesmo componente do WP de mapa em modo `compare`;
- mostra o destino editável e a localização atual como ponto secundário + accuracy ring;
- ajusta viewport para os dois quando isso não revela escala absurda; limita zoom mínimo;
- oferece resumo textual equivalente fora do canvas;
- confirmar um ponto ajustado gera seleção nova com `savedAddressId=null` no checkout;
- cancelar volta ao alerta sem aplicar mudança.

No modo `compare`, cor/forma/label devem distinguir **Entrega** de **Você está aqui**. Não
usar dois pins idênticos e não depender só de cor.

## 9. Copies propostas — autoria Shopman

As frases desta seção são propostas próprias. Não são reprodução nem transcrição de UI do
iFood. Validar no gate Omotenashi, mantendo a semântica dos CTAs.

| Estado | Copy proposta |
|---|---|
| Explicação antes da permissão | “Podemos usar sua localização uma vez para conferir o ponto da entrega.” |
| Ação opt-in | “Usar minha localização” |
| Pending | “Conferindo sua localização…” |
| Divergência — título | “Sua localização parece diferente do endereço de entrega” |
| Divergência — corpo | “Confira antes de continuar. Você pode manter o endereço escolhido, usar o ponto onde está ou revisar no mapa.” |
| Rótulo do alvo | “Endereço de entrega” |
| Rótulo do GPS | “Sua localização atual” |
| Manter | “Entregar neste endereço” |
| Trocar | “Usar minha localização” |
| Mapa | “Revisar no mapa” |
| Decisão mantida | “Certo. Vamos entregar no endereço escolhido.” |
| Compatível | “Sua localização parece próxima do endereço escolhido.” |
| Baixa precisão | “Não deu para comparar com segurança. Você pode tentar de novo ou seguir com o endereço escolhido.” |
| Permissão negada | “A localização não foi liberada. Seu endereço continua selecionado.” |
| Timeout | “A localização demorou para responder. Seu endereço continua selecionado.” |
| Alvo sem coordenada | “Este endereço não tem um ponto preciso para comparar. Você pode revisá-lo no mapa.” |
| Reverse indisponível | “Encontramos o ponto, mas não o nome do endereço. Confira no mapa antes de usar.” |

Evitar: “Você está no endereço errado”, “GPS exato”, “endereço incorreto”, “você está a
X metros” ou qualquer frase que transforme estimativa em certeza.

## 10. Modelo de estado

```text
selected_saved | selected_search
  └─ location_check_requested (gesto)
       ├─ permission_pending
       │    ├─ fix_resolved
       │    │    ├─ comparing
       │    │    │    ├─ compatible ─────────────> seleção preservada
       │    │    │    ├─ diverged ───────────────> warning_visible
       │    │    │    ├─ inconclusive ───────────> soft_status + retry
       │    │    │    └─ unavailable ────────────> soft_status + map/manual
       │    │    └─ stale_selection ─────────────> descarta resultado
       │    └─ denied | timeout | unavailable ───> seleção preservada
       └─ unsupported ───────────────────────────> seleção preservada

warning_visible
  ├─ keep_selected ──────────────────────────────> selected
  ├─ use_current ──> map(current) ──> form ─────> new_selection + zone_quote
  ├─ review_map ───> map(compare) ───────────────> new_selection + zone_quote
  └─ dismiss ────────────────────────────────────> selected
```

Regras de corrida:

- capturar um `selectionFingerprint` sem PII, apenas em memória;
- incrementar sequence id a cada request;
- ignorar fix/response se id ou seleção mudou;
- abortar/ignorar requests no unmount e remover listeners do mapa;
- botão fica idempotente durante pending;
- fechamento nunca cancela nem altera a cotação vigente.

## 11. Política geoespacial e antifalsos positivos

### 11.1 Configuração canônica recomendada

Projetar no `public_config` um único objeto, originado no servidor:

```ts
interface AddressLocationDivergenceConfig {
  mode: 'off' | 'measure' | 'visible'
  threshold_m: number       // default recomendado: 500
  max_accuracy_m: number    // default recomendado: 250
  maximum_age_ms: number    // default recomendado: 30_000
  policy_version: string    // ex.: 'v1'
}
```

Defaults acima são **decisão inicial Shopman**, não benchmark do iFood. Validar bounds no
servidor (`threshold_m` entre 100 e 10.000; `max_accuracy_m` entre 20 e 2.000;
`maximum_age_ms` entre 0 e 300.000). Config ausente/inválida equivale a `mode='off'`.
Não duplicar números em env, Nuxt e componente.

O objeto público chama-se `address_location_divergence`. Ele é independente do boolean
`address_map_confirmation_enabled` da base, mas `visible` só é válido quando o mapa base está
ativo; caso contrário o servidor projeta `off`. Isso mantém rollout e rollback separados sem
deixar “Revisar no mapa” apontar para uma implementação ausente.

`measure` só calcula e emite eventos agregados quando houve gesto opt-in; não mostra alerta.
Ele não autoriza leitura passiva de GPS.

### 11.2 Fix atual

Capturar transitoriamente:

```ts
interface CurrentLocationFix {
  point: { lat: number, lng: number }
  accuracyM: number
  capturedAtMs: number
}
```

Opções do browser:

```ts
{
  enableHighAccuracy: true,
  timeout: 10_000,
  maximumAge: config.maximum_age_ms
}
```

Rejeitar como `inconclusive`, sem alerta, quando:

- lat/lng/accuracy não são finitos ou estão fora do intervalo;
- `accuracyM <= 0` ou `accuracyM > max_accuracy_m`;
- timestamp excede `maximum_age_ms + 5_000` ao iniciar a comparação;
- alvo não tem coordenada válida;
- seleção mudou enquanto o fix era obtido.

### 11.3 Incerteza do alvo

Como Places/salvos não expõem raio de precisão, aplicar margem conservadora por origem,
em função pura e centralizada:

| Origem do alvo | Margem inicial Shopman |
|---|---:|
| pin confirmado visualmente | 30 m |
| Places com número/rooftop | 80 m |
| salvo com coordenada, origem/nível desconhecido | 150 m |
| geocoding textual/centróide | 250 m |
| sem origem ou coordenada | comparação indisponível |

Essas margens são conservadoras e calibráveis em código/config versionado; não são fatos do
Google nem do iFood. `coordinates_source` vem do contrato do WP de mapa. Como o salvo atual
não expõe origem/raio de precisão, usar a margem conservadora de 150 m; a projeção reduzida
sem coordenada permanece incomparável.

### 11.4 Fórmula

Usar Haversine puro apenas para a checagem. Seja:

```text
d = distância entre GPS e alvo
lower_bound = max(0, d - accuracyM - targetUncertaintyM)
```

Classificação:

```text
invalid/missing/stale/low-accuracy -> inconclusive ou unavailable
lower_bound >= threshold_m        -> diverged
lower_bound < threshold_m         -> compatible
```

O alerta usa o **limite inferior**, não a distância bruta. Assim só afirma divergência se
até a interpretação mais favorável dos círculos de incerteza ainda ultrapassa o limiar.
Não arredondar antes de classificar. Não usar CEP, bairro ou município como atalho positivo;
podem servir apenas para cancelar uma afirmação suspeita e cair em `inconclusive`.

### 11.5 Casos de proteção

- GPS a 650 m, accuracy 120 m, alvo incerto 150 m: `lower_bound=380 m`; não alertar.
- GPS a 900 m, accuracy 80 m, alvo incerto 150 m: `lower_bound=670 m`; alertar com threshold 500 m.
- GPS a 3 km com accuracy 600 m: inconclusivo, não alertar.
- alvo ViaCEP sem coordenadas: indisponível, não forward-geocodificar só para acusar divergência.
- ponto atual e alvo em lados diferentes de condomínio grande, mas bounds se sobrepõem: compatível.
- GPS atual originado do mesmo fluxo: não comparar consigo mesmo.

## 12. Contratos e boundaries

### 12.1 Busca/endereço novo — cálculo local

Usar função pura em `app/presentation/addressLocationConsistency.ts` (nome sugerido):

```ts
type LocationConsistencyStatus = 'compatible' | 'diverged' | 'inconclusive' | 'unavailable'

interface LocationConsistencyResult {
  status: LocationConsistencyStatus
  accuracyBucket: 'good' | 'medium' | 'low' | 'unknown'
  reason?: 'missing_target' | 'invalid_fix' | 'stale_fix' | 'low_accuracy'
  policyVersion: string
}
```

O resultado não entra no `AddressSelection`, draft salvo ou pedido. Somente a ação posterior
pode produzir nova seleção canônica.

### 12.2 Endereço salvo e cerca de redução

- projeção integral com lat/lng: usar a mesma função local da busca, com origem
  `saved_unknown` e margem conservadora;
- projeção reduzida sem lat/lng: retornar `unavailable` localmente, sem request de
  comparação;
- nunca adicionar endpoint que aceite pontos arbitrários e responda
  `compatible/diverged` contra um salvo oculto: a resposta binária permite triangulação;
- nunca acrescentar coordenada, distância ou `is_verified` à projeção reduzida;
- “Usar minha localização” continua disponível como criação de destino novo e não revela
  qualquer relação com o salvo;
- Core/Guestman não são alterados por essa leitura.

Não importar código de delivery fee no browser nem reutilizar `store_distance_km`, que tem
outra origem e responsabilidade.

### 12.3 Novo destino a partir de salvo

Ao confirmar localização/mapa diferente:

```ts
{
  savedAddressId: null,
  structured: {
    ...,
    latitude,
    longitude,
    coordinates_source: 'pin'
  }
}
```

Não fazer PATCH no salvo. Se a pessoa escolher explicitamente editar e salvar, seguir o
fluxo de edição já existente, fora da decisão implícita do alerta.

## 13. Privacidade e segurança

Aplicam-se os controles gerais do WP base: finalidade antes do prompt, fix apenas em memória,
nenhuma coordenada/PII em storage, URL, breadcrumb ou evento, reverse server-side e keys no
boundary correto. Esta extensão acrescenta dois gates:

1. nenhum endpoint/status de proximidade pode existir para salvo reduzido;
2. threat test deve provar que ids/pontos forjados não viram oráculo de existência,
   proximidade ou coordenada.

Sem esses dois gates, `measure` e `visible` permanecem `off`, mesmo que o mapa base esteja ativo.

## 14. Acessibilidade e mobile

Aplicam-se tamanho de alvo, teclado, zoom, leitores reais, reduced motion, fallback textual e
retorno de foco do WP base. Deltas desta extensão:

1. aviso nasce de gesto e usa região nomeada/status sem trap;
2. as três decisões são botões reais; “Entregar neste endereço” é a primeira no DOM;
3. accuracy/divergência nunca dependem apenas de círculo, cor ou mapa;
4. fechar/Esc preserva destino e cotação e devolve foco ao acionador;
5. 320 CSS px, landscape e teclado virtual não escondem nenhuma das três decisões.

## 15. Analytics e observabilidade

Reusar o boundary first-party allow-listed definido no WP de mapa. Se ele ainda não existir,
criá-lo uma vez para os dois WPs. Não usar `/storefront/client-error/` para produto.

| Evento | Quando | Propriedades permitidas |
|---|---|---|
| `address.location_check.requested` | gesto opt-in | `target=saved|search`, `mode` |
| `address.location_check.resolved` | classificação | `target`, `status`, `accuracy_bucket`, `policy_version` |
| `address.location_check.failed` | falha técnica/browser | `target`, `reason=denied|timeout|unavailable|unsupported|rate_limited` |
| `address.location_mismatch.shown` | aviso visível | `target`, `accuracy_bucket`, `policy_version` |
| `address.location_mismatch.action` | decisão | `action=keep|use_current|review_map|dismiss`, `target` |
| `address.location_mismatch.recovered` | novo destino confirmado | `path=use_current|review_map`, `zone_result=covered|uncovered|deferred` |

Regras:

- enum allow-listed; nenhuma string livre;
- `measure` emite `requested/resolved`, nunca `shown`;
- amostragem, se necessária, é configurada no servidor e documentada;
- permission denied é comportamento esperado, não erro operacional;
- dashboard observa taxa de check, divergência, ação, recuperação e abandono por versão;
- calibrar threshold apenas em agregado e com review humano; nunca inferir limiar individual.

## 16. Arquivos prováveis
### Alterar

- `surfaces/storefront-nuxt/app/components/AddressPicker.vue`
- componente de mapa extraído pelo WP de confirmação, se existir
- `surfaces/storefront-nuxt/app/presentation/address.ts`
- `surfaces/storefront-nuxt/app/types/shopman.ts`
- `surfaces/storefront-nuxt/app/pages/finalizar.vue` apenas para integração de cotação/eventos
- `shopman/storefront/presentation/address_privacy.py` somente para testes/guardrail da redução, se necessário
- `shopman/storefront/presentation/home.py` para config pública
- boundary de telemetria first-party definido no WP de mapa
- `docs/plans/ADDRESS-UX-PLAN.md`
- `docs/reference/data-schemas.md`
- política/snapshot de privacidade indicados no WP de mapa

### Criar, se a estrutura continuar simples

- `surfaces/storefront-nuxt/app/presentation/addressLocationConsistency.ts`
- `surfaces/storefront-nuxt/tests/addressLocationConsistency.test.ts`
- `surfaces/storefront-nuxt/tests/components/AddressLocationDivergence.test.ts`
- `surfaces/storefront-nuxt/tests/e2e/addressLocationDivergence.spec.ts`
- fixture de vetores da política em local canônico dos testes do storefront

Não criar store global, tabela, migração, pacote de geodistância, provider genérico ou segundo
map picker.

## 17. Plano de implementação

### Fase 0 — caracterização

- congelar os fluxos salvos integral/reduzido, Places, ViaCEP/manual e GPS atual;
- provar precedência server-side de `saved_address_id`;
- caracterizar map/reverse do WP dependente;
- validar que config `off` não muda DOM, requests ou cotação.

### Fase 1 — política pura

- config canônica e bounds;
- Haversine, accuracy, target uncertainty e classification;
- vetores determinísticos da política no storefront;
- state machine, sequence/fingerprint e eventos puros;
- testes de limites antes da UI.

### Fase 2 — integração de salvos e cerca de privacidade

- salvo integral usa o cálculo local com margem conservadora;
- salvo reduzido degrada sem status de proximidade e pode iniciar novo destino;
- guardrail prova que `_reduced` continua sem rua, número, complemento, lat/lng e place id;
- testes de não vazamento e de ausência de oráculo.

### Fase 3 — UX integrada

- ação opt-in em salvo e busca;
- estados pending/compatible/inconclusive/failure;
- aviso e três decisões;
- current location/map compare pelo componente canônico;
- back/cancel/foco/mobile.

### Fase 4 — observabilidade e qualidade

- eventos allow-listed;
- unit/component/API/E2E/a11y/visual;
- QA em Chrome Android e Safari iOS;
- política de privacidade e specs atualizadas.

### Fase 5 — rollout

- `off` em produção após deploy;
- `measure` em alpha/staging e depois amostra controlada de produção;
- analisar falsos positivos por accuracy/source sem PII;
- `visible` em janela de menor tráfego;
- manter rollback por config durante ao menos um release completo.

## 18. Plano de testes

### Unitários/política

- Haversine: zero, antimeridiano, coordenadas inválidas;
- exatamente abaixo/no/acima do threshold;
- subtração de accuracy + margem do alvo;
- accuracy exatamente no máximo e acima;
- stale/unknown/non-finite;
- todas as origens do alvo;
- vetores da política no TypeScript;
- accuracy buckets e classificação sem expor distância;
- config inválida cai em `off`.

### Componentes

Mockar Geolocation, Maps e reverse:

- salvo integral e reduzido;
- Places/pin e ViaCEP/manual;
- compatible não mostra alerta invasivo;
- diverged mostra copy e ações;
- denied/timeout/unsupported/low accuracy preservam seleção;
- keep/dismiss mantêm id e cotação;
- use current não troca antes de mapa/form confirmados;
- review map cancelar não aplica;
- ajustar salvo produz `savedAddressId=null`;
- mudança de seleção descarta resposta antiga;
- clique duplo não duplica request/evento;
- unmount limpa listeners e ignora resposta;
- `off` reproduz baseline; `measure` não renderiza aviso;
- foco, live region, Esc e ordem DOM.

### Backend/projeções

- projeção integral mantém campos atuais e a reduzida continua sem rua/coords/place id;
- nenhum endpoint de comparação é criado;
- sessão reduzida não obtém `compatible/diverged` para alvo salvo;
- logs/eventos não têm PII, id ou distância;
- reverse/save existentes mantêm auth/rate-limit e não recebem chamada antes da decisão.

### E2E

- salvo longe → manter → checkout segue com mesma taxa/endereço;
- salvo longe → localização atual → mapa/form → nova cotação;
- salvo longe → comparar no mapa → cancelar/confirmar;
- salvo próximo → sem alerta;
- salvo reduzido → não compara, não revela proximidade e pode iniciar destino novo;
- Places longe → alerta e três ações;
- ViaCEP/manual → indisponível sem bloqueio;
- permissão negada e timeout → endereço/carrinho intactos;
- baixa precisão → retry, sem falso alerta;
- endereço muda durante request → resultado stale ignorado;
- fora da área após novo ponto → recuperação por retirada já existente;
- reload não restaura GPS nem warning, apenas seleção canônica.

### Visuais e manuais

- 320×568, 375×812, 390×844, 768×1024 e 1280×800;
- light/dark, pending/diverged/inconclusive/denied;
- endereço integral e reduzido;
- zoom 200%/400%, landscape, teclado virtual;
- mapa compare com dois marcadores distinguíveis e attribution visível;
- VoiceOver, TalkBack e teclado.

Baselines usam fake map determinístico; tiles reais somente no smoke manual autorizado.

## 19. Performance

- zero Geolocation/Maps/reverse antes do gesto;
- feedback pending em até 100 ms;
- cálculo local síncrono e insignificante;
- comparação de salvo integral é local; salvo reduzido retorna unavailable sem rede;
- Maps só carrega após `use_current`/`review_map`;
- no máximo um fix por gesto e um reverse quando necessário;
- sem `watchPosition` e sem polling de permission;
- abort/ignore de request tardio;
- nenhuma dependência npm nova.

## 20. Rollout, calibração e rollback

### Gates para `measure`

- vetores da política verdes;
- privacy/PII review verde, incluindo ausência de oráculo para salvo reduzido;
- política de privacidade publicada;
- opt-in e fallback validados em devices;
- eventos agregados inspecionados sem payload livre.

### Gates para `visible`

- volume suficiente de checks em `measure` para observar accuracy/source;
- owner de produto aprova threshold/margens como decisão Shopman;
- revisão manual de casos limítrofes autorizados, sem endereço pessoal em artefato;
- nenhuma regressão de cotação/endereço salvo;
- screenshots e a11y aprovados;
- suporte conhece fallback e kill switch.

### Métricas de saúde

- `diverged / resolved` por accuracy bucket e target source;
- `keep / shown` — sinal de possível falso positivo, não prova isolada;
- `use_current|review_map / shown`;
- recuperação até zona coberta/retirada;
- denied/timeout/low accuracy;
- abandono do passo versus baseline.

Não mudar threshold automaticamente. Uma taxa alta de “manter endereço” pode significar
pedido para outra pessoa, trabalho/casa ou falso positivo; exige pesquisa e amostra manual.

### Rollback

1. Mudar `mode` para `off` na configuração canônica.
2. Confirmar que nenhum CTA/check/request/evento novo aparece.
3. Confirmar busca, salvos, GPS candidato, mapa atual e cotação baseline.
4. Não apagar endereços ou dados: este WP não migra nem persiste resultado.
5. Se apenas UI estiver problemática, `measure` permite preservar cálculo agregado sem aviso,
   desde que privacidade e consentimento continuem válidos.

## 21. Critérios de aceite

- [ ] **AC-01** — Nenhuma leitura de GPS ocorre sem gesto explícito nesta sessão.
- [ ] **AC-02** — Checagem funciona para endereço Places/pin e salvo integral.
- [ ] **AC-03** — Salvo reduzido não é comparado nem expõe status de proximidade; GPS pode iniciar destino novo.
- [ ] **AC-04** — ViaCEP/manual sem ponto degrada para unavailable, sem geocode acusatório.
- [ ] **AC-05** — Accuracy/timestamp são obrigatórios e baixa precisão nunca gera alerta.
- [ ] **AC-06** — A fórmula usa limite inferior com margem do alvo e threshold configurável.
- [ ] **AC-07** — Nenhum número é atribuído ao iFood; 1 km do Entrega Fácil não é usado.
- [ ] **AC-08** — Divergência mostra aviso inline não bloqueante e copy factual própria.
- [ ] **AC-09** — Aviso oferece `Entregar neste endereço`, `Usar minha localização` e `Revisar no mapa`.
- [ ] **AC-10** — Manter/fechar preserva seleção, id salvo, taxa, carrinho e avanço.
- [ ] **AC-11** — Usar localização só troca destino após mapa/formulário confirmados.
- [ ] **AC-12** — Revisar salvo no mapa gera seleção nova sem mutar salvo silenciosamente.
- [ ] **AC-13** — Reverse nunca substitui o ponto GPS/pin confirmado por centróide.
- [ ] **AC-14** — Resposta stale não se aplica depois de trocar/editar endereço.
- [ ] **AC-15** — Denied/timeout/unsupported/rate limit têm saída e não bloqueiam checkout.
- [ ] **AC-16** — Core continua único responsável por zona/taxa e só recalcula após troca confirmada.
- [ ] **AC-17** — Analytics/logs não contêm PII, id, coordenada ou distância exata.
- [ ] **AC-18** — Nenhum endpoint/oráculo de proximidade é criado para salvo reduzido.
- [ ] **AC-19** — Fluxo é operável sem mapa, por teclado e leitor de tela, com targets 44×44.
- [ ] **AC-20** — `off` preserva baseline; `measure` calcula sem aviso; `visible` mostra a UX.
- [ ] **AC-21** — Unit, contrato, componente, API, E2E, a11y, visual, lint, typecheck e build passam.
- [ ] **AC-22** — Privacidade, specs e runbook/rollback estão atualizados antes de produção visível.

## 22. Definition of Done

O WP só termina quando:

1. todos os ACs têm evidência no PR;
2. o WP de mapa/contratos compartilhados está integrado sem componente duplicado;
3. vetores de limite/accuracy provam a política TypeScript;
4. não vazamento e ausência de oráculo do salvo reduzido foram revisados;
5. não há leitura passiva, persistência de fix ou telemetria com PII;
6. threshold e margens estão documentados como decisão Shopman, com owner e versão;
7. fluxo foi validado em Safari iOS e Chrome Android;
8. VoiceOver, TalkBack, teclado e zoom passaram checklist;
9. `off`, `measure` e `visible` foram exercitados no mesmo build;
10. cotação, fora de área, retirada e rollback passaram smoke;
11. `ADDRESS-UX-PLAN.md`, schema e privacidade refletem a entrega real;
12. handoff inclui commits, testes, screenshots, métricas, riscos e estado da config.

## 23. Prompt de execução

```text
Execute docs/plans/WP-CHECKOUT-ADDRESS-LOCATION-DIVERGENCE-2026-09-28.md integralmente.

Antes de editar, crie worktree própria, leia CLAUDE.md, ADDRESS-UX-PLAN.md, o WP de
confirmação por mapa e os contratos citados. Não copie o iFood nem atribua a ele limiar,
fórmula ou microcopy não publicados. GPS é sempre opt-in; accuracy e incerteza do alvo
participam da classificação; alerta é consultivo e nunca troca endereço sozinho.

Preserve AddressPicker/AddressSelection/delivery_address_structured/Core como autoridades.
Não fure a projeção reduzida nem crie endpoint de proximidade para endereços ocultos; não
persista o fix e não envie PII em analytics. Reuse o mapa e a telemetria do WP dependente.
Verifique cada AC e a Definition of Done. Entregue tabela AC × evidência, vetores da
política, screenshots, QA mobile/a11y, métricas de rollout e rollback ensaiado. Não faça
deploy sem coordenação do owner.
```
