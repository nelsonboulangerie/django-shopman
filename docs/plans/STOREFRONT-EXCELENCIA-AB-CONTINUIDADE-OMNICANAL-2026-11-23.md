# Storefront Excellence — plano mestre de experiência, experimentação A/B e continuidade omnicanal

> **Estado:** PROPOSTA / SOMENTE LEITURA — nenhuma implementação autorizada por este documento.  
> **Data:** 23/11/2026. **Escopo:** Django Shopman, Storefront pré-go-live, contratos de experiência, convivência de variantes, copies, Projections e interfaces com o Framework de Comércio Conversacional.  
> **Natureza:** consolidação desta discussão; **não substitui, não edita e não reinterpreta silenciosamente** planos e ADRs vigentes.  
> **Governança:** toda mudança estrutural relevante de UX/UI exige aprovação do proprietário; este plano, por si, não autoriza deploy, migration, escrita transacional, criação de novo app ou alteração de contrato existente.

## 0. Decisão executiva em uma página

A loja atual é a **baseline A**. Uma **candidata B** deve ser desenvolvida e testada simultaneamente, conservando, por padrão, as decisões visuais principais do Storefront atual. A substituição somente ocorre após comparação verificável, aprovação e promoção controlada. O mecanismo de experimentação **é permanente**; cada variante ou experimento é **temporário**, com proprietário, duração, critérios de saída e descarte.

A experiência deve permitir que pessoas idosas, com pouca familiaridade digital, baixa visão ou dificuldades cognitivas **consigam compreender, pedir e encontrar informações sem assistência**, sem penalizar usuários experientes. Acessibilidade, clareza semântica, ausência de promessas falsas, continuidade, integridade do pedido/pagamento e segurança **não são variáveis para trade-off estético ou teste de conversão**.

**Arquitetura de referência (proposta, não estado implementado):**

```text
         Contrato de Excelência (invariantes + testes + evidências)
                            │
     Experience Registry / seleção / coortes / métricas / rollback
                  ┌─────────┴──────────┐
               A: stable          B: candidate
                  └─────────┬──────────┘
                 Presentation / Copy Profiles
                            │
           Projections + Actions + Intents canônicos
                            │
           Shopman: regras, serviços e efeitos únicos
                            │
     Guestman | Orderman | demais domínios existentes
                            ⇅
        Adaptador Shopman ↔ Framework Conversacional
                            ⇅
                   Nice / WhatsApp
```

**Questão ainda aberta e prioritária:** avaliar se a continuidade de uma intenção comercial entre canais pertence a responsabilidades existentes de **Guestman** (micro-CRM/identidade/relacionamento), **Orderman** (pedidos), à orquestração atual ou exige capacidade adicional. **Omniman não existe**: não pressupor sua criação, nem de qualquer novo domínio.

## 1. Fontes canônicas a respeitar (somente leitura)

- [EXCELENCIA-STOREFRONT-PLANO.md](EXCELENCIA-STOREFRONT-PLANO.md): auditoria e plano de excelência existente; levantou 11 P1 e 14 P2 na medição de 16/11, com limites declarados e WPs próprios. **Reconciliar com a evolução posterior do main antes de reabrir achados.**
- [WP-RELEASE-01-versoes-de-apps-sem-quebra.md](WP-RELEASE-01-versoes-de-apps-sem-quebra.md): release build-once/promote, coortes, compatibilidade, shadow e rollback; **não criar segundo mecanismo de release**.
- [COMERCIO-CONVERSACIONAL-FRAMEWORK-PLANO.md](COMERCIO-CONVERSACIONAL-FRAMEWORK-PLANO.md): núcleo conversacional independente de plataforma; contratos e suíte de conformidade.
- [COMERCIO-CONVERSACIONAL-ADAPTADOR-NICE-PLANO.md](COMERCIO-CONVERSACIONAL-ADAPTADOR-NICE-PLANO.md): adaptador da Nice, com fronteiras explícitas e convivência.
- [ADR-043](../decisions/adr-043-release-contract.md), quando disponível sob o nome/path vigente: consultar a fonte canônica no índice; não supor que o link relativo é definitivo.
- [ADR-049 — comércio conversacional](../decisions/adr-049-comercio-conversacional-pacote-puro.md).
- [Storefront spec](../reference/storefront-spec.md), [vocabulário](../reference/suite-vocabulary.md), [regras de release](../reference/release-contract.md) e políticas de Omotenashi/copy.
- Código vigente: `surfaces/storefront-nuxt/`, `shopman/storefront/`, `shopman/shop/projections/`, `shopman/shop/models/omotenashi_copy.py`, `shopman/shop/projections/copy.py`; confrontar também Guestman, Orderman e os outros donos de estado relevantes.

**Regra de precedência:** ADR/contrato vigente e comportamento atual efetivamente medido > plano anterior > hipóteses desta discussão. Divergências devem ser descritas em matriz, **não resolvidas por edição silenciosa de documentos históricos**.

## 2. Objetivos e não objetivos

### Objetivos

1. Auditar **a experiência prática real**, percorrendo UI em navegador e dispositivos/viewport representativos, além de leitura de código.
2. Comparar **A e B simultaneamente**, com jornadas e cenários equivalentes, preservando a A durante toda a experimentação.
3. Canonizar **capacidade permanente de experimentação**, reutilizando release/flags/coortes existentes; testar sem interromper experiência corrente.
4. Isolar **copies configuráveis via Admin** entre variantes, mantendo a fonte central e seus defaults; permitir edição, prévia, publicação e reversão.
5. Preservar compatibilidade de **Projections/Actions**, sem forkar verdade de preço, estoque, prazo, pagamento e lifecycle.
6. Formular um **Contrato de Excelência verificável** para clareza, acessibilidade, continuidade, estética, segurança e promessas verdadeiras.
7. Investigar **continuidade omnicanal** com Guestman, Orderman, Storefront e framework conversacional antes de propor novo domínio.
8. Priorizar mercado brasileiro (WhatsApp, Pix, encomendas, retirada e entrega) e confrontar benchmarks iFood, Delivery Direto, Goomer, Panera Bread, Toast e Olo com evidências e data.

### Fora do escopo de autorização

- Implantar B, alterar serviço ou modelo, criar tabela, migration, regra comercial ou novo micro-app.
- Modificar os quatro documentos-fonte, ADRs vigentes ou qualquer código de produção sem fase/PR autorizados.
- Prometer acessibilidade certificada ou superioridade frente a benchmarks sem bateria real.
- Fazer `shadow` executar pedidos, cobranças, reservas, mensagens ou qualquer efeito externo.
- Colocar Storefront ou particularidades da Nelson dentro do núcleo agnóstico do Framework.
- Tratar Omniman como componente existente ou como solução previamente escolhida.

## 3. Invariantes do Contrato de Excelência

**E1 — Verdade e promessas.** Cada afirmação material ao cliente (preço, estoque, entrega, prontidão, pedido recebido/aceito, cobrança, reembolso, prazo) deve derivar de fonte autoritativa e estado correto. Texto editorial jamais reclassifica status comercial.

**E2 — Autorização e efeito.** Intents/Mutations e efeitos permanecem sob os domínios. A variante visual não autoriza ações novas, não confirma em nome do cliente e não cria efeito duplicado.

**E3 — Continuidade.** Retorno por WhatsApp, recarga, internet instável, navegação de volta, troca de aparelho autorizada ou pagamento externo não devem provocar perda silenciosa ou duplicação. Estado incerto deve aparecer como **incerto**, com recuperação idempotente.

**E4 — Semântica inequívoca.** Cada termo/CTA corresponde a consequência única. “Recebido”, “aceito”, “pago”, “reservado”, “produzido”, “pronto”, “enviado” e “entregue” são estados distintos.

**E5 — Acessibilidade universal.** Testar WCAG 2.2 AA nos fluxos essenciais, VoiceOver/TalkBack, teclado, zoom, contraste, alvos de toque, leitura de erros, fontes ampliadas e baixa carga cognitiva. Não criar um “modo idoso” como substituto de interface-base acessível.

**E6 — Design preservado.** Identidade, tipografia, cores, ritmo, composição e padrões atuais são referência. Correções necessárias podem ser feitas; mudança conceitual exige proposta, comparativo e aprovação.

**E7 — Regressão zero nas capacidades críticas.** A/B não pode piorar a segurança, preços, disponibilidade, identidade, autorização, notas fiscais ou continuidade do pedido.

**E8 — Avaliação justa.** A/B precisa de seleção estável, exposição registrada, cenários comparáveis e resultados segregados por perfil. Não inferir causalidade de diferenças observacionais sem desenho adequado.

**E9 — Reversibilidade.** Kill switch da variante é independente de rollback de release; rollback não apaga efeitos já aceitos, pedidos ou comprovantes.

**E10 — Conservação de autoridade.** Guestman, Orderman, outros domínios, Projections e núcleo conversacional mantêm seus donos. Qualquer autoridade nova exige justificativa explícita e prova de que não duplica.

## 4. Arquitetura da experimentação: solução preferencial e alternativas

### 4.1 Reutilizar release, não bifurcar o produto

Adotar o modelo preferencial do WP-RELEASE-01: uma surface Nuxt com variantes de componentes/fluxos selecionadas pelo BFF/servidor, consumindo os mesmos contratos. Builds imutáveis, coortes e rollback aderem ao mecanismo de release existente. Segunda surface/processo só diante de incompatibilidade técnica demonstrada, registrada em ADR.

Pré-go-live: **A congelada como baseline reproduzível**, B candidata em trabalho isolado; homologação em ambientes/sessões de teste para não poluir dados. Após go-live: padrão estável para todos, candidatas visíveis apenas a coortes autorizadas antes de eventual piloto. Não é necessário tráfego aleatório de clientes reais para uma primeira comparação supervisionada.

A identidade de variante deve permanecer aderente à sessão/jornada; uma recarga não pode alternar versões. Controle server-side, sem confiar em query/cookie manipulável como autorização. Permitir troca deliberada em modo QA, com indicação explícita e isolamento de cenário.

### 4.2 Registro de experimento (contrato conceitual)

```text
experiment_id; scope; owner; hypothesis;
stable_experience; candidate_experience;
eligible_cohorts; assignment_policy; assignment_version;
release_id/build_digest; copy_profile_revision;
projection_contract_baseline; start/end; rollback_policy;
exposure_event; outcome_metrics; evidence_bundle;
approval_state; retirement_date
```

**Não pressupor tabela nova.** Auditar RuleConfig, flags/coortes e dados de release existentes. Se o controle atual bastar, apenas estender contrato e testes. É proibido ter dois control planes concorrentes para o mesmo rollout.

### 4.3 Duas classes de comparação

- **Teste controlado de experiência:** mesmas jornadas, usuários/personas, dados fixados e condições de relógio/rede equivalentes; alternar ordem A/B e verificar entendimento, erros, tempo, recuperação e qualidade percebida.
- **Experimento de política comercial ou IA:** exige elegibilidade, seleção, probabilidades quando houver sorteio, consentimento/autoridade apropriados e registro próprio no Framework. Não confundir um teste visual com decisão comercial contrafactual.

## 5. Copy Profiles: resolver o isolamento sem duplicação

### 5.1 Estado atual a preservar

`OmotenashiCopy` usa chave `key + moment + audience`, override por Admin e default no registro de código; `build_copy()` resolve namespaces em catálogo de leitura. **Essa resolução permanece válida para o fluxo atual** quando não houver contexto experimental.

### 5.2 Requisito de isolamento

Editar a copy de B **não pode** modificar a copy que A vê. A deve continuar funcionando com a mesma semântica e defaults. A B herda o catálogo comum quando não houver override próprio.

Resolver conceitualmente por:
```text
semantic_key + moment + audience + experience_profile + published_revision
   → resolved title/message
```

Uma versão publicada deve ser imutável para fins de reprodutibilidade; edição via Admin cria rascunho/revisão e só passa a valer após publicação explícita. A/B/rollback seleciona um perfil/revisão coerente com o build/experiência. Um override editorial B jamais muda autoridade ou efeitos de uma Action.

### 5.3 Regras de compatibilidade

1. Sem perfil informado: mesma resposta da implementação legada (teste golden).
2. Perfil B sem override: herda texto canônico válido.
3. Mudar rascunho B: nenhuma mudança em A nem na B publicada.
4. Publicar B: só a coorte B recebe as novas mensagens.
5. Rollback B→A: restaura interface + copy revision + critérios de apresentação.
6. Textos de segurança, termos financeiros e estados do pedido: sujeitos a validação de promessa e, quando necessário, não experimentáveis.
7. Cache deve incluir perfil/revisão (ou isolar por namespace equivalente) e invalidar corretamente; nunca permitir *cache bleed* entre variantes, públicos ou momentos.
8. Preview no Admin deve exibir a variante e estado (rascunho/publicada) sem publicar por engano.

**Decisão técnica em aberto:** estender `OmotenashiCopy` com revisão/perfil, adicionar entidades leves de publicação ou resolver por overlay versionado; comparar alternativas por migração, cache, desempenho e preservação de comportamento. **Não escolher esquema sem auditar o Admin, os resolvers e as projeções consumidoras.**

## 6. Projections: preservar fluxo, não congelar implementação

A e B devem consumir as **mesmas Projections/Actions/Intents canônicas** quando possível. A apresentação pode divergir, os fatos comerciais não. Evoluções são preferencialmente aditivas/opcionais, com fallback comprovado; remover/renomear/reinterpretar campos requer plano de compatibilidade e janela de aposentadoria.

**Matriz de mudança:**

| Alteração | Tratamento obrigatório |
| --- | --- |
| Campo opcional novo | Compatibilidade A/B e fallback seguro |
| Action nova | A deve ignorar/entender de modo seguro; B não inventa autoridade |
| Estado novo | Exhaustividade/estado desconhecido e teste de apresentação para todos os consumidores |
| Campo renomeado | Adaptador compatível e fase explícita de retirada |
| Mudança de significado | Novo contrato/versionamento; proibido silently |
| Campo retirado | Prova de nenhum consumidor ativo + fase de contract |
| Regra de preço, estoque, pagamento | Fora de A/B de UX; revisão de domínio própria |

**Testes:** snapshots semânticos (não só JSON), contract tests sobre A e B, estados extremos, erro/desconhecido, estabilidade de ordem/identidade, replay determinístico com relógio controlado, e shadow read-only onde adequado. Shadow **nunca** executa mutações; a escrita tem executor único, idempotência e recibo.

O **Contrato de Excelência não deve virar uma Projection paralela nem serviço de decisão de negócio**. Ele define as condições que cada Presentation/canal deve demonstrar sobre os fatos já projetados.

## 7. Interação com Framework de Comércio Conversacional (sem acoplamento)

Preservar ADR-049: núcleo `conversational-commerce` é genérico, puro, agnóstico de linguagem visual, canal, modelo, framework web e empresa. Nice é adaptador/perfil inicial. Não importar Storefront, OmotenashiCopy, Guestman ou Django para dentro do núcleo.

Reaproveitar princípios compatíveis:
- **Fato com lastro:** oferta, promessa e status só com fonte/validade.
- **Compromisso com dono:** pedido, verificação, prazo e retorno não desaparecem quando uma tela/conversa termina.
- **Efeito com prova:** termos mostrados, autorização, comando único, recibo e reconciliação.
- **Incerteza explícita:** ausência de resposta não significa fracasso ou sucesso.
- **Medição separada:** trajetória de UX e política comercial são observáveis, mas não equivalentes.

O vínculo deve ocorrer por contratos/adaptadores Shopman: referências a cliente/episódio/estado de comércio e acesso autorizado a Projections/Actions, sem duplicar carrinho, pedido, reserva ou gateway.

### 7.1 Continuidade omnicanal como hipótese, não funcionalidade pressuposta

Cenário de referência: cliente conversa com Nice no WhatsApp sobre uma encomenda, abre Storefront para fotos e quantidades, volta ao WhatsApp para esclarecer informação e finaliza no Storefront. O sistema deve distinguir **identidade**, **intenção/episódio**, **sacola/sessão comercial** e **pedido formalizado**. Um cliente pode ter dois assuntos em paralelo.

Não presumir que a existência de identidade reconhecida autoriza acesso à sacola/pedido em outro canal. Exigir vinculação/autorização segura, isolamento de sessões, consentimento apropriado, revogação, expiração e proteção contra atribuição errada de episódio.

### 7.2 Questão arquitetural para investigação adversarial

**Omniman NÃO existe no Shopman e não deve constar como dependência.** Comparar hipóteses:
- **H1 — Guestman ampliado:** identifica pessoa, vínculos de canal, preferências e contexto de relacionamento; avaliar se “intenção em andamento” caberia em sua responsabilidade sem transformá-lo em motor transacional.
- **H2 — Orderman + Guestman + adaptadores existentes:** pedido e ciclo de vida no Orderman; CRM e identidade no Guestman; sessão/intent onde já exista autoridade; continuidade resolvida por contrato entre os dois.
- **H3 — capacidade fina de coordenação:** somente se persistir lacuna comprovada; definir dono mínimo, entradas, saídas, eventos, permissões e ciclo de vida, sem reimplementar regras de Orderman/Guestman.
- **H4 — novo domínio/app:** **último recurso**, após prova de que alternativas anteriores produzem acoplamento ou duplicação piores. Não chamá-lo de Omniman por antecipação.

Pergunta decisiva: **há necessidade de entidade canônica de intenção comercial pré-pedido, independente de canal, ou já existe equivalência adequada em Session, Conversation/Episode e estruturas do Shopman?** Auditar relações, donos, cardinalidade (múltiplas intenções por pessoa), anonimizados, vinculação tardia e desvinculação segura antes de criar entidade.

**Saída esperada da investigação:** inventário do código vivo e respectivos donos, matriz CRUD/fonte de verdade, diagrama de sequência de transição WhatsApp↔Storefront, cenário anônimo→identificado, riscos de sobreposição, alternativas e recomendação fundamentada. Não criar app durante esta fase.

## 8. Experiência prática e preservação visual

### 8.1 Evidência exigida

A auditoria não se resume à leitura de código. Usar stack real de testes, Playwright, screenshots comparáveis, inspeção visual de estados completos, VoiceOver/TalkBack quando viável e observação de usuários reais. Registrar timestamp, commit, ambiente, viewport, dispositivo, dados e limitações. Antes de repetir testes, consultar relatório de excelência de 16/11 e testes/jornadas posteriores para evitar duplicação.

Jornadas mínimas: visitante busca informação; busca de produto; variante de disponibilidade/futura fornada; PDP; adicionar/editar sacola; retirar hoje; encomendar amanhã; entregar em/out-of-zone; identificar por WhatsApp ou SMS; Pix/copiar e colar; cartão; cupom; pagamento incerto; erro de rede; item esgotado entre leitura e envio; cancelamento; acompanhar; recompra; sessão interrompida/retomada; retorno entre canais.

Matriz de contexto: 320/360/375/390 CSS px, desktop, teclado virtual aberto, zoom 200/400%, fonte aumentada, VoiceOver/TalkBack, teclado, conexão lenta/offline, loja aberta/fechada, virada do dia, alteração de disponibilidade. Enfatizar iPhone e Android reais quando houver acesso.

### 8.2 Classificação das mudanças visuais

- **L1 — correção conservadora:** legibilidade, contraste, alvo, foco, copy errada, anúncio de estado, conteúdo cortado, fricção comprovada sem mudança conceitual.
- **L2 — refinamento localizado:** reorganização, disposição de ações, progressive disclosure e refinamento de etapa; exigir before/after e teste.
- **L3 — mudança estrutural:** nova navegação, arquitetura de checkout, hierarquia ou identidade marcadamente diversa; **aprovação explícita do proprietário antes de implementar**.

**Baseline visual atual é a referência canônica.** Não confundir acessibilidade com estética genérica ou simplificação infantilizante. Preservar linguagem autoral da marca com explicações onde necessário. Alterações obrigatórias de segurança/semântica/a11y não podem ser rejeitadas só por preferência visual; apresentar a solução menos disruptiva e a justificativa.

### 8.3 Benchmark

Comparar iFood, Delivery Direto, Goomer, Panera, Toast e Olo por capacidades observadas: descoberta, retirada/encomenda, clareza de disponibilidade, checkout, pagamento, recompra, suporte, acessibilidade, estado incerto e continuidade. Registrar fonte, data, plataforma e evidência; não afirmar paridade ou “superioridade” por marketing. Foco em WhatsApp, Pix, produção artesanal, promessas condicionais e retirada.

## 9. Protocolo A/B e métricas

**A é baseline versionada e executável**; B é candidata isolada. Usar cenários seed equivalentes, relógio fixo quando cabível, gateway falso em QA e bancos/sessões de teste segregados onde necessário. Nada de pedidos/cobranças reais em dois caminhos para comparar. Capturas e traces da mesma jornada em A/B.

**Portões de elegibilidade antes de métricas:** sem violação de segurança/contrato; pagamentos/pedidos consistentes; WCAG 2.2 AA nos fluxos essenciais; promessas corretas; zero perda silenciosa e zero duplicação por retry; rollback testado.

**Métricas comparativas propostas (metas, não fatos atuais):**
- Tarefa concluída sem assistência e interpretação correta do compromisso, separadas por perfil.
- Tempo e toques para concluir, inclusive recompra experiente.
- Erros, retornos, campos corrigidos, bloqueios sem saída e abandono por causa conhecida.
- Sucesso em recuperação de rede, OTP/WhatsApp, Pix e renovação de sessão.
- Regressões de performance, estabilidade visual, Web Vitals e leitor de tela.
- Satisfação/clareza percebida, junto a observação direta.
- Métricas comerciais posteriormente, com cuidado de atribuição e amostra.

**Critério de decisão:** B não vence por média única: precisa passar os portões, melhorar materialmente fricções prioritárias e **não penalizar significativamente usuários experientes**. Se houver trade-off, apresentar evidência e pedir decisão explícita. A escolha pode ser A, B ou uma síntese documentada.

## 10. Ondas do plano (somente proposta, sem execução autorizada)

| Onda | Objetivo | Evidência/entrega | Condição de saída |
| --- | --- | --- | --- |
| **P0 — Inventário e lacunas** | Contrastar planos existentes, ADRs, código atual e QA posterior | Matriz fato/hipótese/defeito fechado, donos e conflito | Nenhuma decisão apoiada só em plano histórico |
| **P1 — Contrato canônico** | Redigir ADR proposto e critérios E1–E10, sem alterar ADRs existentes | Proposta revisável, mapa de interfaces e critérios mensuráveis | Dono aprova decisões arquiteturais |
| **P2 — Isolamento A/B/copy** | Desenhar reutilização de release + perfis/revisões; risco cache/rollback | Especificação, alternativas e testes de não-contaminação | A continua idêntica no cenário legado |
| **P3 — UX real da A** | Inspecionar navegador, mobile, acessibilidade e jornadas | Capturas/traces, achados reproduzíveis, severidade | Baseline suficiente para A/B |
| **P4 — Candidate B** | Especificar correções e evolução L1/L2; L3 mediante aprovação | Backlog test-first com critérios de aceite e componentes impactados | Sem alteração sem autorização |
| **P5 — Validação A/B** | Rodar ambos sob condições equivalentes | Resultados comparativos e regressões, por persona | Portões obrigatórios satisfeitos |
| **P6 — Promoção** | Plano de escolher, promover, monitorar, reverter e aposentar variante | Checklist de release/digest/copy/compatibilidade | Decisão explícita do dono |
| **P7 — Continuidade omnicanal** | Investigar Guestman/Orderman/Framework, preferencialmente paralela às fases P0–P2 | Laudo com hipóteses H1–H4 e decisão mínima | Nenhum domínio novo presumido |

As ondas acima são **estrutura de investigação e planejamento**; qualquer implementação futura requer PR/ordem de execução próprios, gates e revisão.

## 11. Testes de aceitação adversariais mínimos

1. Admin muda rascunho B; A publicada permanece byte a byte igual no catálogo para mesmo momento/público.
2. Publicação de B não altera a revisão que A consome; rollback de B restaura toda apresentação coerente.
3. Cache aquecido por A não entrega texto B, e vice-versa; verificar público/momento/revisão.
4. Projection nova com campos extras não quebra A; campo opcional ausente mantém B funcional.
5. Novo estado comercial desconhecido nunca vira “pago”, “confirmado” ou “disponível” por fallback.
6. Desligar B durante checkout não executa segundo commit; tentativa idempotente recupera pedido já aceito.
7. Falha após envio mostra verdade do estado e caminho seguro; cliente não precisa adivinhar se deve comprar novamente.
8. WhatsApp↔Storefront não confunde pessoas, sacolas, pedidos ou episódios paralelos.
9. Comprador com fonte ampliada e teclado aberto conclui a jornada em smartphone sem ocultação de CTA ou conteúdo decisivo.
10. Leitor de tela anuncia nome, preço, disponibilidade, erro e consequência do envio em ordem lógica.
11. Variante não cria diferenciação de preço, estoque, pagamento, autorização ou promessa por iniciativa própria.
12. Rollback lógico do experimento e rollback de artefato são testados separadamente, sem apagar obrigações já assumidas.

## 12. Pontos explicitamente pendentes de decisão

- **D1:** extensão exata de copy profile/revision: schema, cache e Admin; escolher após auditoria de implementação.
- **D2:** granularidade do A/B: página, fluxo ou experiência completa; estratégia de aderência no checkout.
- **D3:** mecanismo de QA comparável (dois endpoints ou coortes de um único deploy) sem se opor ao WP-RELEASE-01.
- **D4:** critérios quantitativos de homologação por perfil e regressão aceitável para usuários experientes.
- **D5:** classificação L3 e governança de aprovação visual.
- **D6:** localização da continuidade pré-pedido: Guestman, Session/Orderman, adaptadores ou eventual nova capacidade, após análise de código.
- **D7:** semântica e permissão de handoff entre canais, especialmente visitante anônimo, número WhatsApp e cliente autenticado.
- **D8:** fronteira de métricas UX vs `DecisionRecord` de política conversacional.
- **D9:** sequência com os WPs atuais em andamento para não conflitar com execução concorrente.

Nenhuma dessas decisões deve ser convertida em implementação implícita.

## 13. Prompt executivo para agente de engenharia (SOMENTE LEITURA)

> Audite a árvore atual de `main` e os planos/ADRs relacionados, sem tocar em nenhum arquivo ou configuração. Considere o presente documento como proposta de investigação, não autorização para executar. Confronte nossa intenção de A/B permanente e de excelência UX com o WP-RELEASE-01 e o contrato vigente. Examine a resolução atual de OmotenashiCopy/CopyCatalog, risco de contaminação A/B e opções mínimas de isolamento versionado. Verifique os contratos vivos de Projections/Actions/Intents, enumere pontos que poderiam quebrar a A e proponha gates de compatibilidade. Analise o Framework Conversacional e seu adaptador Nice sem violar o núcleo agnóstico. Principalmente, investigue se Guestman, Orderman e demais capacidades existentes já resolvem a continuidade comercial omnicanal, inclusive intenção pré-pedido, múltiplos episódios e acesso anônimo→identificado; **Omniman não existe**. Traga evidências de código (commit, path:line), alternativa recomendada e contraditório, matriz de WPs dependentes, riscos/mitigações e próximos PRs sugeridos. Não criar app nem alterar os planos atuais. Preserve o design do Storefront; mudanças L3 dependem de aprovação. Entregue somente laudo e plano refinado para decisão.

## 14. Conclusão e regra de ouro

**A versão B precisa demonstrar que merece substituir a A.** O cliente não pode sofrer com experimentos, as copies de uma candidata não podem vazar para a experiência estável, e nenhuma evolução de Presentation pode inventar uma segunda verdade comercial.

A infraestrutura de experimentação permanece; variantes e suas dívidas não. A continuidade omnicanal deve nascer da autoridade já existente, se possível, e só justificar um novo domínio após prova da lacuna. **SIREL: simples, robusto e elegante — sem empobrecer a experiência e sem duplicar o negócio.**
