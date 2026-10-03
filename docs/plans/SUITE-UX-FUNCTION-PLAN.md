# SUITE-UX-FUNCTION-PLAN: forma segue função

**Proposta de 03/10/2026 (v4).** Continua a [SUITE-UX-V2-PLAN](SUITE-UX-V2-PLAN.md), cuja v3 o
dono aprovou no geral como **ponto de partida**. A v3 está gravada na branch
`snapshot/suite-ux-proposta-v3` (plano, prévias e as fontes que as regeneram em
[`suite-ux-v2/fontes/`](suite-ux-v2/fontes/)).

O pedido desta rodada, nas palavras do dono:

> *"Refaça uma engenharia reversa profunda quanto às necessidades de cada funcionalidade de cada
> app… Quais são os padrões comuns de necessidades das funcionalidades? Nesse primeiro momento,
> não olhe para o rosto. Primeiro, função. Forma segue função. Minimalismo na sua essência mais
> profunda e cruel, não como preguiça de resolver a complexidade. Encontre os padrões… e trace um
> novo plano de traduzir isso em layout, controles, ações primárias/secundárias, navegação
> primária/secundária, busca/filtro/exibição/paginação, acesso à informação, acesso à principal
> ação, semântica visual, fronteira entre os apps. TUDO deve ser ridiculamente fácil para o
> operador: Omotenashi profundo e afiado."*

Por isso, **este documento não desenha telas.** Ele diz o que cada tela precisa ser. O rosto vem
na próxima rodada, a partir daqui.

---

## 0. Método

Sete análises paralelas, uma por app, todas no mesmo formato ([`suite-ux-v2/funcoes/FORMAT.md`](suite-ux-v2/funcoes/FORMAT.md)).
Cada funcionalidade virou uma **ficha de trabalho**: quem, onde, gatilho, frequência, urgência,
cliente esperando, objetivo real, informação mínima para decidir, entrada, efeito, reversível,
custo do erro, exceções, caminho hoje e caminho mínimo, fronteira. Todas leram front **e** back
(actions, projections, services, modelos), para descrever o trabalho e não o nome da tela.

| app | trabalhos | ficha |
|---|---|---|
| PDV | 59 | [`funcoes/pdv.md`](suite-ux-v2/funcoes/pdv.md) |
| Gestor de pedidos | 59 | [`funcoes/gestor.md`](suite-ux-v2/funcoes/gestor.md) |
| Cozinha + Shopman Apps + chrome comum | 46 | [`funcoes/kds-hub.md`](suite-ux-v2/funcoes/kds-hub.md) |
| Produção | 45 | [`funcoes/producao.md`](suite-ux-v2/funcoes/producao.md) |
| Marketing | 38 | [`funcoes/marketing.md`](suite-ux-v2/funcoes/marketing.md) |
| Compras | 29 | [`funcoes/compras.md`](suite-ux-v2/funcoes/compras.md) |
| B.I. | 26 | [`funcoes/bi.md`](suite-ux-v2/funcoes/bi.md) |
| **total** | **302** | |

Cada ficha tem também a lista de **todas** as telas e estados do app, com o dispositivo que faz
sentido para cada uma. É a base da matriz de cobertura do §10: nenhuma tela fica sem destino.

---

## 1. O que 302 trabalhos dizem, em uma frase

**O operador faz trabalho que o sistema já sabe fazer, em formas diferentes para o mesmo
trabalho, sem a informação da decisão no lugar da decisão.**

As três partes dessa frase aparecem nos sete apps, sem exceção:

- **O sistema sabe e o humano faz.** "Pronto" chega da Cozinha e o Gestor ainda pede o toque;
  "esgotado" é conhecido e a pausa é manual, canal por canal; enviar à cozinha é um toque por
  comanda; o fornecedor já veio no CNPJ da NF e a tela pré-seleciona "o primeiro da lista";
  reconciliar resultado incerto (Marketing) e reconciliar relatório (Produção) são consultas sem
  efeito que pedem um botão; a quantidade produzida já está escrita e abre um diálogo para
  confirmá-la.
- **O mesmo trabalho com formas diferentes.** "Receber dinheiro e dar baixa" tem três telas no PDV
  (pagar, retirada de encomenda, conta na casa); "contar às cegas" tem duas (fechar caixa, fechar
  o dia); "partir do esperado e registrar o real" tem três na Produção (planejar, produzir, fechar
  fornada) e mais uma no Compras (conferir NF); "concluir o preparo" tem cinco portas; despacho,
  recusa e acerto existem em duas versões no Gestor; custo de insumo tem quatro portas no
  Compras; "anúncios esperando o meu sim" tem cinco portas no Marketing e nenhuma tela própria.
- **A informação longe da decisão.** Aceitar pedido sem ver a disponibilidade dos itens;
  reprocessar NFC-e sem o motivo da SEFAZ; falta de insumo que aparece depois do planejamento;
  horário das encomendas que não aparece na Produção; bloqueio de pagamento que o cozinheiro só
  descobre num toast 5 s depois de finalizar; "para quem vai o pedido" numa aba diferente do
  botão Enviar; e o B.I. inteiro, que calcula a projeção, o troco e a sobra por produto para
  pessoas que não abrem o B.I.

---

## 2. Sete leis (o minimalismo que não é preguiça)

Cada lei sai de evidência repetida nos apps. É o filtro por onde passa toda tela da próxima rodada.

### L1. O sistema faz o que sabe; o operador declara só o que só ele vê
O gesto humano existe para registrar um fato do mundo que o sistema não tem como saber ("saiu",
"foi retirado", "produzi 26", "contei R$ 412", "esta caixa veio amassada") ou para uma decisão de
autoridade. Todo o resto é automático e aparece como **fato na linha do tempo, com desfazer**.
*Consequência de forma:* o botão principal de cada item é o fato que só o humano conhece; quando
não há tal fato, não há botão.

### L2. Um trabalho, uma forma, muitas portas
O mesmo trabalho tem a mesma forma em qualquer app, qualquer tela, qualquer dispositivo. A porta
pode ser a fila, o detalhe, a busca, o aviso ou outro app; o que abre é sempre o mesmo.
*Consequência:* a suíte inteira cabe em **7 formas de tela** e **6 gestos transversais** (§3 e §4).

### L3. A informação da decisão está no lugar da decisão, antes do gesto
O que pode impedir ou mudar a decisão aparece **no item, antes do toque**: bloqueio com motivo,
falta, prazo, a conta por trás da sugestão. Nunca um toast depois; nunca em outra aba.

### L4. Caminho feliz sem atrito; atrito proporcional ao irreversível
O caso comum custa 0 ou 1 gesto. Atrito existe só onde há **exceção** (motivo, de uma lista curta)
ou **irreversibilidade** (desfazer para o reversível; selo para o irreversível; assinatura para
exceção de dinheiro ou de autoridade). Conferência é **por exceção**: o que bate entra sozinho;
mexe-se no que não bate.

### L5. Atenção é o recurso escasso
O que pede alguém vira **item numa fila com dono**, não toast nem sino solto. A densidade de uma
fila é fixada pela atenção (4 a 6 itens em foco numa estação), não pelos pixels; o excedente vira
número ("+7 na fila") e agregado ("A fazer"). Tela maior aumenta a distância de leitura, não a
contagem.

### L6. Papel e postura antes de app
Dentro de quase todo app há duas naturezas de trabalho que não podem ter o mesmo peso: **operar**
(segundos ou minutos, de pé, no posto, dispositivo do posto) e **ajustar** (dias, sentado, no
escritório). O Gestor tem quatro naturezas; o Compras tem três papéis com dispositivos opostos; o
Marketing faz 10× por dia uma coisa e 1× por mês outras três, todas com o mesmo peso na barra.
*Consequência:* cada app abre na **fila do papel** de quem entrou; ajustar é um andar separado.

### L7. O estado é da casa, não do dispositivo
Rascunho de recebimento, contagem, timer de forno, checklist de separação, "visto" de alerta e som
da estação moram no servidor. Hoje vivem no navegador: recarregar perde a conferência de uma nota
de 20 itens, e num fournil com três tablets só toca o timer do tablet que o armou.

---

## 3. Os padrões de necessidade

Os rótulos provisórios das sete análises (VIGIAR, TRIAR, AVANÇAR, REGISTRAR-QUANTIDADE, COMPOR,
CONFERIR, CONFIGURAR, PLANEJAR, LOCALIZAR, ENTENDER, APROVAR, CORRIGIR, AUTORIZAR, EMITIR, AVISAR,
mais os propostos por elas: SELAR, INTERRUPTOR, ACUSAR-RECEBIMENTO, TRAVA-FÍSICA, ASSUMIR,
INSTRUIR, ANOTAR, DELEGAR, SEPARAR, SEGUIR-INSTRUÇÃO, REGISTRAR-FATO, AVALIAR, LER-CÓDIGO,
APONTAR, EXPLICAR-NO-LUGAR) colapsam em **sete formas de tela** e **seis gestos transversais**.

### 3.1 Sete formas de tela

| forma | o trabalho que serve | onde está hoje (exemplos) |
|---|---|---|
| **FILA** | VIGIAR + TRIAR + AVANÇAR + APROVAR + ASSUMIR | fila de pedidos (Gestor), estação e Saída (Cozinha), comandas e encomendas do dia (PDV), expedição e timers (Produção), reposição e "a caminho" (Compras), anúncios esperando o meu sim (Marketing), "Precisa de você" (Shopman Apps) |
| **CONFERÊNCIA** | REGISTRAR-QUANTIDADE + CONFERIR + AVALIAR + SEPARAR | produzir, fechar fornada com QC, corrigir QC, planejar (Produção); conferir NF, contagem (Compras); abrir e fechar caixa, fechar o dia, entregador voltou, maquininha voltou, acerto (PDV/Gestor); separação de insumos e de encomendas |
| **COMPOSIÇÃO** | COMPOR + SELAR | venda (PDV), entrada sem NF e pedido ao fornecedor (Compras), campanha e anúncio (Marketing), receita (Produção), oferta e cupom (Marketing) |
| **CADASTRO** | CONFIGURAR (cadastral) + CORRIGIR cadastro | catálogo e painel do produto, clientes e unificação, vínculos de canal (Gestor); insumos, fornecedores, custos (Compras); receitas (leitura e versões); modelos e plataformas (Marketing) |
| **LEITURA** | ENTENDER | B.I. (8 seções), relatórios da Produção, X/Z do PDV, histórico do Marketing |
| **FOCO** | uma tarefa só, com a mão ocupada ou o cliente na frente | pagamento (PDV), finalizar lote (Produção), leitor de NF e de código (Compras/PDV), selo de anúncio (Marketing), contagem cega |
| **MONITOR** | VIGIAR à distância, sem gesto | Painel de retirada (Cozinha), Letreiro (Produção), Tela do cliente (PDV), quadro de estação em TV |

### 3.2 Seis gestos transversais (valem dentro de qualquer forma)

| gesto | o que é | onde se repete hoje |
|---|---|---|
| **LOCALIZAR** | uma busca, uma tecla, alcance (esta tela · app · suíte), leitura de código pela câmera ou leitor | "Cliente veio buscar?", busca de produto F3, busca de pedido, busca de insumo, cliente no PDV, campanha, código da Via Cozinha |
| **EXCEÇÃO ASSINADA** | ATO + MOTIVO (lista curta) + ASSINATURA (PIN/crachá; zero passos se o gerente já está logado) | sangria, troco servido, devolução, estorno, desconto acima do limite, cancelar venda, nota avulsa, edição mais barata, gaveta emperrada, cancelar pedido pago, desligar canal, estornar produção |
| **INTERRUPTOR** | ligar/desligar algo que age sozinho: 1 toque, reversível, efeito imediato, no dispositivo onde está a urgência; **automático quando o sistema sabe** | pausar produto por canal, desligar canal, campanha ligada, congelar efeitos externos, aviso transacional ativo, som da estação |
| **SELO / DESFAZER** | confirmação com atrito proporcional: desfazer por N segundos se reversível; selo (frase, senha, TOTP) se irreversível para fora da casa | finalizar ticket (desfazer 5 s, reabrir 30 min); entregar e despachar (hoje sem nada); disparar campanha e publicar anúncio (selo); remover item (desfazer) |
| **ANOTAR** | motivo ou ocorrência a partir de uma lista curta da casa, com "Outro" em texto | recusa, cancelamento, perda no QC, ocorrência no recebimento, divergência da contagem, nota da cozinha (tags) |
| **AVISO** | o que pede alguém vira item na fila do dono, com push quando ele não está olhando, e some quando resolvido | alertas do Gestor, sino da Produção, sino do Marketing, alarmes do B.I. (hoje só no Admin), "Visto", som |

**EMITIR** (vias, etiquetas, NFC-e) deixa de ser trabalho: é efeito colateral do ato. Só a falha
vira item (AVISO) no lugar de quem resolve. **TRAVA-FÍSICA** (gaveta fechada, papel bipado) e
**DELEGAR** (corrida externa) são estados de um item de FILA, não telas.

---

## 4. As formas, por função

Para cada forma: propósito, anatomia funcional (zonas, não cores), ação primária, secundárias,
navegação, busca/filtro/exibição/paginação, acesso à informação e o que muda por dispositivo.

### 4.1 FILA — "o que pede alguém agora"

- **Propósito:** manter consciência de um fluxo que muda sozinho e declarar o fato que só o humano vê.
- **Zonas:** (1) recorte da fila (estado ou prazo) com contagens; (2) itens, **ordenados por
  urgência** (prazo contra meta), o próximo em destaque; (3) agregado do excedente ("+N", "A fazer").
- **Item:** identificador chamável (código), tempo contra a meta (um número + tom), o essencial
  do conteúdo (itens, valor, quem), o bloqueio **com motivo** quando existir, e **um** gesto: o fato
  humano do momento. Sem ícones decorativos, sem campos que não mudam a decisão.
- **Ação primária:** o fato humano (Aceitar · Iniciar · Pronto · Entregar · Saiu · Finalizar ·
  Aprovar). Uma por item. Se o sistema sabe o fato, não há botão: o item avança sozinho e mostra
  "o sistema fez · desfazer".
- **Secundárias:** assumir, anotar, imprimir, abrir detalhe: no item (desktop: menu; toque:
  pressão longa; celular: deslizar).
- **Navegação:** a fila é a **porta de entrada** do papel. Detalhe sobe em painel (desktop/tablet
  deitado) ou tela cheia (celular), com volta mantendo a posição.
- **Busca:** LOCALIZAR filtra a fila enquanto se digita. **Filtro:** só recortes que mudam o
  trabalho (canal, entrega/retirada, atrasados). **Exibição:** densidade derivada do posto, não
  escolhida. **Paginação:** nunca; o excedente é número.
- **Tempo real:** push (SSE) com o fetch canônico como verdade; "ao vivo" discreto; desatualizado explícito.
- **Dispositivo:** parede/tablet fixo (4–6 em foco, leitura a 1–2 m); celular (1 em foco + 6–8 linhas
  compactas, push e vibração porque a tela apaga); desktop (fila densa em tabela, seleção em lote).

### 4.2 CONFERÊNCIA — "o que aconteceu de verdade"

- **Propósito:** registrar o real partindo do esperado e resolver só a diferença.
- **Zonas:** (1) o esperado, já preenchido (plano, nota, saldo, sugestão); (2) o real, igual ao
  esperado por padrão; (3) a diferença, com motivo; (4) progresso ("faltam 2") e um selo.
- **Ação primária:** **Confirmar** o conjunto (uma vez), não linha a linha. O que bate entra sozinho.
- **Secundárias:** marcar exceção numa linha (número + motivo de lista curta); ver a conta da sugestão.
- **Modo cego** (caixa, fechamento do dia, contagem de estoque): o esperado fica escondido por
  desenho, para não induzir; a diferença só aparece depois do número. É a única variante sem
  pré-preenchimento, e é consciente.
- **Selo que aponta:** o botão de confirmar nunca fica morto; tocado com pendência, leva ao
  primeiro campo que falta (o padrão APONTAR que o Compras já tem).
- **Entrada numérica:** teclado físico no desktop; teclado numérico da tela no toque, grande, na
  zona do polegar; nunca os dois ao mesmo tempo.
- **Dispositivo:** tablet e celular são a casa natural (bancada, doca, câmara fria, vitrine);
  desktop só para conferências de escritório.

### 4.3 COMPOSIÇÃO — "montar uma transação"

- **Propósito:** juntar partes, fatos e um selo numa transação (venda, entrada, campanha, receita, pedido).
- **Zonas:** (1) **fonte** do que se adiciona (catálogo, nota, modelos, insumos); (2) **a conta**:
  a lista do que já foi composto, que é o que se lê de volta e se confere (zona dominante); (3)
  **fatos** da transação (quem, quando, como recebe) numa faixa que vale do começo ao fim; (4)
  **total + um selo**.
- **Ação primária:** o selo (Pagamento · Confirmar entrada · Publicar · Salvar e publicar · Enviar
  pedido), sempre visível, sempre no mesmo lugar, com o total dentro dele.
- **Secundárias:** editar uma linha **sob demanda** (tocar a linha abre o instrumento; não há
  console permanente); ações em várias linhas só em modo seleção.
- **Proibido:** instrumento de edição fixo roubando a zona da conta; duas ferramentas para a mesma
  pergunta (o passo +/− da linha e o teclado numérico, ambos para quantidade).
- **Dispositivo:** desktop com teclado e leitor (digitação e leitura de código como caminho
  principal); tablet com a fonte em grade grande e a conta como painel (ou folha de baixo em pé).

### 4.4 CADASTRO — "regras que valem por muito tempo"

- **Propósito:** ajustar o que dura (produto, insumo, fornecedor, custo, cliente, modelo, canal).
- **Zonas:** lista densa (tabela) com filtros visíveis + painel do item ao lado; edição em linha só
  para o campo mais frequente da lista (preço, mínimo, chave de canal).
- **Ação primária:** salvar o que mudou ("3 campos alterados · Salvar"); nunca salvar campo a campo
  escondido.
- **Lote:** seleção + barra de lote + **revisão antes de confirmar** quando mexe em preço ou publicação.
- **Busca/filtro:** busca + filtros como chips removíveis + contagem do recorte. **Paginação:**
  rolagem contínua com contagem total; o recorte vai para a URL.
- **Dispositivo:** desktop. Exceção: o **interruptor** que mora num cadastro (pausar produto,
  desligar canal) também aparece no posto onde está a urgência (L6).

### 4.5 LEITURA — "o número que muda uma decisão"

- **Propósito:** responder uma pergunta do dono com um número, a comparação e o porquê.
- **Regra-mãe (EXPLICAR-NO-LUGAR):** se o número serve a uma decisão tomada em outro app, ele
  **vai até lá** (ao lado da sugestão do plano, no abrir caixa, na audiência do Marketing, no push).
  A LEITURA fica só com o que é de fato estudo: semanal, mensal, estratégico.
- **Zonas:** pergunta como título · número · comparação com período anterior · "por quê" (o que
  compõe) · **aprofundar** até o registro (pedido, turno, lote, produto, cliente).
- **Filtro:** período (sempre na URL) + no máximo dois recortes. **Exibição:** a forma que a pergunta
  pede (série, ranking, tabela de dois eixos), nunca três leituras da mesma coisa na mesma página.
- **Dispositivo:** desktop para estudo; celular para a olhada (um número e uma frase) e para o alerta.

### 4.6 FOCO — "uma tarefa só, agora"

- **Propósito:** uma tarefa com a mão ocupada, o cliente na frente ou o erro caro.
- **Regras:** o resto da suíte some (rail, seções); um instrumento grande (teclado numérico,
  câmera, lista de formas de pagamento); um selo na zona do polegar; saída com guarda quando há dado.
- **Etapa na URL** para sobreviver a recarga; vibração ao concluir no celular.

### 4.7 MONITOR — "olhar de longe"

- **Propósito:** ser lido a 3–6 m, sem gesto.
- **Regras:** só o que se lê de longe (código, coluna, número); atualiza sozinho; **saída declarada**
  (toque longo no canto ou Esc + PIN) quando aberto numa estação; nada de ação na tela.

---

## 5. Ação: primária, secundária e o que deixa de ser ação

| nível | o que é | onde mora | exemplo |
|---|---|---|---|
| **automática** | o sistema sabe e faz | linha do tempo do item, com desfazer | avançar para "pronto" quando a Cozinha conclui; pausar produto esgotado; enviar à cozinha ao salvar; reconciliar resultado incerto |
| **primária** | o fato humano do momento, um por item ou tela | botão largo do item; selo da composição | Entregar · Finalizar 26 un. · Pagamento R$ 41,00 · Confirmar entrada |
| **frequente** | alternativa comum | visível ao lado, peso menor | Recusar · Transferir · Imprimir via |
| **rara** | existe, pouco usada | menu do item/tela, com a mesma tecla de antes | exportar, reimprimir, histórico, comparar versões |
| **exceção** | desvio com autoridade | EXCEÇÃO ASSINADA | cancelar pago, sangria, estorno, desconto acima do limite |
| **irreversível para fora** | sai da casa e não volta | SELO | disparar campanha, publicar anúncio, emitir nota avulsa |

A regra que corta: **se um botão não é o fato humano do momento nem uma alternativa frequente,
ele não está na superfície.**

---

## 6. Navegação: primária e secundária

- **Primária = o papel.** Cada operador entra na **fila do seu papel** naquele app (o padeiro na
  Expedição, o recebedor na doca, o atendente nas comandas, o dono nas decisões). A seção é
  secundária; a fila é a casa.
- **Dois andares por app:** **Operação** (padrão, no dispositivo do posto) e **Ajustes** (cadastro,
  configuração, relatórios; escritório). Ajustes não divide barra com Operação: entra por um item
  só ("Ajustes"), com suas próprias seções.
- **Item endereçável, volta com contexto, saída de MONITOR declarada, bilhete de volta entre apps**:
  o modelo de cinco níveis da v3 (SUITE-UX-V2-PLAN §4) continua valendo, agora com a fila do
  papel como nível 1.
- **Shopman Apps vira a fila das filas:** "Precisa de você" é a soma das filas de todos os papéis do
  operador, com o item exato; para quem tem um app só, ele nem aparece (abre direto na fila).

---

## 7. Busca, filtro, exibição, paginação

| forma | busca | filtro | exibição | paginação |
|---|---|---|---|---|
| FILA | filtra ao digitar; câmera/leitor acha o item | recortes que mudam o trabalho, com contagem | derivada do posto (não escolhida) | nunca; excedente vira número |
| CONFERÊNCIA | acha a linha (nome, código, EAN) | "só pendências" | lista; uma linha aberta por vez | nunca |
| COMPOSIÇÃO | é o principal caminho no desktop (digitar, ler código) | coleções como atalho na fonte | grade grande no toque; lista no teclado | nunca na conta; fonte rola |
| CADASTRO | busca + chips removíveis | qualquer dimensão, em chips, na URL | tabela com colunas escolhíveis | rolagem contínua + total |
| LEITURA | acha a pergunta | período + até 2 recortes | a que a pergunta pede | não se aplica |
| suíte | **uma busca, uma tecla** (`/`, Ctrl K), alcance esta tela · app · suíte, câmera no toque | — | resultados por tipo, com ações | — |

---

## 8. Semântica: o que a forma precisa dizer (sem escolher cor ainda)

Seis significados, e só seis, em toda a suíte:

1. **Precisa de você** — o item espera um fato ou decisão humana.
2. **Em andamento** — alguém (ou o sistema) está fazendo.
3. **Feito** — concluído; some da fila (vai para o histórico).
4. **Bloqueado, com motivo** — não dá para avançar; o motivo e quem destrava estão no item.
5. **O sistema fez** — automático, com desfazer.
6. **Atenção ao tempo** — a meta está estourando (um número + intensidade, nunca dois indicadores).

E duas marcas de risco: **irreversível** (o selo) e **dinheiro/autoridade** (a assinatura).
O resto do que hoje tem cor própria (canal, coleção, app) é identificação, não estado.

---

## 9. A fronteira entre os apps

O código continua em oito apps (deploy, permissões, ADR-030). A **experiência** se organiza por
**posto e papel**, e alguns trabalhos mudam de casa porque hoje estão no app errado:

| trabalho | hoje | proposta | por quê |
|---|---|---|---|
| Entregar encomenda / pedido no balcão | PDV (encomendas) **e** Gestor (receber na retirada) | um trabalho só, uma forma (FILA + RECEBER), aberto pelos dois | é o mesmo fato com duas telas |
| Saída do pedido (pronto → saiu/retirou) | Cozinha (Saída) **e** Gestor (avançar, despachar) | posto **Passe**: uma fila de saída, aberta pela Cozinha e pelo Gestor | mesma `advance_order`, dois desenhos |
| Pausar produto / desligar canal | Gestor, no Catálogo e em Canais (escritório) | **automático** quando esgota; interruptor também no posto do passe e no celular do gerente | urgência de minutos no lugar de dias |
| Avisos transacionais (pedido, pagamento, fila, fidelidade) | Marketing › Plataformas | Gestor › Canais (Ajustes) | é comunicação da loja, não campanha; foi parar no Marketing pelo seletor do ManyChat |
| Contagem de estoque | aba escondida da Base no Compras | trabalho próprio de **Estoque** (gerente, tablet), CONFERÊNCIA cega | é outro papel, outro dispositivo |
| Fim do dia | fechar caixa, fechar o dia e contar a vitrine em telas separadas | um **corredor** só, em sequência, no tablet | mesmo dono, mesmo momento, mesma forma (cega) |
| Projeção, troco, sobra por produto, em risco | B.I. (aba que o decisor não abre) | ao lado da sugestão do plano (Produção), no abrir caixa (PDV), como audiência (Marketing), push | EXPLICAR-NO-LUGAR |
| Alarmes do B.I. | só no painel do Admin | AVISO no celular do dono e na fila do papel certo | ninguém os vê |
| Comprar × Receber | uma navegação para dois papéis opostos | dois andares: Receber (doca, celular, Operação) e Comprar (escritório, desktop, Ajustes) | L6 |
| Prévia de data futura | no cabeçalho da estação da Cozinha | Produção/Encomendas (planejar) | quem executa o hoje não planeja |
| Decisões do Marketing | 5 portas, nenhuma tela | uma FILA de decisões ordenada por prazo, que é ao mesmo tempo Hoje, sino e push | é o trabalho central do app |

Postos que saem disso (cada um abre direto na sua fila):
**Balcão** (PDV, desktop com periféricos) · **Passe** (saída do pedido) · **Estação** (Cozinha) ·
**Forno** (Produção chão) · **Doca** (Compras receber) · **Estoque** (contagem) · **Fim do dia** ·
**Escritório** (catálogo, canais, compras, receitas, campanhas, B.I.) · **Dono em movimento**
(celular: decisões, alertas, olhada).

---

## 10. Dispositivo por trabalho, e as três notas do dono

A cobertura completa (cada tela e estado de cada app, com forma, dispositivo e destino) está em
[`suite-ux-v2/funcoes/cobertura.md`](suite-ux-v2/funcoes/cobertura.md). Abaixo, as três notas
que o dono fez sobre a v3, respondidas pela função.

### 10.1 PDV: o pé da comanda ficou espremido na v3

A análise mediu a comanda de hoje (`PosCartPanel.vue`, coluna fixa de 360 px): cerca de **400 px
fixos** que nunca rolam (cabeçalho ≈ 53, console do teclado numérico ≈ 204, rodapé ≈ 140). O que o
operador faz ali, por frequência: ler de volta o pedido e o total; corrigir a quantidade da última
linha; remover; ver se foi à cozinha; anotar; descontar; selecionar várias. Desconto e observação
acontecem 0 a 20 vezes por dia contra 100 a 400 vendas.

A v3 ganhou altura na lista apertando o rodapé (dois andares de botões em 112 px). A função diz
outra coisa: **a comanda precisa de lista + total + um selo (Pagamento), e só.**
- O instrumento de edição aparece **ao tocar a linha** (sobre a parte de baixo da lista), não fixo.
- "Enviar à cozinha" deixa de ser botão: o canal envia ao salvar ou ao pagar o que tem preparo (L1),
  com o fato na linha ("na cozinha 21:52").
- "Transferir" vai para o modo seleção (onde já se escolhem as linhas).
- O rodapé fica com **uma faixa só, generosa**: total e Pagamento juntos, o maior alvo da tela.
- No desktop com teclado, não existe teclado numérico na tela, nem recolhido: os dígitos editam a
  linha ativa (como hoje).

### 10.2 PDV no tablet: era igual ao de hoje. Agora é consciente

Não foi consciente na v3. A função mostra que o PDV de venda é **desktop por causa dos periféricos**
(agente local, gaveta e sensor, impressora de bobina, leitor HID, segundo monitor), não por causa da
tela. No tablet: sem gaveta pelo sistema, sem bobina (cai no `window.print`), sem tela do cliente,
leitor só Bluetooth.

Logo, o tablet **não é o balcão em outro tamanho**: é um **segundo posto sem dinheiro físico**, com
trabalho próprio:
- **fila longa e comanda de mesa** (lançar e mandar para a cozinha; pagar só eletrônico, PIX e
  maquininha; dinheiro vai para o caixa);
- **encomendas e retirada** (a lista do dia, ler o QR, entregar);
- **fim do dia** (contar a vitrine andando).
Em pé é o padrão (na mão), com a fonte em grade grande ocupando a tela e a comanda como folha de
baixo (contagem + total + Pagamento sempre visíveis); o teclado numérico só ao tocar uma linha.

### 10.3 Cozinha no tablet e no celular, e quantos cards cabem

Não houve prévia de tablet de verdade nem de celular, e o celular foi descartado por julgamento.
A análise encontrou quem usa e o quê:

| dispositivo | quem | trabalho | densidade (fixada pela atenção) |
|---|---|---|---|
| tablet fixo na bancada/parede | cozinheiro de estação | preparar (iniciar, finalizar, desfazer) | **4 a 6 tickets** em foco + "+N" + faixa "A fazer" |
| tablet fixo no passe | expedidor | Saída: entregar, despachar, conferir volumes | **3 a 4 prontos** grandes + **5 a 8 linhas** de "em preparo" |
| tablet na mão | chefe de cozinha / gerente | o que está atrasado em qualquer estação; corrigir | **6 a 10 linhas** (lista, não grade); visão "todas as estações", que hoje não existe |
| celular | atendente que leva o pedido | prontos para sair: entregar | **1 expandido + 6 a 8 linhas** |
| celular | cozinheiro de estação pequena (barista, lanches) | a própria estação | **1 em foco + 3 a 5 linhas**; exige push e vibração (o KDS não tem push hoje e a tela do celular apaga) |
| TV | público | Painel de retirada | 12 a 24 códigos |

Sobre "caberia mais card no celular": **cabem mais pedidos, como linhas compactas** (código, tempo,
estado, um gesto), não mais cards completos. O card completo só para o pedido em foco; o resto é
lista. A v3 mostrava dois cards inteiros e nada mais; a função pede um em foco e a fila visível.

---

## 11. Achados de função que não são de tela

A engenharia reversa achou defeitos e lacunas que nenhum redesenho resolve sozinho. Os dois
primeiros são defeitos confirmados no código e já viraram tarefas separadas.

| achado | app | natureza |
|---|---|---|
| Um insumo só pode ser pedido **uma vez**: `request_status = "sent"` nunca é limpo, nem pelo recebimento (`services/purchase.py:880`, `confirm_receipt` em `:173`); a tela trava o botão | Compras | **defeito** (tarefa aberta) |
| Confirmar produção com falta para as encomendas: o servidor recusa (`order_shortage`) e o diálogo fica parado sem mensagem (`ProductionStageGrid.vue::confirmStart`) | Produção | **defeito** (tarefa aberta) |
| Histórico de recebimentos é projetado (`receiptHistory`) e nenhuma tela mostra | Compras | lacuna de tela |
| Aprovar pedido de compra tem endpoint (`/approve/`) e nenhum botão | Compras | lacuna |
| Pedido de compra é por insumo, não por fornecedor; recebimento não abate pedido; não há "a caminho" | Compras | regra de negócio |
| Conferência exige ok linha a linha mesmo com a nota batendo | Compras | regra (L4) |
| Rascunhos de recebimento e contagem, timers e checklist só no navegador | Compras, Produção | L7 |
| Alarmes do B.I. só no Admin; nenhum alarme de "vai faltar" e nenhuma medida de acerto da projeção | B.I. | lacuna |
| Nenhum número do B.I. leva ao registro (drill-down) | B.I. | lacuna |
| Sobra/falta por produto (a pergunta nº 1 do dono) sem painel | B.I. | lacuna |
| Reagendar anúncio, congelar efeitos, pedir duplo controle, editar/desativar oferta e cupom: existem no servidor sem botão | Marketing | lacuna (a de oferta é a mais cara) |
| Filtro do evento das campanhas automáticas só no Admin (sem ele, "Produção concluída" dispara a cada fornada) | Marketing | lacuna |
| Disparo manual pede duas confirmações à mesma pessoa; o backend já tem "autor = aprovador" | Marketing | L4 |
| `sound_enabled` da estação existe no modelo e não é lido; KDS sem push; KDS sem caminho para virar estação | Cozinha | L1/L5 |
| Bloqueio de pagamento mostrado antes do toque na Saída e depois (toast) no preparo | Cozinha | L3 |
| Entregar e despachar sem nenhum desfazer | Cozinha, Gestor | L4 |
| Separar e pesar sem nenhum registro (onde o erro é mais caro) | Produção | rastreabilidade |
| Esgotado conhecido, pausa manual por canal | Gestor | L1 |
| Peça pesada digitada pela etiqueta; o leitor não lê código de balança (EAN-13 com preço/peso) | PDV | L1 |

Cada linha vira item de backlog com o dono decidindo prioridade; nenhuma entra escondida num PR
de tela.

---

## 12. Como isso muda o plano de execução

A ordem aprovada continua (**kit primeiro, Gestor piloto, PDV por último**). O que muda é a unidade
de trabalho: em vez de "tela por tela", **forma por forma**.

1. **Kit por forma.** Cada uma das 7 formas vira uma peça do kit com contrato funcional
   (zonas, ação primária única, densidade por posto, regras de busca/filtro/paginação) e teste do
   contrato. Os 6 gestos transversais idem. A camada visual da v3 (tokens, rail, cabeçalho, busca)
   é o rosto dessas peças.
2. **"O sistema faz o que sabe"** é um pacote próprio, com backend: avançar automático, pausa por
   esgotado, enviar à cozinha ao salvar, reconciliações automáticas, conferência por exceção,
   estado no servidor (rascunhos, timers, checklist, visto, som). Cada item com decisão do dono,
   porque muda regra.
3. **Migração por posto**, não por app: Passe (Gestor + Saída da Cozinha) como piloto, depois Doca,
   Forno, Estação, Escritório, Dono em movimento e, por último, Balcão.
4. **Trava de forma**: toda tela declara sua forma; o teste do contrato reprova botão primário
   duplicado, paginação em fila, edição fixa em composição, conferência linha a linha sem exceção.
5. **Inventário de trabalhos como contrato**: as 302 fichas viram o inventário de não-regressão
   (cada trabalho tem que continuar possível, por dispositivo), no lugar do inventário por tela.

---

## 13. O que é decisão do dono

1. **As sete leis** (§2) como filtro de toda tela.
2. **As sete formas e os seis gestos** (§3 e §4) como gramática única.
3. **A nova fronteira** (§9): Passe como posto único da saída; pausa automática por esgotado;
   avisos transacionais saindo do Marketing; Estoque e Fim do dia como trabalhos próprios; B.I. como
   fonte; Comprar e Receber como andares separados.
4. **O que o sistema passa a fazer sozinho** (§5 e §12.2), item a item, porque cada um muda regra
   (ex.: avançar para "pronto" quando a Cozinha conclui; enviar à cozinha ao salvar).
5. **As respostas às três notas** (§10): comanda com lista + total + Pagamento e edição sob demanda;
   PDV no tablet como segundo posto sem dinheiro físico; Cozinha com papéis e densidades por dispositivo.
6. **A ordem**: forma por forma no kit, depois por posto, com o Passe como piloto.

Aprovado isso, a próxima rodada desenha o rosto de cada forma, por dispositivo, a partir da v3.
