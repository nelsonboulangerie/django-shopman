# ADR-037 — Titularidade das decisões

**Status:** Aceito
**Decisão:** dono, 2026-10-16
**Data:** 2026-10-16
**Escopo:** kernels em `packages/`, orquestrador em `shopman/shop`, command/query ingress e superfícies
**Consolida:** ADR-001 §1, ADR-005 §3, ADR-019 e o método de `CORE-BOUNDARIES-AUDIT.md`

---

## Contexto

A suite já possui a regra de independência dos kernels e um orquestrador deliberadamente
cross-domain. Faltava uma regra única para decidir quem é dono de cada decisão. Na ausência
dela, uma pergunta de domínio pode ser respondida no pacote e novamente no orquestrador, ou
uma política que só existe no encontro de domínios pode ser empurrada para um kernel.

O problema não é a existência de adapters, projections ou services. Esses são mecanismos.
O problema é haver mais de uma implementação autoritativa para a mesma pergunta.

## Decisão

> A pergunta canônica de um domínio pertence ao kernel daquele domínio. A política que só
> existe porque dois ou mais domínios se encontram pertence ao orquestrador. Composição e
> titularidade não atravessam essa fronteira.

### 1. Uma decisão tem um dono e um ponto canônico de entrada

Cada decisão expõe um ponto público autoritativo e devolve um resultado que preserve a razão
da decisão. Isso não significa um único verbo por pacote: um domínio pode ter várias decisões
e mutações legítimas. Significa que a mesma decisão não pode ser recalculada por outro dono.

O orquestrador pode aplicar gates, sequenciar chamadas e combinar resultados. Ele não pode
copiar a árvore decisória de um kernel. Um kernel não pode absorver política que dependa do
vocabulário de outros domínios.

### 2. Composição e política cross-domain pertencem ao orquestrador

- **Composição** decide quem participa, em que ordem e sob qual configuração.
- **Política cross-domain** decide uma regra que só tem sentido no encontro de domínios.

Ambas vivem em `shopman/shop`, conforme ADR-005. Não viram pacote pip enquanto forem política
da aplicação. O fato de uma política usar preço, cliente e pedido não transfere sua
titularidade para Offerman, Guestman ou Orderman.

### 3. Mecanismo não define titularidade

Service, adapter, handler, projection, API e Admin são formas de entrega ou execução. A
localização de uma decisão é definida pela pergunta que ela responde, não pelo mecanismo em
que o código começou.

Query/read-side apenas apresenta decisões já tomadas. Command ingress valida transporte,
autorização e idempotência e delega ao dono; não cria uma segunda implementação.

### 4. Bridges opt-in da ADR-001 continuam válidas

Esta ADR não substitui nem restringe a exceção deliberada da ADR-001:

- código de domínio de um kernel (`models/`, `services/`, `protocols/`, `api/`, `admin.py`)
  não importa outro kernel;
- bridges cross-kernel podem existir somente em `adapters/` ou
  `contrib/<outro_kernel>/`;
- a bridge é opt-in, nomeada e usa imports lazy;
- sua importação precisa continuar segura sem o outro kernel instalado.

Uma bridge conecta donos; ela não muda o dono da decisão nem autoriza duplicá-la. Signal é
usado para anunciar efeito sem retorno; porto/adapter, apenas quando o retorno síncrono ou a
variação real de implementação o exige, nos termos da ADR-001.

### 5. Testes de localização

Ao decidir onde algo mora:

1. Se a pergunta usa apenas invariantes e vocabulário de um domínio, pertence ao kernel.
2. Se a regra depende semanticamente de dois ou mais domínios, pertence ao orquestrador.
3. Se há ledger próprio e imutável, a história pertence ao domínio que registra o fato;
   agregações e políticas sobre fatos alheios não ganham o ledger.
4. Se mover o código exigiria importar models ou linguagem de kernels irmãos, o destino
   proposto está errado.
5. Se dois lugares respondem a mesma pergunta, um deles deve delegar ou desaparecer por uma
   transição compatível com a ADR-015.

### 6. Aplicações imediatas

- **Preço:** Offerman possui preço de lista e faixas da oferta. Promoção e preço contextual
  que combinam oferta, cliente, canal ou pedido pertencem ao orquestrador e entram pelo porto
  de pricing do Offerman (ADR-019).
- **Promessa:** Stockman possui a decisão de disponibilidade prometível. O orquestrador pode
  usá-la como gate de um fluxo, mas não recalculá-la.
- **Identidade:** Doorman possui autenticação, desafio, credencial e confiança. Guestman possui
  identidade comercial e contatos. A conversa entre ambos ocorre por contrato ou bridge
  permitido pela ADR-001, nunca por import cross-kernel em service de domínio.

## Consequências

### Positivas

- Mudanças de requisito têm um lugar autoritativo.
- Kernels permanecem instaláveis e testáveis isoladamente.
- O orquestrador continua denso por propósito, sem usurpar decisões de domínio.
- Read-side e superfícies não se tornam donos acidentais de regra.

### Custos

- Duplicações existentes precisam de caracterização e corte explícito.
- Alguns movimentos exigirão evolução de contrato, não simples mudança de arquivo.
- A unicidade semântica não pode ser provada apenas por um gate de imports; precisa de
  contract tests e cenários de mudança por decisão.

## Invariantes

- Uma decisão canônica tem um dono e um ponto autoritativo de entrada.
- Kernel não reimplementa política cross-domain; orquestrador não reimplementa decisão de
  um único kernel.
- Bridges opt-in, nomeadas e lazy da ADR-001 são a única exceção aos imports cross-kernel e
  não transferem titularidade.
- Projections, APIs e superfícies delegam decisões; não as duplicam.
- Mudança de titularidade preserva comportamento ou segue expand-contract quando a ADR-015
  estiver ativa.

## Referências

- [ADR-001 — Cores independentes e bridges opt-in](adr-001-protocol-adapter.md)
- [ADR-005 — Orquestrador como centro de coordenação](adr-005-orchestrator-as-coordination-center.md)
- [ADR-015 — Compatibilidade pós-produção](adr-015-backward-compat-policy-post-prod.md)
- [ADR-019 — Promoção pertence ao orquestrador](adr-019-promotion-belongs-to-the-orchestrator.md)
- [ADR-021 — B.I. é read-side](adr-021-bi-cross-suite-read-layer.md)
- [ADR-022 — Ledger do Cashman](adr-022-cashman-ledger.md)
- [Auditoria de fronteiras do Core](../plans/CORE-BOUNDARIES-AUDIT.md)
