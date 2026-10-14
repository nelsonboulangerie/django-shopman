# Coordenação até o go-live (passagem para qualquer agente)

> Documento vivo. Quem assume a coordenação lê isto inteiro, depois o `CLAUDE.md`,
> e atualiza a seção "Estado" ao encerrar o turno. Vale para Claude, Codex,
> DeepSeek ou humano. Atualizado em 14/10/2026.

## 1. O papel

Coordenar o Shopman da Nelson Boulangerie até a virada para produção.

- **Falar com o dono (Pablo) em português, curto, no chat.** Ele não lê documento: a
  pergunta vai inteira na conversa, com as opções e a recomendação, respondível com
  "1", "2" ou "sim". Documento é registro entre sessões, nunca canal com ele.
- **O óbvio não se pergunta.** Se um anfitrião atento faria sem pedir licença, faça e
  relate em uma linha. Coerência entre canais (o que vale na loja online vale no PDV)
  é correção de defeito, não decisão. Pergunte só o que muda negócio, lei, dinheiro,
  escopo, ou contradiz uma decisão dele. Antes de perguntar, procure a decisão em
  `docs/reference/` e `docs/decisions/`: o que ele já decidiu não se reabre.
- **Delegar.** Cada frente vai para um agente em worktree próprio (uma frente = um
  branch = um PR). A coordenadora acompanha até MERGED e não deixa trabalho dormente
  (seção "A ESTEIRA" do `CLAUDE.md`).
- **Garantir qualidade.** Todo trabalho visual passa pelo checklist D1 a D12 (seção 3);
  a coordenadora abre as capturas e audita antes de mostrar ao dono. Copy reprovada
  volta ao agente; o dono não vê rascunho.

## 2. Regras comuns (cole no começo de todo brief de agente)

1. Worktree próprio; `git add` só arquivo nomeado; nunca `git stash` puro.
2. Esteira no mesmo turno: commit, push, PR, `gh pr merge <N>` (fila de merge). PR
   draft só sai de draft completo e verde.
3. Vermelho: nomear a causa lendo o log. "Marketing — cadeia completa" é flake
   conhecido (reexecutar). Saída da fila por check: ler o run do `merge_group`.
4. Baseline visual só a CI regenera (`docs/reference/operator-visual-baselines.md`).
5. Conjunto mínimo Nuxt UI (md/xl; solid/outline/ghost; primary/neutral/error); `:ui`
   mora uma vez no kit.
6. Copy inequívoca, curta, sem travessão, vocabulário de
   `docs/reference/suite-vocabulary.md` e `docs/reference/omotenashi-copy.md`;
   "dispositivo", nunca "aparelho" (fora do Storefront).
7. Core (`packages/`) é sagrado: mudança só com necessidade medida; chave nova de
   JSONField entra antes em `docs/reference/data-schemas.md`.
8. Testes do app tocado e do kit; geometria/e2e quando é layout.
9. Prévia testada num navegador de verdade, zero 4xx/5xx, capturas antes/depois
   claro/escuro com nome único da frente.
10. Faixa de portas própria por agente; matar só os próprios processos.
11. Janela apertando: commit, push, PR draft "WIP:" e o próximo passo exato.
12. Scratchpad é compartilhado: nome de arquivo único com o número do PR.
13. Worktree não testa `packages/*` sozinha: `PYTHONPATH`/`PYTHON` explícitos, ou
    `pytest -o "pythonpath=. packages/..."` com o `.venv/bin/python` da raiz.
14. Depois do MERGE, apagar `node_modules`, `.nuxt`, `.output` da própria worktree
    (caminho literal).

## 3. Checklist de design do dono (relatar "D1 OK" item a item)

- D1. Cartão de topo `outline`; cartão dentro de cartão `soft` sem borda. Selo sempre `soft`.
- D2. Cards sem cabeçalho/rodapé destacado salvo necessidade real.
- D3. Botões só do conjunto mínimo; conteúdo centrado; botão não estica além do necessário.
- D4. Alinhamento borda a borda dentro do bloco.
- D5. Peças irmãs de tamanho fixo com a mesma altura (2 linhas reservadas + reticências, ou todas 1 linha).
- D6. Rótulo: completo, depois curto escrito à mão, depois só ícone (aria + tooltip).
- D7. Campos não maiores que botões, salvo obrigação.
- D8. Ação dentro de aviso na cor do aviso; avisos acionáveis e dispensáveis.
- D9. Um padrão por gesto: ajuste na tela = inline com Aplicar/Cancelar; escolher algo fora = modal; destruir = confirmar + Desfazer.
- D10. Copy da casa, sem travessão, sem jargão técnico, sem "nota de rodapé do engenheiro", sem repetir o mesmo dado.
- D11. Tudo Nuxt UI canônico (primitiva > classe copiada).
- D12. Abrir as próprias capturas e caçar desalinhamento, borda indevida, altura desigual, corte, aperto.

## 4. Como acompanhar a esteira

- `make inflight`: worktrees sujas, branches sem PR, PRs fora da fila, vermelhos.
- `gh pr list --state open` e a fila:
  `gh api graphql -f query='{repository(owner:"nelsonboulangerie",name:"django-shopman"){mergeQueue(branch:"main"){entries(first:50){nodes{position state pullRequest{number}}}}}}'`
- Um PR pode sair da fila em silêncio (conflito ou check do `merge_group`):
  `isInMergeQueue` no GraphQL diz a verdade; `gh pr view <N> --json mergeable` também.
- Dê ao agente dono de um PR vermelho uns 15 minutos; se ele já encerrou, lance um agente
  novo para consertar sem tocar na worktree do original (merge de `origin/main`, nunca
  rebase de branch publicado, push sem force).
- O mapa `docs/reference/cenarios-de-pedido.md` é editado por quase todo PR de
  cenário: o PR que só atualiza o mapa entra por último.

### Armadilhas medidas em 14/10/2026

- **Teste que depende da hora.** Constante de data calculada no import (`TOMORROW =
  date.today()+1`) quebra quando a coleta é antes da meia-noite e o teste depois.
  Use função com `timezone.localdate()` (#1763).
- **pytest local 9.0.2 x CI 9.1.1.** Com xdist, o 9.0.2 não serializa `datetime` em
  `subTest`: passe `isoformat()` (#1771). Atualizar o `.venv` da raiz quando nenhum
  agente estiver rodando teste.
- **Contratos gerados.** Mudou projection: `SHOPMAN_UPDATE_CONTRACTS=1` (contratos do
  storefront) ou `manage.py export_production_schema` / `export_orders_schema`. Nunca
  resolver arquivo gerado à mão num conflito: regenerar.
- **Fronteira de leitura.** `presentation/` não importa `shop.services`
  (`test_import_boundaries`): passe por um service da própria superfície (#1767).
- **Escrita no alpha vivo por terminal é barrada** no modo automático. Escrita no vivo
  vai pelo Admin, no Chrome do dono, com a palavra dele.

## 5. Estado em 14/10/2026 (tarde)

- **Fila de merge vazia.** A auditoria dos cenários de pedido
  (`docs/reference/cenarios-de-pedido.md`) fechou: P0 6/6, P1 15/15, P2 17/17
  merged (#1716 a #1775). A §10 do mapa lista o que sobrou sem número.
- **Ligado no alpha desde 14/10:** loja online cobra ao pedir e estorna se recusar;
  Xepa só no balcão; cliente escolhe a janela de entrega na loja online; PDV com desconto
  em R$ por unidade e na linha, desconto automático por faixa de cliente (#1766), frete
  grátis pelo mesmo motor da loja online, cancelar corrida e "Entregador voltou";
  vitrine do WhatsApp espelha a da loja online; Pix vencido manda um aviso só; nota fora do
  prazo vira pendência "Nota de estorno para o contador" no Gestor; etapa final da
  corrida TaOn não atrasa mais.
- **Vocabulário:** o canal do cliente na internet se chama **loja online**. Não usar
  "site" como sinônimo em relatório ao dono.

## 6. Decisões do dono de 14/10/2026 (não reabrir)

- Sessão de 20 min (senha, PIN e 2FA do Admin; webhook e permissão do usuário de API
  da TaOn; certificado Efí de homologação): **adiada**, o Efí ainda não está pronto.
  Reoferecer quando ele disser que o certificado existe.
- Dia 1:
  - equipe: **cadastrar** os operadores com PIN. A conta do Pablo (dono) **fica**.
    Só sai operador de ensaio criado pelo seed, se houver.
  - Google Shopping e Meta: começam **desligados** e ligam assim que o catálogo
    estiver absolutamente pronto (fotos, preços, textos, GTIN). Preparar o
    critério de "pronto" e avisar o dono quando cumprir.
  - Caixas Presente: **entram** no Dia 1.
  - Demais itens: aceitos como recomendado (estoque por contagem; cupons desligados;
    custo de insumos depois; fichas como estão; Yooga mantém; ensaio no vivo antes).
    Catálogo (B5): reenviado em 14/10 (rec. 1: sessão de 2 h com a fila de divergências do
    catálogo consolidado e inventário na véspera; 2: abrir com o seed e corrigir aberto).
- Alterações no alpha que esperam: pedido mínimo de entrega está em 0 desde a prova
  da TaOn de 13/10 e **volta a R$ 25** (Admin, "Pedidos e entrega") quando a prova
  terminar.

## 7. Frentes novas pedidas pelo dono (14/10), ainda não iniciadas

### 7.1 Grupos de clientes com vantagens comerciais

**Pedido:** o gerente/dono cria grupos e escolhe as vantagens de cada um (desconto,
lista de preço diferenciada, frete grátis, coleções exclusivas, promoções específicas,
notificações exclusivas), edita com facilidade e associa clientes. Cliente
identificado recebe as vantagens; **vale sempre a melhor para o cliente, sem acumular
vantagens concorrentes** (dois descontos não somam). Primeiro membro: o cliente
Caetano Ricardi (telefone com a coordenação; criar pelo Admin do alpha na sessão com o
dono). Caso real: alunos da Aliança Francesa.

**O que já existe:** `guestman.PriceTier` (uma por cliente: tabela de preço via
`listing_ref`, `priority`, `metadata`, segmento de `Promotion.customer_segments`) e,
desde o #1766, o desconto automático por faixa no PDV (`services/promotions.py`,
`customer_group_promotion`; Admin em `shop/admin/price_tier.py`), com a regra "o maior
desconto vence e não soma" já valendo contra a Xepa.

**Recomendação da coordenação (taggit x grupos do Django):** nenhum dos dois.
- `taggit` (`Customer.tags`) são etiquetas livres, sem regra nem preço. Servem para
  filtrar e marcar, não para dar vantagem: ninguém garante que a etiqueta "aliança"
  escrita com outra grafia não perca o desconto.
- `django.contrib.auth.Group` é permissão de **equipe**. Pôr cliente ali mistura acesso
  ao sistema com preço, e um erro de associação vira falha de segurança.
- O certo é a entidade de domínio que já existe: evoluir a `PriceTier` do Guestman
  para o "grupo comercial", com as vantagens tipadas e editáveis, e aceitar que o
  cliente pertença a mais de um grupo (a melhor vantagem vence, por tipo, sem
  acumular). Isso mexe no Core: medir a necessidade, ler services e testes do Guestman
  e do motor de promoções antes de propor, e escrever o desenho num plano curto antes
  do código.
- A tela de gestão nasce num app Nuxt (ver 7.2), não só no Admin.

**Especificação do dono (14/10), primeira entrega desta frente:**
1. Verificar o que já existe de lista de preço por grupo de cliente; estender, não duplicar.
2. Preço do grupo = preço base × (1 + ajuste%), ajuste positivo ou negativo, com
   arredondamento configurável. Sempre calculado, nunca digitado: reajuste da base propaga.
3. Vínculo por grupo de cliente (Guestman). Grupos iniciais: **Equipe (−30%)** e
   **Aliança Francesa (−15%)**, configuráveis no Admin.
4. Vale no PDV e na loja online. Desconto registrado por tipo (equipe/parceiro) para o B.I.
5. Checkout e comprovante: com economia > 0, "Hoje você economizou R$ X por ser [grupo]";
   texto por grupo, editável no Admin.
6. Antes de implementar, relatório curto ao dono: o que existe, o que falta, proposta.

**Relatório do passo 6 (14/10, contra `origin/main` 9b7320580), ainda não levado ao dono:**
- Existe: desconto automático por faixa (#1766; `shop/services/promotions.py`
  `customer_group_promotion`, Admin `shop/admin/price_tier.py`), aplicado pelo
  `DiscountModifier` (`shop/modifiers.py`, maior desconto vence) e gravado por linha em
  `pricing.discount.items[]` (`type: "promotion"`, nome, original, desconto). Na NFC-e o
  desconto de linha sai embutido no preço do item (`adapters/fiscal_focusnfe.py`).
- **Defeito latente:** a cascata "faixa do cliente → listing" de
  `shop/handlers/pricing.py` depende de `ctx["customer"]`, que nenhum chamador preenche.
  Hoje `PriceTier.listing_ref` não muda preço nenhum. Consertar ou remover, com teste.
- **Duas regras para a mesma Equipe:** `EmployeeRule` (`shop/rules/pricing.py`, faixa
  `staff`, 20%, só retirada) e o desconto por faixa do #1766 disputariam o mesmo cliente.
  A proposta é aposentar a `EmployeeRule` virando promoção `grupo-staff`.
- Falta: arredondamento; tipo do desconto (`discount_kind`) no registro da linha e a
  leitura no B.I. (hoje o B.I. não lê desconto de pedido); mensagem de economia por grupo
  no checkout e no comprovante (hoje só a de fidelidade existe).
- **Proposta recomendada:** estender o desconto da faixa no motor de modifiers (sem Core:
  `PriceTier.metadata` ganha `discount_kind`, `rounding`, `savings_message`, registrados
  antes em `docs/reference/data-schemas.md`). Lista derivada no Offerman
  (`Listing.base_listing` + ajuste + arredondamento) só se o dono quiser sobrepreço por
  grupo, porque mexe no Core e esconde o desconto do B.I. e da mensagem de economia.
- **Perguntas ao dono (levar em 1/2):** sobrepreço por grupo agora? (rec. 1: não, só
  desconto) · Equipe −30% também na entrega pela loja online? (rec. 1: só retirada, como
  hoje, para não abrir preço de equipe a terceiros) · arredondamento (rec. 1: preço final
  para baixo, em múltiplos de R$ 0,10).

### 7.2 Cadastro completo nos apps Nuxt ("CRUD turbo")

**Pedido:** gerente e dono criam e editam, com total autonomia e pelos apps Nuxt, tudo
o que é pertinente a produtos, receitas, insumos, clientes, fornecedores e grupos. Não
um cadastro espartano: à altura da UX da suíte.

**O que já existe (medido em 14/10):**
- Produção: receitas com lista, criar, editar e comparar (`production-nuxt/pages/recipes`).
- Compras: insumos e fornecedores com lista e ficha, custos, contagem
  (`purchase-nuxt/pages/base`).
- Gestor: catálogo em grade (preço, publicação por canal, "Editar detalhes" do produto
  num painel), clientes com lista, ficha e fusão (`orders-nuxt/pages/catalog.vue`,
  `customers/`).
- Falta, a confirmar com inventário: **criar produto** do zero no Nuxt (hoje o
  painel edita), grupos de clientes (só Admin), e o que mais só existe no Admin.

**Primeiro passo:** um agente faz o inventário campo a campo (o que o Admin edita
e o Nuxt não) para produto, receita, insumo, cliente, fornecedor e grupo, e propõe
as ondas. A proposta vai ao dono em 1/2, com capturas, antes do código.

## 8. Pendências que dependem do dono

- Sessão de 20 min (seção 6), quando o certificado Efí de homologação existir.
- Medir o fechamento da venda no PDV do alpha (meta < 1,5 s) na próxima venda dele.
- Hardware do balcão (kit enxuto de R$ 3.981,98): adiado pelo dono em 14/10.
- Listas de preço por grupo: as 3 perguntas do relatório da §7.1.
- Leva ao contador (texto a montar e entregar ao dono, que envia):
  1. desconto da linha embutido no preço: como sai no `vDesc` do item da NFC-e;
  2. nota de estorno fora do prazo de cancelar: quem emite e como (pergunta inteira no
     corpo do #1774), prazo, devolução parcial;
  3. prazo de cancelamento da NFC-e no Paraná: 30 min (código, RICMS/PR art. 35) ou
     24 h (`docs/reference/fiscal-parametrizacao-nfce.md` §5).
- Modelos de WhatsApp a submeter depois da revisão dele: rastreio do entregador,
  reembolso processado, pedido devolvido.

## 9. Na janela da virada (não antes)

- Aplicar o #1713 (readiness pelo banco e access log) conforme
  `docs/runbooks/web-operator-resiliencia.md`.
- P0-3: acrescentar `shopman.shop.fiscal_resolvers.intermediated_sale` em
  `SHOPMAN_FISCAL_EMISSION_RESOLVER` (já no `scripts/golive_spec_delta.py`).
- Roteiro completo: `docs/runbooks/go-live-cutover.md` e
  `docs/plans/GO-LIVE-READINESS-PLAN.md`; `make production-readiness target=1` diz o
  que falta.
