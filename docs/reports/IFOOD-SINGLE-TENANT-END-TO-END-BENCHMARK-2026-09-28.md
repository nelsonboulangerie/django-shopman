# iFood single-tenant — benchmark end-to-end para o Storefront

**Data de corte:** 2026-09-28

**Superfícies comparadas:** iFood Web em Chrome desktop e Shopman Storefront Nuxt/Django

**Caso real observado:** Rap1000 Kibixinha, Londrina-PR

**Resultado:** benchmark documental consolidado; esta mudança não altera produto nem inicia
pagamento/deploy, mas incorpora uma observação posterior de pedido real conduzido pelo usuário

**Base revalidada:** `origin/main` em `e3880d89d`; observações anteriores preservam sua data

## 1. Objetivo e conclusão

Este relatório registra o que o iFood faz bem, o que falhou na jornada observada e o que é
aplicável a uma boulangerie single-tenant. Ele não transforma o iFood em especificação, não
prioriza um backlog e não autoriza implementação.

A principal lição não é visual. O iFood organiza a compra como uma redução progressiva de
incerteza: onde entregar, o que está disponível, quanto custa, quando chega, como pagar e o
que acontece depois do compromisso. O Shopman já possui fundações transacionais maduras
que não devem ser trocadas por uma cópia de interface: projeções e ações canônicas,
reconciliação do carrinho, checkout idempotente, cálculo de entrega no Core e pagamento
integrado ao acompanhamento.

A condição single-tenant permite uma experiência potencialmente melhor e menor. Não existe
razão para reproduzir ranking de lojas, publicidade, filtros de merchants, selos de
marketplace, carteira própria ou uma lista extensa de produtos financeiros. A comparação
útil é entre momentos da jornada, feedback, prevenção e recuperação de erros.

O benchmark comprova, entre outros pontos:

- o valor de confirmar visualmente o ponto de entrega antes dos detalhes do endereço;
- a importância de deixar promessa, taxa, mínimo, desconto e total verificáveis;
- a eficiência de edição reversível até o último CTA;
- o benefício de preservar carrinho, endereço, cupom e total ao sair para um widget de
  pagamento;
- o custo de flashes de estado incorreto, erros sem ação, rótulos técnicos, modais sem saída
  e perda silenciosa da seleção de pagamento;
- que o Shopman já oferece conteúdo de produto, recuperação transacional, tracking e
  acessibilidade estrutural que devem ser preservados.

## 2. Método, níveis de evidência e limites

### 2.1 Legenda

- **[OD] Observação direta:** visto na interface ou árvore acessível do iFood em 28/09/2026.
- **[MD] Medição direta:** propriedade obtida por inspeção somente leitura do DOM/estilos.
- **[FI] Fonte iFood/primária:** documentação, publicação técnica ou listagem oficial.
- **[AS] Auditoria Shopman:** leitura estática de rotas, contratos, componentes, testes e PRs.
- **[INF] Inferência:** tradução fundamentada para o caso single-tenant.
- **[HIP] Hipótese:** questão plausível ainda sem medição ou teste de usuário local.

### 2.2 Artefatos incorporados

1. Notas efêmeras da exploração autenticada de endereço, Rap1000/Kibixinha, carrinho,
   cupons, checkout, pagamento e pós-entrega. Elas não são dependência do repositório; apenas
   a síntese sanitizada abaixo é canônica.
2. Pesquisa com fontes primárias, normativas e inferências single-tenant.
3. Auditoria estática do Storefront, revalidada no baseline informado no cabeçalho.
4. `WP-CHECKOUT-ADDRESS-MAP-CONFIRMATION-2026-09-28.md` e sua extensão dependente
   `WP-CHECKOUT-ADDRESS-LOCATION-DIVERGENCE-2026-09-28.md`.

### 2.3 Procedimento observado

- A sessão começou deslogada no iFood Web, viewport 1360×656.
- Um endereço autorizado pelo usuário em Londrina foi usado para contextualizar o catálogo.
- CAPTCHAs foram resolvidos somente pelo usuário; a observação não os contornou.
- O usuário realizou o login e abriu a loja correta quando a descoberta interna falhou.
- A primeira rodada chegou ao CTA `Fazer pedido` sem acioná-lo. Em rodada posterior, o usuário
  concluiu um pedido Pix e acompanhou a entrega.
- O widget de cartão foi explorado apenas com valores sintéticos obviamente inválidos;
  nenhum desses valores foi submetido ou salvo.
- A rodada posterior produziu código Pix, pedido, mensagens e tracking reais, mas código,
  identificadores, endereço, conta e sessão foram deliberadamente omitidos.
- A observação posterior foi feita no Web, com handoff móvel pontual; não equivale a auditoria
  completa do app nativo.

### 2.4 Limitações

- A observação foi majoritariamente Web desktop; o app nativo pode divergir. O celular só foi
  observado no handoff de pagamento, sem cobertura sistemática da jornada móvel.
- Conteúdo e regras do iFood variam por conta, região, horário e experimento.
- Busca/listagem falharam regionalmente durante a sessão; o usuário abriu a loja correta.
- Houve uma única observação transacional de pós-pedido. Fontes oficiais continuam sendo a
  base para capacidades não vistas; um caso não prova frequência nem mecanismo interno.
- Não foram coletados LCP, INP, CLS, waterfall ou RUM do iFood.
- A auditoria Shopman foi estática e não executou compra local. O levantamento nasceu em
  `7cc56f77d`, foi sintetizado em `664a57b93` e revalidado em `e3880d89d`.
- Avaliação, conversão, preferência e impacto financeiro exigem teste local; aparência não é
  evidência de resultado.

## 3. Filtro single-tenant

| Padrão do marketplace | Tratamento nesta análise |
|---|---|
| Escolha, ranking e comparação de lojas | Descartado |
| Lojas patrocinadas, selos e publicidade | Descartado |
| Macroáreas Mercado/Farmácia/Pets/Shopping | Descartado |
| Nota e distância do merchant | Descartado |
| Regras e taxas entre milhares de merchants | Descartado |
| Endereço, cobertura, promessa e taxa | Transferível |
| Busca, categorias e coleções por ocasião | Adaptável a produtos |
| Cardápio ativo por horário/disponibilidade | Transferível |
| Sacola, revisão, cupom e pagamento | Transferível com simplificação |
| Tracking, ajuda e recuperação | Transferível |
| Carteira, clube e crédito do marketplace | Fora do escopo salvo estratégia própria futura |

A Nelson deve usar identidade, tokens, voz, fotografia e ilustração próprios. Não copiar
vermelho, mascote, composição, ícones, nomes de componentes ou microcopy do iFood.

## 4. Jornada real observada — Rap1000 Kibixinha

### 4.1 Linha do tempo

1. **[OD] Endereço antes da vitrine.** A entrada pediu “Onde você quer receber seu pedido?”
   e ofereceu busca, localização e login para endereços salvos.
2. **[OD] Busca → mapa → detalhes.** Uma sugestão Google com número abriu “Você está
   aqui? Ajuste a localização”; após confirmar o pin vieram número, complemento, referência
   e favorito.
3. **[OD] Descoberta falhou.** As buscas por `Rap 10`, `Ra 1000` e `Kibixinha`, além de
   `/restaurantes` e da categoria Salgados, terminaram em erro regional sem CTA de retry.
4. **[OD] Handoff humano.** O usuário abriu diretamente a loja **Rap1000 Kibixinha**.
5. **[OD] Loja.** O topo mostrou nota 4,9, mínimo de R$ 20, entrega em 60–70 min, taxa de
   R$ 14 e retirada indisponível.
6. **[OD] PDP.** A Kibixinha custava R$ 18; quantidade atualizava o valor do CTA. Havia
   comentário livre, mas não alergênicos, peso, composição estruturada ou disponibilidade.
7. **[OD] Login tardio.** O primeiro `Adicionar` levou a `/entrar`; depois do login feito
   pelo usuário, endereço e intenção voltaram preservados.
8. **[OD] Mínimo.** Uma Kibixinha gerou subtotal de R$ 18 e bloqueio claro porque frete não
   conta no mínimo. Não houve sugestão contextual para completar os R$ 2.
9. **[OD] Carrinho/checkout.** Itens, taxas, entrega, cupom, pagamento e total ficaram
   editáveis até o último CTA.
10. **[OD] Exploração financeira segura.** Pix, dinheiro/troco, maquininha na entrega e o
    widget de Crédito/Débito/VR/VA foram explorados sem submeter os valores sintéticos.
11. **[OD] Parada da primeira rodada.** Pix foi restaurado e `Fazer pedido` permaneceu
    habilitado, mas não foi acionado nessa rodada.
12. **[OD] Retomada posterior.** O usuário refez o trecho final e submeteu um pedido Pix.
13. **[OD] Handoff móvel degradado.** A transição de pagamento no celular mostrou o erro
    “conexão não é privada”, sem continuidade confiável nessa superfície.
14. **[OD] Pix copiado.** Após copiar o código, a interface avançou otimisticamente. A
    observação não prova confirmação financeira nem revela o gatilho interno.
15. **[OD] Tracking.** A página acompanhou as etapas, mas ficou atrasada em relação à entrega
    física; a mudança apareceu somente após refresh manual.
16. **[OD] Pós-entrega.** O fluxo chegou ao estado entregue sem que endereço, código Pix,
    identificador do pedido ou mensagens fossem transcritos para este relatório.

### 4.2 Estado financeiro final observado

| Linha | Valor |
|---|---:|
| 1× Kibixinha | R$ 18,00 |
| 1× Bolinho de Carne | R$ 18,00 |
| Subtotal | R$ 36,00 |
| Taxa de serviço | R$ 0,99 |
| Taxa de entrega | R$ 14,00 |
| Desconto aplicado | -R$ 6,75 |
| **Total final** | **R$ 41,99** |

**[OD]** A promessa era entrega no mesmo dia em 60–70 minutos. O endereço completo foi usado
sob autorização na sessão, mas não foi preservado em artefato versionado. A tabela retrata a
primeira rodada; a submissão ocorreu apenas na rodada posterior.

**[OD/INF]** O desconto permaneceu R$ 6,75 quando o subtotal passou de R$ 27 para R$ 36,
embora a regra exibida fosse 25% até R$ 10. Isso pode ser elegibilidade parcial, cache ou
regra não exposta. Não é possível concluir bug sem remover/reaplicar o benefício em teste
controlado.

### 4.3 Transições e URLs sanitizadas

| Transição | Evidência | Registro seguro |
|---|---|---|
| Loja → produto → carrinho | [OD] Web desktop | Somente tipo de rota; nenhum parâmetro de sessão |
| Carrinho → `/pedido/finalizar` | [OD] Web desktop | Rota estável observada |
| Checkout → widget de pagamento | [OD] Web + handoff móvel | Domínio do widget e origem funcional; query, token e ids omitidos |
| Confirmação → tracking | [OD] rodada posterior | `/pedido/{id}` como padrão redigido; id real omitido |
| Tracking → estado entregue | [OD] rodada posterior | Estado textual; sem mensagem, endereço ou identificador |

### 4.4 Matriz de decisão por etapa

| Etapa | Padrão iFood observado | Estado Shopman auditado | Oportunidade | Risco | Prioridade documental |
|---|---|---|---|---|---|
| Identidade | Login tardio preserva intenção | WhatsApp-first, `next` seguro e dispositivo confiável | Medir melhor momento do login | Copiar atraso e aumentar surpresa | Medir, não implementar |
| Endereço | Busca → ponto → detalhes; divergência é princípio oficial | Endereço estruturado e zona/taxa no Core | Executar WPs base/extensão após aprovação | GPS passivo, PII, falso positivo | P1 planejado |
| Descoberta | Contexto rico, mas busca falhou sem recuperação | Shell leve, catálogo vivo, busca acessível | Medir zero-result e oferecer saída útil | Importar excesso de marketplace | P2 de evidência |
| Produto | Quantidade e comentário simples | Conteúdo mais rico; sem variantes selecionáveis | Levantar demanda real por modificadores | Criar domínio sem operação | Hipótese |
| Carrinho | Mínimo e revisão editável | Fila otimista e reconciliação canônica | Explicar mínimo e preservar reversibilidade | Valor transitório/stale | Preservar/P2 |
| Benefício | Regra visível; desconto possivelmente stale | Elegibilidade server-side | Tornar motivo verificável | Prometer desconto incorreto | P1 de confiança |
| Pagamento | Métodos amplos, widget e Pix; handoff móvel falhou | Métodos server-driven e resultado ambíguo seguro | Validar continuidade entre superfícies | Duplicar cobrança ou perder confiança | P1 de confiabilidade |
| Confirmação | Avanço otimista após copiar Pix [OD] | Recibo e estado autoritativo | Medir diferença entre cópia e confirmação | Tratar UI como verdade financeira | P0 de invariante |
| Tracking | Estado ficou stale até refresh [OD] | SSE + polling canônico | Testar atualização real e recuperação | Progresso decorativo/atrasado | P1 de observabilidade |
| Pós-entrega | Estado entregue observado uma vez | Suporte, avaliação e reorder já existem | Preservar continuidade e ação contextual | Inferir satisfação/prevalência | Preservar |

“Prioridade documental” orienta investigação e proteção de invariantes; não autoriza backlog
nem implementação.

## 5. Comparação end-to-end

### 5.1 Entrada, localização e identidade

**iFood observado/fontes**

- **[OD]** Permite ver cobertura e catálogo como convidado; login só surgiu na intenção de
  adicionar.
- **[OD]** Oferece Facebook, Google, celular e e-mail. Celular pergunta como receber o
  código e destacou WhatsApp.
- **[FI]** O guia oficial de 01/04/2026 documenta OTP por e-mail, SMS ou WhatsApp e separa
  notificações transacionais de marketing.
- **[OD]** A exigência de login apareceu depois do toque em `Adicionar`, sem promessa
  explícita de retorno; na prática, a intenção foi preservada.

**Shopman auditado**

- **[AS]** `/entrar` prioriza WhatsApp zero-phone, com SMS/OTP, dispositivo confiável,
  retorno seguro por `next` e ponte `/a` que remove capacidade sensível da URL.
- **[AS]** Autenticação é exigida antes de abrir `/finalizar`, não ao adicionar item.
- **[AS]** Copy de preservação da sacola só aparece quando existe carrinho real.

**Conclusão comparativa**

- **Comprovado:** ambos preservam contexto; o Shopman tem boundary de sessão e recuperação
  mais explicitamente modelados.
- **[HIP]** O momento ideal do login no Shopman depende de funil. A observação do iFood não
  prova que login após `Adicionar` converte melhor, e o redirecionamento tardio também gerou
  surpresa.
- **Preservar:** WhatsApp-first, alternativa, `next` seguro, dispositivo confiável e
  capacidade fora da URL.

### 5.2 Home e descoberta

**iFood observado/fontes**

- **[OD]** Header sticky com macroáreas, busca global, endereço, perfil e carrinho.
- **[OD]** Home extensa com carrosséis, categorias, filtros, marcas, prazo, taxa e centenas
  de cards; endereço contextualiza tudo.
- **[FI]** O iFood declara personalização por histórico, turno e contexto. Pesquisa publicada
  em 2025 registra também “banner blindness” e sensação de excesso de publicidade.
- **[OD]** Skeletons preservaram a geometria, mas a árvore montada tinha cerca de 26 mil px
  de altura e houve CAPTCHAs repetidos.

**Shopman auditado**

- **[AS]** Home já prioriza status da loja, pedido ativo, reorder, destaques, busca/menu,
  visita e WhatsApp.
- **[AS]** O PR #1215, agora mesclado em `main`, separou shell leve do catálogo pesado e
  criou endpoint canônico de catálogo para menu, busca, coleções e overlay.
- **[AS]** A verdade operacional continua no servidor e o modo offline não finge dados vivos.

**Conclusão comparativa**

- A vantagem single-tenant é remover a decisão “qual loja?” e organizar por ocasião,
  categoria, disponibilidade, recompra e intenção.
- **[HIP]** Coleções por turno e contexto podem ajudar, mas só telemetry e experimento local
  distinguem relevância de banner adicional.
- **Preservar:** shell leve, pedido ativo, promessa factual, reorder e catálogo vivo separado
  do snapshot estrutural Continuum.

### 5.3 Busca

**iFood observado**

- **[OD]** Busca tem abas Lojas/Itens, query na URL e loading reconhecível.
- **[OD]** Consultas e rotas gerais terminaram no mesmo erro regional: “Ops! Tivemos um
  problema...”, sem tentar novamente, trocar região, voltar ou pedir ajuda.
- **[OD]** Nem a distinção zero-result versus indisponibilidade ficou clara.

**Shopman auditado**

- **[AS]** Busca é case/accent-insensitive, usa campos semânticos e tolerância simples a
  erros; termo e filtros são endereçáveis.
- **[AS]** Conflitos alimentares são explícitos; overlay cuida de teclado, foco, `inert` e
  Escape.
- **[AS]** Não há evidência de recentes/populares personalizados nem de funil de zero-result.

**Conclusão comparativa**

- O Shopman não deve regredir sua recuperação para copiar a apresentação do iFood.
- **Gap comprovado de evidência, não de função:** não há telemetry documentada de
  zero-results/refino/abandono no material auditado.
- **[HIP]** Recentes, populares e sugestões contextuais só devem existir se reduzirem tempo
  até o produto sem criar catálogo paralelo.

### 5.4 Loja, cardápio e produto

**iFood observado**

- **[OD]** A página da Rap1000 concentrou status, mínimo, prazo, taxa, avaliação, horários,
  endereço comercial e meios aceitos antes da compra.
- **[OD]** Drawer separou Sobre/Horário/Pagamento, mas a lista financeira era longa,
  duplicada e misturava método, bandeira e produto financeiro.
- **[OD]** Kibixinha tinha imagem, descrição, preço, quantidade, comentário e CTA com total.
- **[OD]** Faltavam peso, alergênicos, composição estruturada, estoque e sugestões.
- **[OD]** A qualidade editorial do merchant era inconsistente; havia grafias divergentes e
  erros de concordância.

**Shopman auditado**

- **[AS]** `/produto/[sku]` diferencia 404/410/falha SSR e oferece preço, peso, promoção,
  estoque, nutrição, alergênicos, dietas, traços, conservação, medidas, relacionados,
  favoritos e “Me avise”.
- **[AS]** Não existe contrato de variantes, modificadores ou complementos selecionáveis.

**Conclusão comparativa**

- **Shopman maduro:** conteúdo e confiança do produto já superam o item observado.
- **Gap comprovado:** variantes/modificadores/complementos não existem no contrato/UI do
  Shopman. Se o negócio precisar, é decisão de domínio, preço e pedido; não estado local.
- **[HIP]** A necessidade comercial e os tipos de opção ainda precisam ser levantados; a
  existência de um seletor confuso de refrigerante no iFood não justifica copiá-lo.

### 5.5 Carrinho e mínimo

**iFood observado**

- **[OD]** Drawer permitiu editar/remover, mostrou subtotal, serviço, entrega e total.
- **[OD]** Mínimo de R$ 20 excluía taxa de entrega e bloqueava progressão corretamente.
- **[OD]** Não sugeriu o menor complemento necessário.
- **[OD]** Badge e contador de cupons mostraram valores transitórios incorretos durante
  hidratação.

**Shopman auditado**

- **[AS]** Quantidade absoluta, fila serial, atualização otimista, reconciliação canônica,
  proteção contra resposta velha, rollback, substituição em `409` e recuperação em `429`.
- **[AS]** Sacola tem undo, descontos, estoque, encomenda, substitutos, alertas, retenções,
  mínimo, frete grátis, erro de zona e CTA móvel.

**Conclusão comparativa**

- **Preservar:** robustez e recuperação do Shopman; o iFood não forneceu evidência para
  substituir esse desenho.
- **[HIP]** Recomendar um complemento relevante para atingir mínimo pode reduzir atrito, mas
  deve ser honesto, server-driven e não induzir desperdício.
- **[HIP]** A posição de cupom (sacola versus checkout) precisa de observação/funil local.

### 5.6 Checkout, endereço e mapa

**iFood observado**

- **[OD]** Busca de endereço com Google Places levou obrigatoriamente a mapa, pin central e
  confirmação espacial; depois vieram número, complemento, referência e favorito.
- **[OD]** O número foi reaproveitado automaticamente.
- **[OD]** Tiles não carregaram na primeira rodada; pin e CTA funcionaram, mas não houve
  mensagem, retry ou alternativa explícita.
- **[OD]** No checkout, endereço, prazo, modalidade e resumo ficaram visíveis/editáveis.
- **[OD]** Troca de endereço preservou o pedido; estado selecionado dependia sobretudo de
  borda visual.

**Shopman auditado/WP existente**

- **[AS]** Places, ViaCEP, manual, GPS, reverse geocode, endereço estruturado e mapa já
  existem. Busca/GPS ainda não convergem sempre para confirmação visual.
- **[AS]** `delivery_address_structured` já carrega coordenadas e `place_id`; zona, distância
  e taxa são calculadas exclusivamente pelo Core.
- O WP dedicado `WP-CHECKOUT-ADDRESS-MAP-CONFIRMATION-2026-09-28.md` já especifica a
  convergência, ponto confirmado, precisão, fallback, acessibilidade, privacidade, kill
  switch, testes e rollback.

**Conclusão comparativa**

- **Gap comprovado:** falta a confirmação visual universal prevista no WP dedicado.
- Este relatório **não duplica nem substitui** o WP de mapa; a evidência direta atual o
  complementa, especialmente pela falha real de tiles sem recuperação.
- **Preservar:** endereço canônico único, coordenada confirmada, enriquecimento por reverse e
  cálculo de zona/taxa no Core. Mapa não vira autoridade paralela.

### 5.7 Entrega, retirada e agenda

**iFood observado/fontes**

- **[OD]** A loja oferecia só entrega padrão, hoje, 60–70 min, R$ 14. Retirada aparecia,
  abria “Retirada indisponível” e terminava em `Ok, entendi`.
- **[OD]** Não houve agendamento na jornada observada.
- **[FI]** Fontes oficiais documentam preparo, saída, mapa quando a logística permite,
  atraso/cancelamento e janela para recebimento.

**Shopman auditado**

- **[AS]** Entrega/retirada, disponibilidade, calendário, dias fechados, limite de
  pré-pedido e slots de retirada vêm do servidor.
- **[AS]** Fora da zona oferece retirada quando possível; impossibilidade tem saída
  explícita.

**Conclusão comparativa**

- A solução do Shopman é mais rica que o caso observado e deve ser preservada.
- Mostrar uma capacidade indisponível pode informar, mas não deve parecer selecionável; motivo
  precisa estar disponível sem criar um beco sem saída.
- Mapa de entregador/ETA interno continua **hipótese operacional**, não gap: só faz sentido
  com localização e eventos confiáveis.

### 5.8 Cupons, promoções e fidelidade

**iFood observado**

- **[OD]** Cupons ficaram bloqueados até selecionar pagamento, com motivo explícito.
- **[OD]** Drawer mostrou validade, mínimo, percentual/teto, taxas excluídas e `Ver regras`.
- **[OD]** O benefício aplicado discriminou desconto de R$ 6,75 e não afetou taxas.
- **[OD]** Campo acessível era `campaignCode`; uma regra expôs token cru de design.
- **[OD/INF]** Após mudança do subtotal, o desconto não mudou; causa não determinada.

**Shopman auditado**

- **[AS]** Cupom, benefício/fidelidade e elegibilidade são validados no servidor; oferta
  compartilhável consulta preço/estoque no clique e resolve conflito de carrinho.
- **[AS]** Checkout suporta cupom, benefícios, presente e fiscal sem mover autoridade para a
  UI.

**Conclusão comparativa**

- **Preservar:** regra e cálculo server-side, desconto discriminado, conflito explícito e
  oferta idempotente.
- Nunca expor nome técnico/token, nem anunciar benefício que some sem explicação.
- **[HIP]** Autoaplicar o melhor benefício elegível pode simplificar o single-tenant, mas
  exige regra de desempate, consentimento e prova de que não elimina escolha relevante.

### 5.9 Pagamento online: Pix, crédito, débito, VR e VA

**iFood observado**

- **[OD] Pix, primeira rodada:** selecionado em um clique; QR/cobrança só surgiriam depois de
  `Fazer pedido`, que não foi acionado nessa rodada.
- **[OD] Pix, rodada posterior:** o pedido foi criado e o código foi copiado. A tela pareceu
  avançar imediatamente após a cópia; sem instrumentação interna, não se sabe se foi estado
  otimista, polling, evento ou coincidência temporal.
- **[OD] Mobile:** o handoff exibiu “conexão não é privada”. Host, query e certificado não
  foram registrados; causa e abrangência continuam desconhecidas.
- **[OD] Widget externo:** `paymentwidget.ifood.com.br` abriu na mesma aba com
  `origin=/pedido/finalizar`, skeleton e quatro opções: Crédito, Débito, Vale-refeição e
  Vale-alimentação.
- **[OD] Crédito/Débito:** número, nome impresso, validade, CVV, apelido e CPF/CNPJ; preview
  frente/verso; CTA bloqueado até validade.
- **[OD] Pré-autorização:** copy “Faremos uma pequena cobrança com devolução automática”, sem
  valor, prazo ou descritor da fatura.
- **[OD] Débito:** “Consulte as bandeiras e bancos disponíveis”; o help não expôs conteúdo
  acessível na interação observada.
- **[OD] Vale-refeição:** Ticket, VR Refeição, Alelo Refeição e Pluxee Refeição/Sodexo.
  VR abriu o formulário; uma primeira tentativa Ticket voltou silenciosamente.
- **[OD] Vale-alimentação:** abriu o formulário-base sem seletor prévio de bandeira.
- **[OD] Validação sintética:** erros específicos para número, nome, validade, CVV, apelido e
  CPF; todos apareceram junto ao campo e na árvore acessível; nada foi submetido.
- **[OD] Parcelamento:** não apareceu no cadastro nem no checkout observado. Ele pode surgir
  após cartão válido/salvo, etapa não executada; ausência total não pode ser afirmada.
- **[OD] Retorno:** histórico preservou itens, endereço, prazo, cupom, taxas e total, mas
  removeu a seleção Pix e desabilitou `Fazer pedido` sem aviso.

**Shopman auditado**

- **[AS]** Métodos são server-driven; restrições de Pix, cartão e troco ficam no contrato.
- **[AS]** Pagamento e recuperação vivem em `/pedido/[ref]`; resultado ambíguo procura recibo
  e não reenvia cegamente.
- **[AS]** Dados Stripe de teste aparecem somente em ambiente de teste.

**Conclusão comparativa**

- **Preservar:** idempotência, estado autoritativo, recibo e pagamento na linha do pedido.
- Um widget externo deve preservar o rascunho e retornar ao ponto certo; se a forma anterior
  precisar ser reconfirmada, essa consequência deve ser anunciada.
- Pré-autorização precisa informar valor/faixa, prazo de devolução e descritor quando o
  provedor disponibilizar.
- Benefício/cartão só deve ser ofertado quando contratado pela operação; não copiar a matriz
  financeira do iFood.
- Não há evidência direta suficiente para decidir parcelamento no produto local.

### 5.10 Pagamento na entrega, dinheiro e troco

**iFood observado**

- **[OD]** Dinheiro; débito Mastercard/Visa/Elo; crédito Hipercard/Visa/Mastercard/Elo/Amex.
- **[OD]** Selecionar maquininha apenas marcou método e habilitou o CTA; sem parcelamento.
- **[OD]** Dinheiro perguntou se precisava de troco. `Sim` pediu “Troco pra quanto?”, citou
  o total e validou o valor; `Não` marcou o método.
- **[OD]** Modal de troco não tinha saída clara e `Esc` não funcionou na observação.
- **[OD]** Alternar online/entrega preservou cupom e total.

**Shopman auditado**

- **[AS]** Métodos e troco são validados pelo servidor; o checkout já modela dinheiro e
  restrições de pagamento.

**Conclusão comparativa**

- Capturar troco antes do envio é omotenashi operacional e reduz falha na porta.
- Toda modal precisa de fechar/cancelar, Escape, retorno de foco e mensagem de erro no campo.
- Chips de valor provável são apenas hipótese; nunca podem substituir entrada livre e
  validação contra o total.

### 5.11 CPF/CNPJ e nota

**iFood observado**

- **[OD]** Campo opcional `CPF/CNPJ na nota` ficava antes do CTA.
- **[OD]** Valor sintético inválido recebeu máscara e erro, mas o CTA final permaneceu
  habilitado.
- **[OD]** Switch acessível como `enableInput`; ao desligar, campo, valor e erro permaneceram
  visíveis/desabilitados.
- **[OD]** Não havia explicação clara de finalidade, salvamento ou privacidade.

**Shopman auditado**

- **[AS]** Dados fiscais são obrigatórios para entrega e opcionais para retirada; salvar é
  opt-in separado.

**Conclusão comparativa**

- O Shopman já tem política mais explícita, mas copy, erro, requisito por modalidade e
  salvamento precisam continuar alinhados ao contrato real.
- Um campo opcional desativado não deve conservar erro visual; um campo requerido inválido
  não deve parecer compatível com submissão.

### 5.12 Confirmação e pós-pedido

**iFood observado/fontes**

- **[OD]** Uma rodada posterior enviou o pedido e chegou ao tracking; código Pix,
  identificador, endereço e mensagens foram omitidos.
- **[OD]** Copiar o Pix foi seguido por avanço otimista da UI. Isso não é prova de pagamento
  confirmado nem especificação a copiar.
- **[OD]** O tracking ficou atrasado em relação à entrega física e só exibiu a mudança depois
  de refresh manual.
- **[HIP]** Chamada antecipada de entregador é uma explicação possível para sinais percebidos
  na jornada, mas não houve observação de dispatch, logs, rede interna ou operação que a
  confirme. Não tratar como comportamento do iFood.
- **[FI]** Publicações do iFood descrevem aceite do restaurante, cancelamento quando não há
  resposta, push de preparo, acompanhamento de etapas, mapa quando aplicável, código de
  entrega e Live Activities no iOS.
- **[FI]** A Apple recomenda Live Activity curta, sem anúncio, com informação essencial e
  deep link para o contexto.

**Shopman auditado**

- **[AS]** `/pedido/[ref]` combina polling canônico e SSE, com promessa, prazo, timeline,
  pagamento, Pix/cartão, stale state, suporte, cancelamento, confirmação, avaliação e reorder.
- **[AS]** SSE acelera percepção, mas polling preserva correção; status e deadline vêm do
  servidor.

**Conclusão comparativa**

- **Shopman maduro:** pagamento e tracking numa linha do tempo, degradação SSE→polling,
  cancelamento conforme ação válida e reorder com conflito explícito.
- A interface não deve avançar para “pago” por gesto de cópia; confirmação vem do provedor e
  da projeção canônica. Tracking stale precisa de detecção/recuperação, não animação inventada.
- Live Activity ou equivalente PWA é hipótese de canal, não requisito derivado da observação.
- Não criar ETA, mapa ou progresso decorativo.

### 5.13 Suporte, erro, reembolso e recompra

**iFood fontes/observação**

- **[FI]** Ajuda parte do pedido e roteia loja/plataforma; problema pode pedir descrição e
  evidência; reembolso mostra status, meio e prazo.
- **[FI]** Histórico permite recompra; personalização usa contexto e pedidos anteriores.
- **[OD]** Após login, a loja exibiu “Peça de novo”.
- **[OD]** O pior erro observado — busca regional — não ofereceu recuperação.

**Shopman auditado**

- **[AS]** Pedido ativo, histórico, repetir, favoritos, alertas, cancelamento, protocolo,
  suporte, avaliação, endereços e direitos LGPD já existem.
- **[AS]** Reorder resolve append/replace e não deve destruir carrinho silenciosamente.

**Conclusão comparativa**

- **Preservar:** ajuda contextual, contato humano, ações server-driven, protocolo e conflito
  explícito.
- A vantagem single-tenant é não obrigar o cliente a descobrir quem é responsável. A
  operação coordena internamente e devolve ação, owner e prazo.

## 6. Dimensões transversais

### 6.1 UX/UI e feedback

**Fortes no iFood [OD]**

- hierarquia clara e CTAs largos nos momentos de decisão;
- endereço, prazo e total permanecem visíveis;
- quantidade atualiza o valor do CTA imediatamente;
- skeletons aproximam a geometria final;
- edição é reversível até o último CTA;
- dependências são explicadas, como cupom bloqueado até pagamento.

**Falhas observadas [OD]**

- tela branca antes do checkout;
- contador de cupons e badge de carrinho com valores transitórios errados;
- metadata temporária `undefined`;
- erro de busca sem saída;
- retirada com falso affordance;
- mapa sem tiles e sem fallback;
- perda silenciosa da seleção de pagamento;
- modal de troco sem saída clara;
- handoff móvel de pagamento com “conexão não é privada”;
- tracking atrasado até refresh manual.

**Leitura single-tenant [INF]**

Feedback imediato só é omotenashi quando é coerente. Skeleton não justifica valor falso;
otimismo deve ser reversível e reconciliado com a fonte autoritativa.

### 6.2 Copy

**[FI]** O guia de conteúdo do iFood prioriza clareza, concisão e utilidade; humor cede em
fome, erro e dinheiro. A observação confirmou perguntas e CTAs curtos, mas também encontrou
conteúdo de merchant mal revisado, justificativa longa de taxa, tokens técnicos e finalidade
fiscal pouco explicada.

Para a Nelson:

- título nomeia o estado;
- corpo explica consequência e o que foi preservado;
- CTA descreve ação;
- prazo, valor, endereço e disponibilidade são factuais;
- humor fica na descoberta, não em pagamento, atraso ou cancelamento;
- copy operacional continua ligada à projeção/capacidade, não a string local que promete
  estado inexistente.

### 6.3 Omotenashi

Comportamentos transferíveis:

- pedir dados em camadas e reaproveitar o que já se sabe;
- conferir ponto antes de pedir complemento;
- mostrar custo e promessa antes do compromisso;
- antecipar troco, indisponibilidade e condição de cupom;
- preservar carrinho e rascunho em login/widget;
- avisar mudança material sem exigir refresh;
- não confundir gesto local, como copiar Pix, com confirmação financeira;
- abrir ajuda no contexto do pedido.

O omotenashi superior ao benchmark está nas falhas: oferecer retry/fallback no mapa, busca e
pagamento; explicar por que uma escolha foi perdida; sugerir substituto/mínimo sem empurrar
consumo; não fazer o cliente repetir dados nem diagnosticar qual sistema falhou.

### 6.4 Performance percebida

**[OD]** A sessão mostrou skeletons úteis, mas também tela branca, DOM muito longo, valores
transitórios, metadata quebrada e desafios anti-bot repetidos. Isso não produz métricas
comparáveis.

**[AS]** O merge do PR #1215 removeu catálogo pesado do caminho crítico do shell e preservou
endpoint vivo para catálogo. Essa solução deve ser medida e preservada.

**[FI]** Para Web, os limites normativos de referência são LCP ≤2,5 s, INP ≤200 ms e
CLS ≤0,1 no p75. São budgets candidatos, não medições deste benchmark.

### 6.5 Acessibilidade

**Pontos positivos do iFood [OD]**

- headings/landmarks, links integrais e avaliação “de 5 estrelas”;
- endereço operável por teclado na etapa observada;
- nomes úteis em quantidade e CTA;
- tabs/radios/métodos com estado;
- erros do widget próximos aos campos e presentes na árvore.

**Problemas do iFood [OD]**

- `checkout-label`, `campaignCode`, `backToHome`, `enableInput` e token de design expostos;
- mapa sem instrução de teclado e sem fallback;
- `prev`/`next` em inglês;
- botão de voltar do widget sem nome;
- estado do endereço escolhido sobretudo visual;
- modal de troco sem Escape;
- possível duplicação de navegação responsiva na árvore.

**Shopman [AS]** já possui skip link, foco pós-rota, live regions, `inert`, Escape, reduced
motion, safe areas e cuidados com teclado móvel. O WP de mapa exige alternativa não visual,
zoom, leitores reais e alvo mínimo.

Baseline: WCAG 2.2 AA, alvos de ao menos 44×44 CSS px, estados não dependentes só de cor e
testes reais com teclado, VoiceOver e TalkBack.

### 6.6 Privacidade e segurança

- **[OD]** O iFood pede localização no contexto, mas o login por e-mail usa aviso de marketing
  opt-out; não copiar sem revisão LGPD.
- **[OD]** Widget de pagamento separa domínio e apresenta links legais, mas a tela não explicou
  tokenização/PCI nem os detalhes da pré-autorização.
- **[OD]** O handoff móvel mostrou erro de confiança TLS. Como host, parâmetros e certificado
  não foram coletados, causa e abrangência continuam desconhecidas.
- **[OD]** Um iframe antifraude expôs identificador derivado da sessão na URL da árvore; o
  valor foi omitido.
- **[AS]** Shopman já remove capacidades sensíveis da URL, faz step-up em direitos de conta e
  mantém chaves server-side.
- **WP mapa:** proíbe lat/lng, endereço, query, CEP, `place_id` e instruções em telemetry;
  pede atualização legal antes de ativar.

Princípio: coletar somente o necessário, explicar finalidade no momento certo, não salvar por
padrão e não usar benchmark como justificativa para ampliar dados.

### 6.7 Estados de erro e retorno

| Situação | Evidência iFood | Contrato desejável/preservado no Shopman |
|---|---|---|
| Busca falha | Erro sem CTA [OD] | Próxima ação concreta; distinguir vazio de indisponível |
| Mapa falha | Pin/CTA sem tiles ou fallback [OD] | Texto, retry, manual e preservação do ponto |
| Item muda | Conteúdo pode variar [FI] | Reprice/stock canônico, substituto, sacola preservada |
| Mínimo | Bloqueio e regra exata [OD] | Bloqueio cedo, saída para adicionar ou retirar |
| Cupom | Condição visível; desconto possivelmente stale [OD/INF] | Elegibilidade e total server-side, motivo específico |
| Widget | Carrinho/cupom preservados; pagamento perdido [OD] | Preservar tudo e anunciar reconfirmação necessária |
| Handoff móvel | “Conexão não é privada” [OD] | Falhar fechado, explicar retorno seguro e nunca pedir credencial em origem não confiável |
| Pagamento ambíguo | Não observado | Idempotência, recibo e “não pague novamente” |
| Tracking stale | Entrega só apareceu após refresh [OD] | SSE + polling + refresh recuperável, com relógio/estado do servidor |
| Atraso | Ações oficiais por estado [FI] | Promise/deadline, suporte/cancelamento server-driven |
| Reembolso | Status, meio e prazo [FI] | Timeline e protocolo no pedido |

## 7. Soluções maduras do Shopman que são invariantes

1. `Action` com validade, razão, idempotência e confirmação continua dirigindo a UI.
2. Catálogo Continuum é estrutural; preço, estoque, promoção e sessão vêm do endpoint vivo.
3. Carrinho otimista é fila serial reconciliada, não verdade local permanente.
4. `delivery_address_structured` é o único contrato de endereço; mapa não calcula zona/taxa.
5. Checkout usa revisão do carrinho, chave idempotente e recibo para resultado incerto.
6. Pagamento e tracking usam projeção do servidor, não relógio/inferência do cliente.
7. SSE melhora percepção; polling mantém correção.
8. Offline/PWA não fingem disponibilidade ou pedido vivo.
9. Endereço novo só é persistido pelo Core após pedido bem-sucedido.
10. Privacidade, capacidade e step-up não podem ser enfraquecidos por conveniência visual.

## 8. Gaps comprovados versus hipóteses

### Gaps comprovados no material auditado

- confirmação por mapa ainda não é etapa comum a GPS e Places no Shopman;
- variantes/modificadores/complementos selecionáveis não existem no contrato/UI;
- `storefront-spec.md` usa nomes antigos de rotas e etapa de pagamento separada;
- não há evidência documental de RUM/funil/zero-results suficiente para comparar conversão;
- a política pública precisa refletir Maps/Places/geolocalização antes de eventual rollout do
  WP de mapa.

### Hipóteses que não podem ser promovidas a gap sem investigação

- mover o login para o primeiro `Adicionar`;
- autoaplicar promoção ou mover cupom para a sacola;
- adicionar recentes/populares/personalização de busca;
- recomendar complemento para mínimo;
- oferecer parcelamento;
- criar mapa/ETA próprio de entregador;
- expor passkey na entrada;
- implementar Live Activity/equivalente;
- criar variantes sem demanda e regras operacionais levantadas.

Não há ordem de prioridade nesta seção.

## 9. Questões de decisão para planejamento futuro

1. Qual é o momento de menor fricção para autenticar sem enfraquecer identidade, fidelidade e
   entrega?
2. Quais famílias reais de produto exigem variante, modificador ou complemento, e como isso
   afeta preço, estoque, produção e pedido?
3. Como anexar a evidência direta do iFood ao WP de mapa sem duplicar plano?
4. Onde clientes descobrem e entendem benefícios sem ocultar elegibilidade?
5. Quais métricas de funil, busca e Web Vitals já existem no Live e quais faltam?
6. Quais meios de pagamento a operação realmente oferece online e na entrega?
7. Há base operacional confiável para ETA/mapa de entregador?
8. Quais strings operacionais devem continuar server-driven e quais são conteúdo editorial?
9. Como reconciliar a spec de rotas com a implementação atual sem criar outro documento
   divergente?

Responder essas perguntas pertence a uma sessão futura de planejamento, com owners de
produto, operação, checkout, pagamento, privacidade e acessibilidade.

## 10. Fontes primárias e normativas

Consultadas na pesquisa complementar em 28/09/2026:

- [Gerenciamento de Conta e Cadastro iFood](https://institucional.ifood.com.br/ajuda/conta-e-cadastro-ifood/) — 01/04/2026.
- [Como funciona a entrega do iFood](https://institucional.ifood.com.br/ajuda/como-funciona-a-entrega-do-ifood/) — 01/04/2026.
- [Pagamentos e Carteira iFood](https://institucional.ifood.com.br/ajuda/pagamentos-e-carteira-ifood/) — 01/04/2026.
- [Como falar com o suporte](https://institucional.ifood.com.br/ajuda/pedir-ajuda-no-ifood/) — 01/04/2026.
- [Problemas com o pedido](https://institucional.ifood.com.br/ajuda/problemas-com-o-pedido-ifood/) — 06/04/2026.
- [Reembolsos e estornos](https://institucional.ifood.com.br/ajuda/reembolsos-e-estornos/) — conteúdo vigente em 2026.
- [Cupons e descontos](https://institucional.ifood.com.br/ajuda/cupons-e-descontos-do-ifood/) — 01/04/2026.
- [Bastidores: como funciona um pedido](https://institucional.ifood.com.br/institucional/como-funciona-um-pedido-do-ifood/) — 11/07/2025.
- [Entrega Fácil: confirmação/edição de endereço](https://medium.com/ifood-developer/entrega-f%C3%A1cil-novos-fluxos-de-edi%C3%A7%C3%A3o-de-endere%C3%A7o-e-confirma%C3%A7%C3%A3o-de-entrega-ac01878059c3) — 09/08/2023.
- [Recomendação de coleções no iFood](https://arxiv.org/abs/2508.03670) — 05/08/2025.
- [Design de conteúdo para UX](https://institucional.ifood.com.br/inovacao/design-de-conteudo-para-ux-ifood/) — 30/04/2024.
- [App Store — app consumidor](https://apps.apple.com/br/app/ifood-pedir-delivery-em-casa/id483017239?platform=ipad) — consultada em 28/09/2026.
- [Google Play — app consumidor](https://play.google.com/store/apps/details?gl=BR&id=br.com.brainweb.ifood) — atualizado em 21/09/2026.
- [Apple editorial — iFood](https://apps.apple.com/br/iphone/story/id1364187313) — consultado em 28/09/2026.
- [WCAG 2.2](https://www.w3.org/TR/wcag/).
- [Android Core app quality](https://developer.android.com/develop/adaptive-apps/quality-guidelines/core-app-quality).
- [Apple HIG — Live Activities](https://developer.apple.com/design/human-interface-guidelines/live-activities), atualizada em 16/12/2025.
- [Core Web Vitals thresholds](https://web.dev/articles/defining-core-web-vitals-thresholds).

Fontes secundárias da pesquisa foram usadas somente como sinais de risco, nunca para afirmar
prevalência: Reclame Aqui sobre cupom/suporte (15/02/2026), relato Reddit sobre
suporte/reembolso (05/09/2026) e relato histórico de acessibilidade no TDC (2018).

## 11. Encerramento

O benchmark confirma que uma experiência de delivery de referência é uma experiência de
confiança, continuidade e recuperação. O iFood oferece ótimos padrões de endereço, revisão e
clareza financeira, mas não é impecável; a sessão observada revelou falhas concretas que não
devem ser copiadas.

O Shopman já tem uma base transacional forte e, após o merge do PR #1215, uma fundação melhor
para medir velocidade percebida. O próximo passo deste estudo não é implementar nem ranquear
ideias: é planejar, com evidência local, quais diferenças resolvem problemas reais da Nelson
sem desfazer contratos maduros nem importar complexidade de marketplace.
