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
| **total** | **302 fichas, ~295 trabalhos distintos** | |

O mesmo trabalho do chrome comum ("quem está operando", identificar por PIN/crachá) aparece em até
cinco fichas (PDV P02, Gestor P28, Produção P45, B.I. BI-25, Cozinha C03); por isso ~295 distintos.

Cada ficha tem também a lista de **todas** as telas e estados do app, com o dispositivo que faz
sentido para cada uma. É a base da matriz de cobertura
([`funcoes/cobertura.md`](suite-ux-v2/funcoes/cobertura.md)): nenhuma tela fica sem destino.

O plano passou por uma **revisão adversarial** contra as fichas antes de ir ao dono; as correções
que ela pediu (piloto, guardas das automações, assinatura de duas pessoas, contagem cega, densidades
da Cozinha, trabalhos que não cabiam nas formas) já estão no texto.

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
autoridade. O que o sistema sabe vira **automático por padrão**, e aparece como fato na linha do
tempo do item.
Três travas, porque automático errado custa caro:
- **Automático é o padrão, nunca o único caminho.** O gesto manual continua no menu do item (há
  estações sem tela, que recebem papel; há o leitor de código; há o caso que o sistema não viu).
- **Desfazer só para o que fica dentro da casa.** O que sai da casa (aviso ao cliente, pedido
  concluído para o iFood, mensagem) **espera o prazo do desfazer antes de sair**, ou não é automático.
- **Toda automação tem guarda escrita** (§5.1) e é decisão do dono, uma a uma, porque muda regra.
*Consequência de forma:* o botão principal de cada item é o fato que só o humano conhece; quando o
sistema já sabe o fato, o item avança sozinho e o botão desce para o menu.

### L2. Um trabalho, uma forma, muitas portas
O mesmo trabalho tem a mesma forma em qualquer app, qualquer tela, qualquer dispositivo. A porta
pode ser a fila, o detalhe, a busca, o aviso ou outro app; o que abre é sempre o mesmo.
*Consequência:* a suíte inteira cabe em **7 formas de tela**, **8 gestos transversais** e **1 contrato de chrome** (§3 e §4).

### L3. A informação da decisão está no lugar da decisão, antes do gesto
O que pode impedir ou mudar a decisão aparece **no item, antes do toque**: bloqueio com motivo,
falta, prazo, a conta por trás da sugestão. Nunca um toast depois; nunca em outra aba.

### L4. Caminho feliz sem atrito; atrito proporcional ao irreversível
O caso comum custa 0 ou 1 gesto. Atrito existe só onde há **exceção** (motivo, de uma lista curta)
ou **irreversibilidade** (desfazer para o reversível; selo para o irreversível; assinatura para
exceção de dinheiro ou de autoridade). Conferência é **por exceção**: o que bate entra com **um ato
físico só** (contar volumes, bipar), e mexe-se no que não bate. Nunca entra "sozinho" o que ninguém
viu: perecível com validade e lote, e lote de forno que libera aviso ao cliente, sempre passam por
um olhar humano (que pode ser um só, para o conjunto).

### L5. Atenção é o recurso escasso
O que pede alguém vira **item numa fila com dono**, não toast nem sino solto. A densidade de uma
fila é fixada pela atenção (4 a 6 itens em foco numa estação), não pelos pixels; o excedente vira
número ("+7 na fila") e agregado ("A fazer"). Tela maior aumenta a distância de leitura, não a
contagem. (A tabela densa do desktop não contradiz isso: é **supervisão** de muitas filas, não um
posto de execução.)

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
APONTAR, EXPLICAR-NO-LUGAR) colapsam em **sete formas de tela**, **oito gestos transversais** e
**um contrato de chrome** (identidade e estação).

### 3.1 Sete formas de tela

| forma | o trabalho que serve | onde está hoje (exemplos) |
|---|---|---|
| **FILA** | VIGIAR + TRIAR + AVANÇAR + APROVAR + ASSUMIR | fila de pedidos (Gestor), estação e Saída (Cozinha), comandas e encomendas do dia (PDV), expedição e timers (Produção), reposição (Compras), "Precisa de você" (Shopman Apps). **A criar:** "a caminho" (Compras, o pedido de compra não existe como objeto hoje) e a fila de anúncios esperando o meu sim (Marketing, hoje tem 5 portas e nenhuma tela) |
| **CONFERÊNCIA** | REGISTRAR-QUANTIDADE + CONFERIR + SEPARAR | produzir, fechar fornada com QC, corrigir QC, planejar (Produção); conferir NF (Compras); entregador voltou, maquininha voltou, acerto (Gestor). **Modo cego:** abrir e fechar caixa, fechar o dia, contagem de estoque. **Modo lista (SEPARAR):** separação de insumos e de encomendas, que é marcar o que já foi separado, sem número |
| **COMPOSIÇÃO** | COMPOR + SELAR | venda (PDV), entrada sem NF e pedido ao fornecedor (Compras), campanha e anúncio (Marketing), receita (Produção), oferta e cupom (Marketing) |
| **CADASTRO** | CONFIGURAR (cadastral) + CORRIGIR cadastro + AVALIAR | catálogo e painel do produto, clientes e unificação, vínculos de canal (Gestor); insumos, fornecedores, custos (Compras); receitas (versões, e a nota 0–5 da versão, P42, que é juízo e não conferência); modelos e plataformas (Marketing) |
| **LEITURA** | ENTENDER | B.I. (8 seções), relatórios da Produção, X/Z do PDV, histórico do Marketing |
| **FOCO** | uma tarefa só, com a mão ocupada ou o cliente na frente | pagamento (PDV), finalizar lote (Produção), leitor de NF e de código (Compras/PDV), selo de anúncio (Marketing). **Variante "executar instrução"** (SEGUIR-INSTRUÇÃO): pesar por ficha (P08) e ler a fórmula na bancada (P34), receita escalada, passo a passo, no tablet |
| **MONITOR** | VIGIAR à distância, sem gesto | Painel de retirada (Cozinha), Letreiro (Produção), Tela do cliente (PDV), quadro de estação em TV |

A contagem cega mora só na CONFERÊNCIA (modo cego); quando ela acontece com a mão ocupada, abre em
FOCO, mas a forma é a da conferência.

### 3.2 Oito gestos transversais (valem dentro de qualquer forma)

| gesto | o que é | onde se repete hoje |
|---|---|---|
| **LOCALIZAR** | uma busca, uma tecla, alcance (esta tela · app · suíte), leitura de código pela câmera ou leitor | "Cliente veio buscar?", busca de produto F3, busca de pedido, busca de insumo, cliente no PDV, campanha, código da Via Cozinha |
| **EXCEÇÃO ASSINADA** | ATO + MOTIVO (lista curta) + ASSINATURA. Duas regras diferentes: **autoridade** (basta ser gerente; zero passos se o gerente já é quem opera) e **segunda pessoa** (a assinatura tem de ser de outra pessoa, nunca de quem está logado) | autoridade: sangria, troco servido, devolução, estorno, desconto acima do limite, cancelar venda, nota avulsa, edição mais barata, gaveta emperrada, desligar canal. Segunda pessoa: cancelar pedido pago (Gestor P19), disparo acima do limiar (Marketing M09). *Proposta, muda regra:* estornar produção (P13, hoje basta `can_void` com motivo opcional) |
| **CONFIRMAR COM PROVA** | prévia do efeito + idempotência + conflito "manter o meu / usar o atual" + recuperar rascunho | 12 lugares no Gestor (preço, publicação, lote, ordem de coleção…), recuperação de rascunho no Marketing (M36); cresce com a L7, porque estado no servidor aumenta conflito entre dispositivos |
| **INTERRUPTOR** | ligar/desligar algo que age sozinho: 1 toque, reversível, efeito imediato, no dispositivo onde está a urgência; **automático quando o sistema sabe** | pausar produto por canal, desligar canal, campanha ligada, congelar efeitos externos, aviso transacional ativo, som da estação |
| **SELO / DESFAZER** | confirmação com atrito proporcional: desfazer por N segundos se reversível; selo (frase, senha, TOTP) se irreversível para fora da casa | finalizar ticket (desfazer 5 s, reabrir 30 min); entregar e despachar (hoje sem nada); disparar campanha e publicar anúncio (selo); remover item (desfazer) |
| **ANOTAR** | motivo ou ocorrência a partir de uma lista curta da casa, com "Outro" em texto; sem destinatário | recusa, cancelamento, perda no QC, ocorrência no recebimento, divergência da contagem, comentário no histórico |
| **INSTRUIR** | mensagem com destinatário, que tem de chegar ao lugar de quem executa | nota da cozinha (Gestor P16, tags + texto) que precisa aparecer no ticket da estação; observação da linha no PDV |
| **AVISO** | o que pede alguém vira item na fila do dono, com push quando ele não está olhando, e some quando resolvido | alertas do Gestor, sino da Produção, sino do Marketing, alarmes do B.I. (hoje só no Admin), som |
| **ACUSAR CIÊNCIA** | provar que viu, quando nada mais prova (diferente de AVISO); registrado no servidor, com escopo de estação | "Recebi o cancelamento" (Cozinha K10, por ticket, evita desperdício); "Visto" do pedido novo (K20, hoje por dispositivo e local, por isso duas telas da mesma estação discordam) |

**EMITIR** (vias, etiquetas, NFC-e) deixa de ser trabalho: é efeito colateral do ato. Só a falha
vira item (AVISO) no lugar de quem resolve. **TRAVA-FÍSICA** (gaveta fechada, papel bipado) e
**DELEGAR** (corrida externa) são estados de um item de FILA, não telas. **TIMER** (forno, timers de
chão) é um estado de item de FILA com contagem regressiva e alarme; o alarme some com o fato que o
resolve (fechar a fornada já declara a retirada, P15), sem "Visto" separado.

### 3.3 Contrato de chrome: identidade e estação

"Quem está operando" (identificar por PIN ou crachá, 5 a 30 vezes por dia no PDV) e "que dispositivo
é este" (provisionar estação, parear TV, instalar, ativar push) não são cadastro de escritório: são
feitos **no próprio dispositivo**, por quem está ali. Um contrato único no kit: trava, PIN/crachá,
troca de operador, e o provisionamento que define de uma vez **estação, som e densidade** (K21/K22;
hoje o `sound_enabled` existe no modelo e não é lido, e só o PDV oferece virar estação).

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
- **Dispositivo:** parede/tablet fixo (4–6 em foco, leitura a 1–2 m); celular (1 em foco + 3 a 5
  linhas compactas, push e vibração porque a tela apaga); desktop (tabela densa com seleção em lote,
  para **supervisão**, não para execução). Densidades por papel no §10.3.

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
| **automática** | o sistema sabe e faz (padrão, nunca o único caminho; guarda no §5.1) | linha do tempo do item, com desfazer para o que fica na casa; o gesto manual no menu | avançar para "pronto" quando a Cozinha conclui; pausar produto esgotado; enviar à cozinha sem toque; consultar resultado incerto |
| **primária** | o fato humano do momento, um por item ou tela | botão largo do item; selo da composição | Entregar · Finalizar 26 un. · Pagamento R$ 41,00 · Confirmar entrada |
| **frequente** | alternativa comum | visível ao lado, peso menor | Recusar · Transferir · Imprimir via |
| **rara** | existe, pouco usada | menu do item/tela, com a mesma tecla de antes | exportar, reimprimir, histórico, comparar versões |
| **exceção** | desvio com autoridade | EXCEÇÃO ASSINADA | cancelar pago, sangria, estorno, desconto acima do limite |
| **irreversível para fora** | sai da casa e não volta | SELO | disparar campanha, publicar anúncio, emitir nota avulsa |

A regra que corta: **se um botão não é o fato humano do momento nem uma alternativa frequente,
ele não está na superfície.**

### 5.1 Guardas das automações (cada uma é decisão do dono)

| automação | o que pode dar errado | guarda |
|---|---|---|
| **Avançar para "pronto" quando a Cozinha conclui** | estação sem tela (Lanches recebe papel) nunca conclui; aviso de "pronto" ao cliente não volta atrás | o "Pronto" manual fica no menu do item e no leitor da Via Cozinha; aviso ao cliente só sai depois do prazo do desfazer |
| ~~Pausar produto esgotado~~ → **canais externos respeitam o estoque** (revisto em 03/10 a pedido do dono) | Site/app e PDV **já tratam** o esgotado sem pausa (site bloqueia, mostra "esgotado", oferece "Me avise" e avisa quando volta; PDV mostra o selo e desativa o botão). A lacuna real é **iFood e Meta/Google**: o status enviado olha só publicado/vendável, nunca o estoque (`catalog_projection_ifood.py:143`, `views/product_feed.py:121`), então o iFood segue `AVAILABLE` e o pedido entra para ser recusado. Pausa automática **não** é a cura: misturaria "acabou" com "decisão da casa", desligaria o "Me avise" e estragaria a métrica do `ShelfOutage` | as projeções externas passam a mandar `UNAVAILABLE` / `out of stock` quando o vendável zera e reenviam quando volta (o `ShelfOutage` já detecta a passagem por zero), com a mesma regra de estoque do site; a **pausa manual continua** para o que não é falta de estoque (qualidade, decisão da casa, produto sem rastreio). Volta ao dono como "sim" ou "não" |
| **Enviar à cozinha sem toque** (30 a 200 vezes por dia) · **opcional, desligado por padrão, ligável e reversível por estação** (decisão do dono: depende da equipe e da dinâmica do dia) | mesa ainda decidindo, tempo dos pratos, item removido depois de enviado vira card de cancelamento que a estação tem de reconhecer (desperdício) | enviar depois de um intervalo parado ou ao sair da comanda; "segurar" por linha; desfazer enquanto a estação não iniciou; definir o que é "salvar" (hoje o PDV não tem esse ato) |
| **Reconciliar resultado incerto** (Marketing M13) | repetir um envio cujo resultado é desconhecido manda a mensagem duas vezes | só leitura; um resultado `unknown` nunca é reenviado sozinho |
| **Qualidade por exceção** (P19) | liberar aviso ao cliente de lote que ninguém olhou | o portão humano fica, como **um** ato: "N lotes, nenhuma exceção · Confirmar" |
| **Recebimento por exceção** (C10/C13; hoje o servidor exige o ok linha a linha) | a nota diz 20 kg, chegam 18, entram 20 em silêncio | um ato físico (contar volumes ou bipar cada volume). **Validade é incontornável** (dono): quando tudo bate, a tela pede **só a validade**, uma linha por perecível, do jeito mais rápido possível (atalhos "mesma de ontem", a validade típica do item, ler a data da embalagem pela câmera), e nada mais |
| **Pré-preencher a abertura do caixa** | conferência de custódia vira declaração; o erro se esconde e só aparece na contagem cega do fechamento | a abertura é **contada**, nunca preenchida (P10); o "troco provável" do B.I. vira sugestão de **separação** na véspera (BI-17), não o valor do campo |

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
| Saída do pedido (pronto → saiu/retirou) | Cozinha (Saída) **e** Gestor (avançar, despachar) | **uma** fila de saída, o posto **Saída**, morando no **Gestor** (proposta de 03/10, aguarda o dono); a Cozinha fica só com as estações | mesma `advance_order` (`services/kds.py:975`), dois desenhos; e a Saída da Cozinha hoje manda "abra este pedido no Gestor" quando há maquininha ou troco (`services/kds.py:962`) |
| Pausar produto / desligar canal | Gestor, no Catálogo e em Canais (escritório) | **automático** quando esgota; interruptor também no posto do passe e no celular do gerente | urgência de minutos no lugar de dias |
| Avisos transacionais (pedido, pagamento, fila, fidelidade) **e** a ligação mensagem ↔ modelo aprovado do WhatsApp | Marketing › Plataformas (M30 e M31) | os dois juntos, para Gestor › Canais (Ajustes), levando o TOTP e a permissão `configure_platforms`; exige atualizar o contrato do Marketing (`docs/reference/marketing-surface-contract.md`, `make marketing-docs`) | M31 é comunicação da loja, não campanha, e M30 é o mesmo trabalho com outro alvo (separar os dois quebraria a L2). **Decisão do dono** |
| Contagem de estoque | aba escondida da Base no Compras | trabalho próprio de **Estoque** (gerente, tablet), CONFERÊNCIA cega | é outro papel, outro dispositivo |
| Fim do dia | fechar caixa, fechar o dia e contar a vitrine em telas separadas | um **corredor** só, em sequência, no tablet | mesmo dono, mesmo momento, mesma forma (cega) |
| Projeção, troco, sobra por produto, em risco | B.I. (aba que o decisor não abre) | ao lado da sugestão do plano (Produção), no abrir caixa (PDV), como audiência (Marketing), push | EXPLICAR-NO-LUGAR |
| Alarmes do B.I. | só no painel do Admin | AVISO no celular do dono e na fila do papel certo | ninguém os vê |
| Comprar × Receber | uma navegação para dois papéis opostos | dois andares: Receber (doca, celular, Operação) e Comprar (escritório, desktop, Ajustes) | L6 |
| Prévia de data futura | no cabeçalho da estação da Cozinha | Produção/Encomendas (planejar) | quem executa o hoje não planeja |
| Decisões do Marketing | 5 portas, nenhuma tela | uma FILA de decisões ordenada por prazo, que é ao mesmo tempo Hoje, sino e push | é o trabalho central do app |

Postos que saem disso (cada um abre direto na sua fila):
**Balcão** (PDV, desktop com periféricos) · **Saída** (saída do pedido) · **Estação** (Cozinha) ·
**Forno** (Produção chão) · **Doca** (Compras receber) · **Estoque** (contagem) · **Fim do dia** ·
**Escritório** (catálogo, canais, compras, receitas, campanhas, B.I.) · **Dono em movimento**
(celular: decisões, alertas, olhada; o modo "fora da loja" depende do consentimento de localização,
ainda pendente na v3).

---

## 10. Dispositivo por trabalho, e as três notas do dono

A cobertura completa (cada tela e estado de cada app, com forma, posto, andar, dispositivo e
destino) está em [`suite-ux-v2/funcoes/cobertura.md`](suite-ux-v2/funcoes/cobertura.md):
**271 linhas**, das quais 150 mantêm a casa (com reforma de forma), 62 se fundem com outra tela do
mesmo trabalho, 18 mudam de app ou posto, 9 viram automático, 10 somem (com motivo) e 22 são telas
novas. Um script cruzou a matriz com os 301 identificadores de trabalho das fichas: **nenhum ficou
sem tela.** Abaixo, as três notas
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
- "Enviar à cozinha" sai do rodapé: se o dono aprovar a automação (§5.1, com intervalo parado,
  "segurar" por linha e desfazer enquanto a estação não iniciou), o envio acontece sozinho e o fato
  aparece na linha ("na cozinha 21:52"); o gesto manual (F9) continua no cabeçalho da comanda. Sem a
  automação, ele fica no cabeçalho, não no pé.
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
- **encomendas e retirada** (a lista do dia, ler o QR, entregar); se a encomenda tem **saldo a
  receber em dinheiro** (P62), o tablet não recebe: entrega a cobrança ao caixa (a encomenda aparece
  na fila do Balcão como "receber R$ 22,00 de Ana Ferreira") e só depois libera a entrega;
- **fim do dia** (contar a vitrine andando).
Em pé é o padrão (na mão), com a fonte em grade grande ocupando a tela e a comanda como folha de
baixo (contagem + total + Pagamento sempre visíveis); o teclado numérico só ao tocar uma linha.

### 10.3 Cozinha no tablet e no celular, e quantos cards cabem

Não houve prévia de tablet de verdade nem de celular, e o celular foi descartado por julgamento.
A análise encontrou quem usa e o quê:

| dispositivo | quem | trabalho | densidade (fixada pela atenção; números da ficha `kds-hub.md` §2b) |
|---|---|---|---|
| tablet fixo na bancada/parede | cozinheiro de estação | preparar (iniciar, finalizar, desfazer) | **4 a 6 tickets** em foco (3×2 em ~1280 px); ticket de 6+ itens ocupa duas alturas; o resto vira "+N" e faixa "A fazer" |
| tablet fixo no passe | expedidor | Saída: entregar, despachar, conferir volumes | **3 a 4 prontos** grandes + **5 a 8 linhas** de "em preparo" (código, tempo, estações faltando) |
| tablet fixo na separação | separador de encomendas | separar (picking), com aviso de estoque por item | **2 a 4 tickets** longos |
| tablet na mão | chefe de cozinha / gerente | o que está atrasado em qualquer estação; corrigir | **6 a 10 linhas** (lista, não grade). A visão "todas as estações" **não existe hoje**: é recurso novo (§11) |
| tablet na mão | atendente de salão ou balcão | achar o pedido do cliente e entregar | **4 a 6 cards** em duas colunas |
| celular | atendente que leva o pedido à mesa ou à porta | prontos para sair: entregar, conferir volumes | **3 a 5 linhas**, o mais antigo no topo, só o primeiro expandido com os itens |
| celular | cozinheiro de estação pequena sem tablet (barista, lanches) | a própria estação | **1 em foco + 2 a 3 linhas** ("próximo", "depois"); exige push e vibração (o KDS não tem push hoje e a tela do celular apaga) |
| celular | gerente fora da cozinha | ser avisado quando passar da meta | **só alerta (push), sem quadro** |
| TV na cozinha | cozinha grande | quadro da estação, só leitura | **6 a 8 tickets** em densidade ampla; o gesto fica num tablet pequeno ou no leitor de código |
| TV no salão | público | Painel de retirada | **12 a 24 códigos** |

O entregador **não usa** o KDS: quem despacha é o expedidor; troco e maquininha são do Gestor.

Sobre "caberia mais card no celular": **cabem mais pedidos, como linhas compactas** (código, tempo,
estado, um gesto), não mais cards completos. O card completo só para o pedido em foco; o resto é
lista. A v3 mostrava dois cards inteiros e nada mais; a função pede um em foco e a fila visível.

### 10.4 App × dispositivo × papel

Toda célula tem um conjunto de trabalhos ou "não oferecido" com o motivo. A cobertura tela a tela
está em [`funcoes/cobertura.md`](suite-ux-v2/funcoes/cobertura.md).

| app | desktop | tablet | celular | parede |
|---|---|---|---|---|
| **PDV** | Balcão completo (periféricos: gaveta, bobina, leitor, 2º monitor) | segundo posto sem dinheiro físico: fila longa e comanda de mesa, encomendas e retirada, fim do dia (§10.2) | balcão de bolso: encomendas do dia e retirada pelo QR, comanda rápida na fila; dinheiro vai ao caixa | Tela do cliente (MONITOR) |
| **Cozinha** | não oferecido (a cozinha não tem desktop; o chefe usa tablet na mão) | estação, passe, separação, chefe (§10.3) | atendente, estação pequena, gerente por push (§10.3) | quadro da estação, Painel de retirada |
| **Gestor** | escritório: fila supervisionada em tabela, catálogo, canais, clientes | passe: fila e saída; interruptores (pausar, desligar canal) | dono em movimento: push, aceitar/recusar, detalhe, interruptores, resumo fora da loja (com consentimento) | não oferecido (a fila de parede é a Saída da Cozinha) |
| **Produção** | gestão: plano, relatórios, receitas (edição), revisão de QC | forno e bancada: dia de produção, expedição, finalizar lote, separação e pesagem (FOCO executar instrução), timers | no bolso: timers que vibram, finalizar lote, ler etiqueta do lote, separar andando, foto da ficha nova (P35) | Letreiro (MONITOR) |
| **Compras** | Comprar: reposição, pedido por fornecedor, custos, base | conferência da nota com a linha aberta ao lado; contagem de estoque | Doca: escanear NF, conferir, confirmar; contagem andando (C28); aprovar pedido de compra (C05) para o dono em movimento; olhar a reposição (C01) | não oferecido |
| **Marketing** | compor campanhas, modelos, ofertas, plataformas | leitura e revisão (o compositor de 5 etapas e o multi-select das ofertas pedem teclado e mouse) | fila de decisões: revisar e selar anúncio do push; interruptor de campanha | não oferecido |
| **B.I.** | estudo: as perguntas semanais e mensais, com aprofundamento | leitura na véspera: projeção do dia (BI-15) e sobra/falta por produto, sentado ou em casa | a olhada (um número e uma frase) e o alerta | não oferecido |
| **Shopman Apps** | fila das filas | fila das filas | fila das filas + busca única com câmera | não oferecido |

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
| Visão "todas as estações" para o chefe de cozinha (o que está atrasado em qualquer estação) | Cozinha | **recurso novo** (regra da casa: não inventar sem decisão do dono) |
| Fila de decisões do Marketing, "a caminho" do Compras, histórico de recebimentos na tela, sobra/falta por produto no B.I. | vários | **telas novas** sobre dado que já existe ou que falta modelar |
| QR na etiqueta do lote (para "ler etiqueta" na Produção) | Produção | recurso novo (a etiqueta de hoje não tem código) |

Cada linha vira item de backlog com o dono decidindo prioridade; nenhuma entra escondida num PR
de tela.

---

## 12. Como isso muda o plano de execução

A ordem aprovada continua (**kit primeiro, Gestor piloto, PDV por último**), **e a reforma de tela
não muda regra de negócio** (premissa da v3). O que muda é a unidade de trabalho: em vez de "tela
por tela", **forma por forma**; e as mudanças de regra que a função pede andam numa trilha à parte.

1. **Kit por forma.** Cada uma das 7 formas vira uma peça do kit com contrato funcional
   (zonas, ação primária única, densidade por posto, regras de busca/filtro/paginação) e teste do
   contrato. Os 8 gestos transversais e o contrato de chrome idem. A camada visual da v3 (tokens, rail, cabeçalho, busca)
   é o rosto dessas peças.
2. **"O sistema faz o que sabe" é uma trilha separada de mudança de regra**, que não bloqueia o
   kit nem o piloto: avançar automático, pausa por esgotado, enviar à cozinha sem toque,
   reconciliações automáticas, conferência por exceção, estado no servidor (rascunhos, timers,
   checklist, visto, som). Cada item com a guarda do §5.1 e uma decisão do dono.
3. **Piloto: a fila do Gestor**, com as regras de hoje (como aprovado). Depois, por posto: Doca,
   Forno, Estação, Escritório, Dono em movimento e, por último, Balcão. Juntar a saída do Gestor e
   a Saída da Cozinha num posto **Saída** só é proposta nova (§13), não continuidade: depende de
   mudança de regra e puxa a Cozinha, que a v3 classificou como risco alto.
4. **Trava de forma**: toda tela declara sua forma; o teste do contrato reprova botão primário
   duplicado, paginação em fila, edição fixa em composição, conferência linha a linha sem exceção.
5. **Inventário de trabalhos como contrato**: as 302 fichas viram o inventário de não-regressão
   (cada trabalho tem que continuar possível, por dispositivo), no lugar do inventário por tela.

---

## 13. O que é decisão do dono

**Respostas do dono (03/10/2026):**
- Leis, formas e gestos: **aprovados** em geral. Recursos novos: **aprovados**.
- Nova fronteira: **aprovada**. O posto do "Passe" se chama **"Saída"** (por enquanto), ou **"Saída
  da Cozinha"** sempre que couber; é o termo que a Cozinha e o vocabulário da casa já usam.
- Automações: (1) "pronto" sozinho no Gestor **sim**; (2) pausa de esgotado **revista** (ver §5.1:
  o que falta é iFood e Meta/Google respeitarem o estoque, não pausa); (3) enviar à cozinha sem toque
  **opcional por estação, desligado por padrão**; (4) Marketing confere o incerto sozinho **sim**;
  (5) qualidade em lote **sim**; (6) recebimento por exceção **sim, com a validade sempre pedida**, de
  forma ultra facilitada.
- Trabalhos fora dos apps: editar cliente ganha tela no Gestor **sim**; alarmes do B.I. com tela e
  no celular **sim**; feriados e clima automáticos **sim, feriados com confirmação do gestor**; regras
  de disparo do Marketing ficam no Admin **sim**; etiquetas de consumo e lugares do salão: explicados
  ao dono, decisão pendente.
- iFood e Meta/Google passam a respeitar o estoque (no lugar da pausa automática): **sim**.
- Etiqueta de consumo do produto: o nome fica **"Vocação"** (do produto), como o dono já tinha nomeado em 17/08 (ele chegou a propor "Perfil de consumo" e voltou atrás) e quer o campo no
  **cadastro do produto no Gestor (Catálogo, painel do produto)**. Hoje o painel não tem o campo; o dado
  mora em `ProductConsumptionTag` (separado do produto de propósito, chaveado por SKU texto para o
  histórico externo). A tela escreve nesse modelo; o modelo não muda. Produto novo sem perfil vira
  aviso para classificar com um toque.
- Lugares do salão: o dono teme trabalho manual que envelheça. Não há mapa nem gesto por venda: o
  cadastro é a lista de mesas e lugares (`SeatingSpot`, uma vez, muda só quando muda o mobiliário) e a
  lotação é calculada sozinha pela comanda (abre/paga) e pelo modo de consumo (`services/room.py`).
  Aprovado: fica automático, e o B.I. mostra "calculado com N lugares, cadastrados em dd/mm". O dono
  quer também um **editor visual de mesas** (arrastar, reconfigurar à vontade conforme a realidade),
  em Ajustes. Hoje o `SeatingSpot` não guarda posição nem forma: o editor pede campos novos de
  layout (modelo do backstage, não do Core), e usa `active_from`/`active_until` para não reescrever
  o passado ao mudar o salão.

1. **As sete leis** (§2) como filtro de toda tela.
2. **As sete formas, os oito gestos e o contrato de chrome** (§3 e §4) como gramática única.
3. **A nova fronteira** (§9): Estoque e Fim do dia como trabalhos próprios; B.I. como fonte;
   Comprar e Receber como andares separados; avisos transacionais e modelos do WhatsApp saindo
   juntos do Marketing (com mudança no contrato do Marketing). E, como **pedido de mudança de uma
   decisão já tomada**: juntar a saída do Gestor e a Saída da Cozinha num posto só, **Saída** (hospedado no Gestor, §15).
4. **O que o sistema passa a fazer sozinho** (§5.1 e §12.2), item a item, com a guarda de cada um,
   porque cada um muda regra. Também: a regra de **segunda pessoa** na assinatura (§3.2) e o estorno
   de produção passando a pedir gerente.
5. **As respostas às três notas** (§10): comanda com lista + total + Pagamento e edição sob demanda;
   PDV no tablet como segundo posto sem dinheiro físico; Cozinha com papéis e densidades por dispositivo.
6. **A ordem**: forma por forma no kit; a fila do Gestor como piloto (como aprovado); a trilha de
   regras em paralelo; depois por posto, Balcão por último.
7. **Os recursos novos** do §11 (visão "todas as estações", telas novas, QR na etiqueta do lote),
   porque a casa não inventa recurso sem decisão do dono.
8. **Cinco trabalhos que hoje vivem fora dos apps** (Admin ou terminal) e continuam lá até decisão:
   editar o cadastro do cliente (Gestor U05); cerimônia do disparo e público mínimo (Marketing M38);
   alarmes, etiquetas de consumo, lugares do salão e cargas de dados do B.I. (BI-22, BI-23, BI-24).
   Ganham tela ou ficam como estão?

Aprovado isso, a próxima rodada desenha o rosto de cada forma, por dispositivo, a partir da v3.

## 14. Prévias v4: o rosto da função (03/10/2026)

15 telas, cada uma com pinos numerados e legenda que diz qual lei ou forma ela materializa.
Imagens em [`suite-ux-v2/v4/`](suite-ux-v2/v4/); fontes, gerador e spec (`SPEC4.md`) em
`suite-ux-v2/fontes/v4/`.

| Tela | Forma · lei | Arquivo |
|---|---|---|
| PDV · Venda (desktop) | COMPOSIÇÃO: lista + total + Pagamento; editor da linha sob demanda; 13 linhas visíveis (hoje 8, v3 10) | `pos-sale.jpg` |
| PDV · tablet (segundo posto, sem gaveta) | grade é a tela, comanda em folha; numérico só ao tocar a linha; pagamento eletrônico, dinheiro vai ao Balcão | `pos-tablet.jpg` |
| PDV · Fim do dia | corredor de 3 passos, CONFERÊNCIA cega, pergunta do dia estranho, selo do dia | `fim-do-dia.jpg` |
| Saída da Cozinha · tablet | FILA do expedidor; pronto automático marcado; entregar com desfazer | `saida-tablet.jpg` |
| Cozinha · estação · tablet | 4–6 tickets, "+N na fila", bloqueio de pagamento antes do toque | `cozinha-estacao.jpg` |
| Cozinha · celular | Saída no bolso, barista, gerente só com o aviso | `cozinha-celular.jpg` |
| Gestor · fila | só fato humano é botão; "o sistema fez · desfazer" | `gestor-fila.jpg` |
| Gestor · produto | Vocação no cadastro; canais externos respeitam o estoque; pausa manual com motivo | `catalogo-produto.jpg` |
| Compras · Doca · celular | recebimento por exceção; validade sempre pedida, em um toque | `compras-validade.jpg` |
| Produção · Qualidade | qualidade em lote, exceções à parte | `producao-qualidade.jpg` |
| Produção · Planejamento | o porquê na linha (L3); falta de insumo no planejar | `plano-porque.jpg` |
| B.I. · Sobrou ou faltou | LEITURA: pergunta, resposta, comparação, aprofundar | `bi-sobra.jpg` |
| PDV · Ajustes › Salão | editor visual de mesas; vale a partir de hoje | `salao-mesas.jpg` |
| Marketing · celular | fila de decisões por prazo; selo com digital | `marketing-decisoes.jpg` |
| Shopman Apps | a fila das filas | `hub.jpg` |

**Propostas novas que as prévias assumem (pedem o "sim" do dono):** confirmar envio do Marketing
com a digital do dispositivo (a frase digitada fica como alternativa) e segunda pessoa acima de um
limiar; desfazer de 5 s em Entregar/Despachar na Saída; dinheiro no tablet do PDV vira "receber"
na fila do Balcão.

**Não desenhado (só na legenda):** passo 2 do Fim do dia (contar a vitrine, mesmo contador por
produto), abertura de caixa, editor de mesas no tablet, diálogo de exceção assinada do Gestor.

## 15. Rodada de 03/10 (tarde): respostas do dono e o que mudou

**Decidido:**
- Envio do Marketing confirmado com a **digital do dispositivo**, com segunda pessoa acima do limiar: **sim**.
- **Desfazer de 5 s** em Entregar e Despachar, e o aviso ao cliente só depois do prazo: **sim**.
- **Fechamento às cegas sem R$, para ninguém** (nem Gestor, nem gerente): nenhum valor absoluto de
  venda, esperado ou diferença no corredor do Fim do dia; no máximo relativo (%), e mesmo isso com
  cautela. A diferença do caixa vira veredito ("dentro da tolerância" / "fora: o gestor confere"). O
  número só existe na auditoria do Dono (`cashman.audit_shift`). Achado: o endpoint do fechamento
  (`DayClosingView.get`) entrega ao gerente `expected_amount_q`, `difference_q`, totais por meio e
  `qty_available` (não renderizados, mas no JSON) — virou tarefa à parte.
- **Vocação** com o peso da sua utilidade: uma linha pequena no painel, aviso discreto na lista.
- **Planejamento**: a linha mostra só o número e no máximo um sinal; a conta inteira vai para um
  "Por quê" que abre por cima.

**Proposta revista: PDV no tablet.** A proposta "dinheiro vai para a fila do Balcão" faria o cliente
entrar em outra fila. Fatos do código: cartão não tem fio com a maquininha (o operador passa e
confirma, `payman` `asserted_at_terminal`), PIX mostra QR na tela, e um tablet pode ser provisionado
**dividindo a gaveta e o turno do Balcão** (`station_terminal_shared`, `api/operations.py:1133`); a
comanda mora no servidor. Proposta: o tablet é um segundo posto **na mesma gaveta e no mesmo turno**
do Balcão, com todos os meios na mesa (maquininha vai até a mesa; dinheiro entra na mesma gaveta, mesma
contagem cega). Sem energia: o tablet segue no 4G, a maquininha tem bateria e 4G, a gaveta abre na
chave, sem cupom impresso; **sem internet nenhuma o sistema não vende** (não há fila local hoje): um
modo de contingência é decisão à parte. Prévia: `pos-tablet-fluxo.jpg`.

**Proposta revista: uma Saída só.** Hoje existem duas telas para o mesmo fato (Cozinha › Saída e a
zona Saída do Gestor), com a mesma `advance_order`. As prévias desenharam as duas, o que pareceu um
terceiro painel. Proposta: **uma fila de saída, no Gestor** (dono do ciclo do pedido, já resolve
maquininha e troco, que a Saída da Cozinha hoje recusa), com um modo de toque para o tablet do passe;
a Cozinha fica com as estações e o "em preparo". Aguarda o dono.

**Novos pacotes de trabalho:**
- **UX-14 Respostas ativas.** O B.I. "Sobrou ou faltou ontem?" vira padrão da suíte: cada papel tem
  suas perguntas, respondidas sem pedir, na fila e no push (Produção: o que fazer amanhã e por quê;
  Compras: o que comprar até sexta; Gestor: quem está esperando demais; Marketing: o que divulgar
  agora; Balcão: troco para amanhã). Começa por inventariar a pergunta nº 1 de cada papel.
- **UX-15 Ajustes em todos os apps.** Cada app ganha o andar Ajustes para o que o operador muda com
  frequência (impressoras, maquininhas, salão, envio à cozinha, som e densidade da estação, canais).
- **UX-16 CRUD no Nuxt.** Trazer para os apps o cadastro que se mexe na operação; o Admin fica com a
  configuração geral que quase não muda. Começa por medir quais páginas do Admin o operador abre e
  com que frequência, e decide por frequência × papel.
- **Nome.** O sistema se chama **Shopman** na frente do operador. Para a home ("Shopman Apps"), opções
  em aberto (§13): "Central" (já é o endereço `central.`), "Início", ou só "Shopman".
