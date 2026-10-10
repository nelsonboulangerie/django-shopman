# Roteiros da QA física, do ensaio geral e do canário de um

> Para imprimir e levar à loja. Uma folha por papel: **cliente**, **balcão**, **cozinha** e
> **gerente**, mais a folha dos **periféricos** (impressão, gaveta, som, tablets) e a do
> **canário de um**. Cada passo diz **o que tocar** e **o que conferir**. Quando algo não
> sair como escrito, marque ✗ e preencha uma linha na [folha de anotação](#folha-de-anotação).
>
> Escrito a partir das telas como estão no `main` em 10/10/2026 (rotas, botões e frases
> lidos no código). Se a tela disser outra coisa, vale a tela: anote a diferença, ela
> também é achado.
>
> Fecha as linhas **QA física Omotenashi** e **Impressão, gaveta e som** da
> [matriz canônica](../plans/GO-LIVE-READINESS-PLAN.md) e o §5 do
> [pré-flight](go-live-preflight.md). O canário é o §4 do [cutover](go-live-cutover.md).

## Quando usar

| Rodada | Onde | Dinheiro | Nota fiscal | Quem |
|---|---|---|---|---|
| **Ensaio geral** (uma semana antes) | alpha, na loja, com os dispositivos de verdade | Pix da Efí em sandbox, cartão Stripe de teste (`4242 4242 4242 4242`) | Focus em homologação (sem valor fiscal) | equipe inteira, cada um no seu papel |
| **Dia D, canário de um** | produção, depois do deploy da virada | Pix e cartão **reais**, um de cada, e um estorno | Focus em produção | o dono compra; o gerente confere |
| **Dia D, abertura** | produção | real | real | equipe, repetindo os passos marcados com ★ |

No ensaio geral, faça **todas** as folhas. No dia D, depois do canário, refaça só os passos
com ★ (o mínimo para abrir a porta com segurança).

## Antes de começar (todas as rodadas)

- [ ] Cada pessoa sabe o seu papel e tem esta folha impressa.
- [ ] Um observador anota o horário de início e o SHA do deploy (o gerente pega no Admin ou com quem fez o deploy).
- [ ] Dispositivos ligados e carregados: PC do balcão (PDV + agente), tablet do balcão (se houver), tablet de cada estação da cozinha, celular do cliente (um iPhone e um Android, se der), tela do cliente no balcão, monitor do Painel de retirada.
- [ ] Impressora térmica do balcão com papel; impressora da estação sem tela (Lanches, TM-T20X) com papel.
- [ ] Gaveta fechada e com o fundo de troco contado.
- [ ] Maquininha carregada e com sinal.
- [ ] Wi-Fi da loja e a rede reserva (4G) identificadas: quem vai desligar a rede no teste sem conexão sabe onde fica o roteador.
- [ ] Loja **aberta** no sistema (a loja mostra o horário de hoje sem aviso de fechada).

### O que anotar quando falhar

Para cada ✗, uma linha na [folha de anotação](#folha-de-anotação):

1. **hora** (com minuto) e **dispositivo** (ex.: "tablet Cafés", "iPhone do Pablo");
2. **folha e passo** (ex.: "Balcão B12");
3. **o que tocou** e **o que apareceu** (copie a frase da tela, palavra por palavra);
4. **código do pedido** ou da comanda, se houver (ex.: `NB-2002`, comanda `1007`);
5. **foto ou captura da tela**, sem dado pessoal de cliente real;
6. se **travou o trabalho** (não dá para seguir) ou **só incomodou**.

Não tente consertar na hora. Anote, siga para o próximo passo se der, e avise o gerente
se travou.

---

## Folha 1 · Cliente (loja online)

Quem faz: alguém da equipe no celular, **fora** do Wi-Fi da loja (no 4G), como um cliente
faria. Endereço: o domínio da loja (`www.`).

### C1. Cardápio e sacola

- [ ] ★ **C1.1** Abrir a loja no celular. **Confira:** a Home carrega em menos de 3 s, com o horário de hoje e sem aviso de loja fechada.
- [ ] ★ **C1.2** Tocar em **Cardápio**. **Confira:** título "Cardápio", produtos com foto e preço; os esgotados com o selo "Indisponível" e foto acinzentada.
- [ ] **C1.3** Ligar **Mostrar só disponíveis**. **Confira:** os indisponíveis somem; desligar traz de volta.
- [ ] ★ **C1.4** Tocar em **Adicionar** num produto. **Confira:** o botão vira o contador (− 1 +) e o ícone da **Sacola** na barra de baixo pulsa. Não aparece aviso: isso é o esperado.
- [ ] **C1.5** Num produto com opções, tocar em **Adicionar**, escolher a opção e confirmar. **Confira:** aviso "Adicionamos … à sua sacola." e o produto mostra "N na sacola".
- [ ] **C1.6** Num produto indisponível que aceita aviso, tocar em **Me avise sempre**. **Confira:** abre "Ative seu aviso" com a declaração de 18 anos; sem entrar, o botão leva a entrar.
- [ ] **C1.7** Abrir um produto (toque na foto). **Confira:** a página do produto tem foto, descrição e o mesmo botão **Adicionar**.

### C2. Sacola

- [ ] ★ **C2.1** Tocar na **Sacola**. **Confira:** "Sua sacola" com "N itens · R$ total", e o total bate com a soma de cabeça.
- [ ] **C2.2** Aumentar e diminuir a quantidade de um item; tocar na lixeira de outro. **Confira:** total recalcula na hora; o item removido some.
- [ ] **C2.3** Deixar a sacola abaixo do pedido mínimo (se houver). **Confira:** "Faltam R$ X para o pedido mínimo de R$ Y" e **Finalizar pedido** desligado com o motivo.
- [ ] ★ **C2.4** Com a sacola válida, tocar em **Finalizar pedido**. **Confira:** sem estar logado, vai para a tela de entrar com a frase "Sua sacola está guardada."

### C3. Entrar

- [ ] ★ **C3.1** Tocar em **Abrir o WhatsApp**, enviar a mensagem pronta e voltar à loja. **Confira:** a loja entra sozinha em poucos segundos e segue para o checkout.
- [ ] **C3.2** (outro celular) Tocar em **Prefere receber um código por SMS?**, informar o telefone, **Receber por SMS**. **Confira:** o SMS chega em até 1 min; o código de 6 dígitos entra sozinho; "Salvar este aparelho?" aparece antes de **Entrar**.
- [ ] **C3.3** Digitar um código errado. **Confira:** "Código inválido ou expirado." e dá para tentar de novo.
- [ ] **C3.4** Cliente novo: **Confira:** a loja pergunta "Como podemos te chamar?" antes de seguir.
- [ ] ★ **C3.5** **Confira:** no ensaio aparece o selo "Ambiente de teste"; **no dia D ele NÃO pode aparecer** (se aparecer, é ✗ que trava).

### C4. Checkout com retirada

- [ ] ★ **C4.1** Em "Finalize seu pedido", conferir **Contato** e tocar em **Continuar**.
- [ ] ★ **C4.2** Em **Como receber**, escolher **Retirada** ("Gratuita").
- [ ] ★ **C4.3** Em **Quando**, escolher hoje e um horário. **Confira:** horários que já passaram aparecem riscados com "Horário já passou"; dias fechados riscados.
- [ ] ★ **C4.4** Em **Pagamento**, escolher **Pix**. Tocar em **Revisar pedido**. **Confira:** "Revise seu pedido" lista itens, subtotal e total certos.
- [ ] ★ **C4.5** Tocar em **Enviar pedido**. **Confira:** abre a página do pedido (`/pedido/<código>`) com "Aguardando a loja". Anote o código: _______
- [ ] **C4.6** **Confira** no WhatsApp do cliente: chega "Recebemos seu pedido…".

### C5. Pagar com Pix

O Pix só é gerado **depois que a loja aceita** o pedido (o gerente aceita no Gestor, Folha 4,
G1.3). Combine com o gerente.

- [ ] ★ **C5.1** Depois do aceite, **Confira** sem recarregar: "Gerando seu Pix" e logo "Pague com Pix" com o QR, o **Pix Copia e Cola**, **Copiar código** e o tempo para pagar (10 min).
- [ ] **C5.2** Tocar em **Copiar código**. **Confira:** aviso "Código Pix copiado." e o código cola no app do banco.
- [ ] ★ **C5.3** Pagar (ensaio: Pix de sandbox pelo gerente na Efí; dia D: Pix real no app do banco). **Confira**, sem recarregar a página: a etapa vira "Pago" e o WhatsApp avisa a confirmação.
- [ ] ★ **C5.4** **Confira:** o botão "Simular pagamento" **não existe** na tela. Se aparecer, é ✗ que trava (o Pix ainda está no simulado).
- [ ] **C5.5** Deixar um segundo pedido com Pix vencer (10 min sem pagar). **Confira:** "Pagamento expirado" e o WhatsApp diz que nada foi cobrado.

### C6. Checkout com entrega e cartão

- [ ] ★ **C6.1** Novo pedido; em **Como receber**, escolher **Entrega**.
- [ ] ★ **C6.2** Em **Endereço de entrega**, digitar "Rua, número ou CEP" de um endereço da área. **Confira:** o mapa pergunta "É aqui que vamos entregar?"; depois de **Usar este endereço**: "Entregamos no seu endereço · taxa de R$ X · a N km".
- [ ] **C6.3** Testar um endereço fora da área. **Confira:** "Ainda não entregamos nesse endereço" e o botão para trocar para retirada.
- [ ] ★ **C6.4** **Confira:** o campo "CPF ou CNPJ para a nota fiscal" é obrigatório na entrega; sem ele, o pedido não segue ("Falta o CPF ou CNPJ para a nota fiscal.").
- [ ] **C6.5** Em **Quando**, escolher a data. **Confira:** na entrega não há escolha de horário (só data).
- [ ] ★ **C6.6** Em **Pagamento**, escolher **Cartão**, **Revisar pedido**, **Enviar pedido**.
- [ ] ★ **C6.7** Na página do pedido, tocar em **Pagar com cartão**. **Confira:** abre a página segura do Stripe numa aba nova. Ensaio: cartão `4242 4242 4242 4242`, validade futura, CVC qualquer. Dia D: cartão real.
- [ ] ★ **C6.8** Depois de pagar, voltar à aba do pedido. **Confira:** "Pagamento autorizado" e, quando a loja confirmar, "Pago".
- [ ] **C6.9** **Confira:** no ensaio aparece a caixa "Ambiente de teste" com os cartões de teste; **no dia D ela NÃO pode aparecer**.

### C7. Acompanhar

- [ ] ★ **C7.1** Manter a página do pedido aberta enquanto a cozinha trabalha. **Confira:** as etapas andam sozinhas: "Recebido", "Aceito", "Pago", "Em preparo", "Pronto" (e "Saiu para entrega", "Entregue" na entrega). O selo diz "Ao vivo".
- [ ] **C7.2** **Confira** no WhatsApp: chegam "está confirmado", "em preparo", "pronto e esperando por você no balcão" (retirada) ou "saiu" (entrega).
- [ ] **C7.3** **Confira:** quando a NFC-e sai, chega o link da nota.
- [ ] **C7.4** Num pedido ainda sem pagamento, tocar em **Cancelar pedido**, marcar "Entendo que o pedido será cancelado…" e **Confirmar cancelamento**. **Confira:** "Pedido cancelado" e a cozinha recebe o aviso (Folha 3, K4).
- [ ] **C7.5** Num pedido já pago, **Confira:** o botão é **Solicitar cancelamento** (vira pedido ao gerente), não cancela sozinho.
- [ ] **C7.6** Abrir **Conta › Pedidos**. **Confira:** os pedidos do teste aparecem em "Em andamento" ou "Finalizados".

---

## Folha 2 · Balcão (PDV)

Quem faz: o operador do caixa no PC do balcão. Onde houver tablet de balcão, repita os
passos marcados com 📱 nele.

### B1. Entrar e abrir o caixa

- [ ] ★ **B1.1** Abrir o PDV. **Confira:** "Identifique-se para operar"; entrar com o PIN. PIN errado mostra "Identificação inválida. Tente de novo."
- [ ] **B1.2** Ficar 1 min sem tocar em nada. **Confira:** a tela trava sozinha e pede o PIN de novo.
- [ ] ★ **B1.3** Ir em **Caixa**, tocar em **Abrir caixa**, contar a gaveta e informar o **Fundo de troco**; **Abrir caixa e vender**. **Confira:** aviso "Caixa aberto · fundo R$ X".
- [ ] ★ **B1.4** Em **Ajustes › Terminal**, tocar em **Testar o agente de novo**. **Confira:** Impressora e Gaveta aparecem prontas. Se não, ✗ e vá à Folha 5.

### B2. Venda em dinheiro

- [ ] ★ **B2.1** Buscar um produto em "Buscar produto, código ou comanda" e tocar nele; adicionar mais dois itens. **Confira:** a contagem fala em **itens** (unidades), e o total bate.
- [ ] ★ **B2.2** Tocar em **Pagamento** (F4), escolher **Dinheiro**, tocar numa nota maior ("Recebi nota de R$ X"). **Confira:** o visor mostra o **Troco** certo.
- [ ] ★ **B2.3** Tocar em **Validar** (Enter). **Confira:** a gaveta abre sozinha (PC do balcão), sai a Via Recibo, e a tela diz "Venda concluída" com o troco. Com **CPF na nota** (tecla F), a tela mostra "NFC-e em emissão…" que vira "NFC-e autorizada".
- [ ] ★ **B2.4** Fechar a gaveta. **Confira:** a próxima venda só começa com a gaveta fechada (se ficar aberta, aparece "Gaveta aberta" e o PDV espera).
- [ ] **B2.5** Tocar em **Nova venda**. **Confira:** o PDV limpa e volta à busca.

### B3. Venda na maquininha

- [ ] ★ **B3.1** Lançar itens, **Pagamento**, **Débito** (ou **Crédito**), **Validar**. **Confira:** "Passe na maquininha" com o valor; cobrar na maquininha e tocar em **OK, cobrei na maquininha**.
- [ ] ★ **B3.2** **Confira:** a gaveta **não** abre; sai a Via Recibo; "Venda concluída".

### B4. Venda com Pix no balcão

- [ ] ★ **B4.1** Abrir a **Tela do cliente** (barra lateral) no monitor virado para o cliente. **Confira:** mostra "Que bom ter você aqui."
- [ ] ★ **B4.2** Lançar itens, **Pagamento**, **Pix**, **Validar**. **Confira:** o QR aparece no PDV ("Aguardando Pix") **e** na Tela do cliente ("Aponte a câmera para pagar…").
- [ ] ★ **B4.3** Pagar o Pix. **Confira:** aviso "PIX do pedido X confirmado.", a venda conclui sozinha e a Tela do cliente diz "Volte sempre."

### B5. Comanda, cozinha e transferir

- [ ] ★ **B5.1** Em **Comandas** (F2), **Abrir comanda** (próxima livre). Lançar um café e um lanche. **Enviar à cozinha** (F9). **Confira:** os itens mostram "Na cozinha" e o botão diz "Enviado"; a cozinha recebe (Folha 3, K2).
- [ ] **B5.2** Abrir uma segunda comanda. Na primeira, **Selecionar** o lanche e tocar em **Transferir** (F10), escolher a segunda como **Comanda de destino**. **Confira:** o lanche sai de uma e entra na outra com o mesmo preço; a cozinha **não** recebe um pedido novo do lanche (ele já estava lá), e o card passa a dizer a comanda nova.
- [ ] **B5.3** Usar **Dividir**: separar um item numa **Nova comanda**. **Confira:** nasce a comanda "N/2" com o item.
- [ ] **B5.4** Usar **Juntar**: juntar a comanda nova na original. **Confira:** a comanda de origem fica livre.
- [ ] **B5.5** Tirar um item já enviado (**Cancelar envio à cozinha**). **Confira:** a cozinha recebe a mudança com alarde (Folha 3, K4).

### B6. Dividir a conta

- [ ] ★ **B6.1** Numa comanda com 4 itens, **Pagamento**, **Dividir** (F10). Em "Em quantas pessoas?", tocar **2**. **Confira:** o visor diz "Peça R$ X · pessoa 1 de 2".
- [ ] **B6.2** Receber a pessoa 1 em dinheiro e a pessoa 2 na maquininha. **Confira:** "Restante" chega a zero e a venda conclui com as duas formas no recibo.

### B7. Desconto com gerente

- [ ] ★ **B7.1** Num item, abrir o item e tocar em **Desconto**, "Em %", motivo **Cortesia**. **Confira:** o total cai.
- [ ] ★ **B7.2** Dar um desconto na venda acima do limite. **Confira:** "Esta venda precisa de um gerente." e o botão vira **Pedir autorização**.
- [ ] ★ **B7.3** Tocar em **Pedir autorização**. **Confira:** "Autorizar a venda", "Quem autoriza?"; o gerente digita o PIN dele; o operador continua logado ("Você continua como …") e a venda conclui.
- [ ] **B7.4** PIN de gerente errado. **Confira:** a venda não conclui.

### B8. Sem conexão: derrubar a rede e voltar

Combine com o gerente. **Desligue a rede do balcão** (tirar o cabo do PC ou desligar o
Wi-Fi do PC; se o roteador for de toda a loja, avise a cozinha antes). Cronometre.

- [ ] ★ **B8.1** **Confira** em até 5 s: faixa "Sem conexão…" no topo, que **não** cobre nenhum botão; e o aviso "Sem conexão. O balcão continua vendendo."
- [ ] ★ **B8.2** Tocar em **O que funciona agora**. **Confira:** a lista diz dinheiro e maquininha sim; Pix, entrega, encomenda e desconto não.
- [ ] ★ **B8.3** Fazer uma venda em **dinheiro**. **Confira:** a gaveta abre (PC do balcão), o recibo sai pela impressão do navegador, e a tela diz "Venda guardada neste dispositivo."
- [ ] ★ **B8.4** Fazer uma venda na **maquininha**. **Confira:** o aviso passa a "Sem conexão. 2 vendas esperando envio."
- [ ] **B8.5** Tentar **Pix**. **Confira:** "Pix precisa de conexão. Receba em dinheiro ou na maquininha."
- [ ] **B8.6** Tentar dar um **desconto**. **Confira:** o PDV recusa e diz que precisa de conexão.
- [ ] **B8.7** Tentar **Fechar o caixa**. **Confira:** "N vendas feitas sem conexão ainda não foram enviadas. Envie antes de fechar o caixa."
- [ ] ★ **B8.8** **Religar a rede.** **Confira** em até 30 s: "Enviando 2 vendas guardadas…" e os avisos "Venda guardada enviada: pedido NB-…" (anote: _______ e _______).
- [ ] ★ **B8.9** **Confira** no Gestor (Folha 4): as duas vendas aparecem como pedidos pagos, e a NFC-e de cada uma sai depois do envio.
- [ ] **B8.10** **Confira:** a faixa some e o PDV volta a vender Pix.

### B9. Sangria, suprimento e fechar o caixa

- [ ] **B9.1** Em **Caixa**, abrir "Movimento de caixa", **Saída de caixa** (sangria), valor e motivo, PIN do gerente, **Registrar movimento**. **Confira:** sai o comprovante e a gaveta abre.
- [ ] **B9.2** **Entrada de caixa** (suprimento) do mesmo jeito. **Confira:** sai o comprovante.
- [ ] ★ **B9.3** No fim, **Fechar caixa**: contar a gaveta e informar o **Valor contado**, **Conferir e fechar**, **Fechar o caixa**. **Confira:** a tela **não** mostra a diferença (contagem cega); o turno encerra.
- [ ] **B9.4** O gerente confere a diferença (Folha 4, G5).

---

## Folha 3 · Cozinha (KDS)

Quem faz: a equipe da cozinha, cada uma no tablet da sua estação. O **Painel de retirada**
fica no monitor público.

### K1. Ligar a estação

- [ ] ★ **K1.1** Abrir o app da Cozinha no tablet (instalado na tela inicial, em tela cheia). Entrar com o PIN. **Confira:** a tela não apaga sozinha com o tempo (deixe parado 5 min).
- [ ] ★ **K1.2** Em **Estações**, tocar na estação deste tablet (Cafés, Lanches, Encomendas…). **Confira:** o título é o nome da estação e o card dela fica marcado "a deste dispositivo".
- [ ] ★ **K1.3** Tocar uma vez em qualquer lugar da tela (isso libera o som no navegador). **Confira:** não aparece "O navegador bloqueou o som desta estação". Se aparecer, tocar em **Ativar o som**.
- [ ] ★ **K1.4** Em **⋯ › Ajustes da estação**, conferir **Som da estação: Ligado**.
- [ ] **K1.5** **Confira:** ao lado do título, "Ao vivo".

### K2. Pedido novo

- [ ] ★ **K2.1** O balcão envia uma comanda (Folha 2, B5.1) ou a loja manda um pedido aceito. **Confira** em até 5 s: o card aparece, toca a fanfarra, e o aviso azul "Pedido novo …" diz "Toca nesta estação até alguém dar Visto."
- [ ] ★ **K2.2** **Confira:** o som se repete a cada 8 s enquanto ninguém dá **Visto**. Medir do outro lado da cozinha: dá para ouvir com o forno e a máquina de café ligados?
- [ ] ★ **K2.3** Tocar em **Visto**. **Confira:** o som para neste tablet **e** nos outros tablets da mesma estação.
- [ ] **K2.4** **Confira** no card: o código grande, "Retirada", "Entrega" ou "Encomenda", os itens ("2× …"), as observações e o tempo correndo.

### K3. Preparar e Pronto

- [ ] ★ **K3.1** Tocar em **Iniciar preparo**. **Confira:** o card passa a "Em preparo" e o botão vira **Pronto …**.
- [ ] ★ **K3.2** Tocar em **Pronto**. **Confira:** o card esmaece e mostra **Desfazer** por 5 s; depois sai da fila.
- [ ] **K3.3** Num outro pedido, tocar em **Pronto** e logo **Desfazer**. **Confira:** o card volta para "Em preparo".
- [ ] **K3.4** Em **⋯ › Reabrir um concluído**, reabrir um pedido. **Confira:** ele volta à fila.
- [ ] **K3.5** Num pedido com pagamento pendente, **Confira:** o card mostra o bloqueio com o motivo e não deixa marcar Pronto.

### K4. Mudança com alarde

> Depende da **#1646** estar no ar. Sem ela, o que existe é o aviso vermelho no topo
> ("Pedido …: item cancelado às …. O resto continua.") com **Recebi o cancelamento**; a
> redução de quantidade e a troca de comanda chegam sem alarde, e isso é ✗.

- [ ] ★ **K4.1** O balcão tira um item já enviado (Folha 2, B5.5). **Confira** em até 5 s: o card vai para o topo com moldura vermelha, "Mudou" e a linha "Cancelado: 1× …"; toca o som de mudança (diferente da fanfarra).
- [ ] ★ **K4.2** Tentar marcar **Pronto** nesse card. **Confira:** o botão é **Recebi o cancelamento** (vermelho); só depois dele o Pronto volta.
- [ ] **K4.3** O balcão diminui a quantidade de um item enviado. **Confira:** "…: agora 1, eram 3" e o botão **Visto**.
- [ ] **K4.4** O balcão transfere um item para outra comanda (B5.2). **Confira:** "Era a comanda …" no card.
- [ ] ★ **K4.5** O cliente cancela um pedido (Folha 1, C7.4). **Confira:** itens riscados e "Pedido cancelado às …. Não preparar."; o card fica até alguém dar ciência.

### K5. Saída e Painel de retirada

- [ ] ★ **K5.1** Abrir o **Painel de retirada** (`/pickup`) no monitor público. **Confira:** "Retirada no balcão", colunas **Em preparo** e **Pronto para retirar**, só números (nenhum nome de cliente).
- [ ] ★ **K5.2** Quando uma estação começa o preparo, **Confira:** o número entra em "Em preparo" em até 10 s.
- [ ] ★ **K5.3** Quando todas as estações marcam Pronto, **Confira:** o número passa a "Pronto para retirar".
- [ ] ★ **K5.4** O gerente entrega o pedido pela **Saída** no Gestor (Folha 4, G2). **Confira:** o número sai do painel.

### K6. Cozinha sem conexão

- [ ] **K6.1** Desligar o Wi-Fi de um tablet. **Confira:** "Sem conexão" ao lado do título, a fila continua na tela com a hora da última leitura.
- [ ] **K6.2** Tentar marcar Pronto. **Confira:** aviso de falha ("… Tente de novo.") e o card volta ao estado anterior. Nada some.
- [ ] **K6.3** Religar. **Confira:** "Ao vivo" volta e os pedidos que chegaram na queda aparecem.

---

## Folha 4 · Gerente (Gestor e Admin)

Quem faz: o gerente, no PC ou tablet do escritório, com o **Gestor de pedidos**
(`gestor.`), o **Admin** (`/admin/`) e o PDV para o fim do dia.

### G1. Fila e aceite

- [ ] ★ **G1.1** Abrir o Gestor e entrar. Tocar uma vez na tela. **Confira:** o selo diz "Som de pedido novo ativo" (não "Som bloqueado: toque para ativar").
- [ ] ★ **G1.2** Quando o pedido do cliente chegar (Folha 1, C4.5), **Confira** em até 5 s: o card com "Novo", o som, e o relógio "aceita sozinho em M:SS" (ou "cancela sozinho em", conforme o canal).
- [ ] ★ **G1.3** Abrir o pedido e tocar em **Aceitar**. **Confira:** o status vira "Aceito" e o cliente passa a ver o Pix (Folha 1, C5.1).
- [ ] **G1.4** Deixar um segundo pedido sem tocar até o relógio zerar. **Confira:** ele se aceita sozinho (ou se cancela, se o canal for assim) e aparece em "O sistema fez".
- [ ] **G1.5** Num terceiro pedido, tocar em **Recusar**, escrever o motivo e **Recusar pedido**. **Confira:** o cliente recebe o aviso com o motivo.
- [ ] ★ **G1.6** **Confira:** o chip de pagamento diz "Pix · Pago" depois do Pix do cliente, e **nunca** "Pagamento simulado, sem dinheiro" no dia D.
- [ ] **G1.7** No pedido, em **Nota para a cozinha**, escrever e salvar. **Confira:** a nota aparece no card da Cozinha.

### G2. Saída: retirada e entrega

- [ ] ★ **G2.1** Ir em **Saída**. Quando a cozinha marcar Pronto (Folha 3, K3.2), **Confira:** o pedido aparece pronto, com o chip de cada estação.
- [ ] ★ **G2.2** Pedido de retirada: o cliente chega, tocar em **Marcar como retirado**. **Confira:** o número sai do Painel de retirada (Folha 3, K5.4) e a NFC-e sai ("NFC-e sai na retirada" vira "NFC-e autorizada").
- [ ] ★ **G2.3** Pedido de entrega: depois de Pronto, **Confira** que a DANFE imprimiu sozinha na impressora da saída ("DANFE impressa" no card). Imprimir a **Via Pedido** e grampear na sacola.
- [ ] ★ **G2.4** Tocar em **Marcar saída para entrega** (ou **Saiu com a maquininha**) e, na volta, **Marcar como entregue**. **Confira:** o cliente vê "Saiu para entrega" e depois "Entregue".
- [ ] **G2.5** Entrega por parceiro (se ligada): **Cotar entrega** e **Chamar entregador**. **Confira:** a corrida aparece no pedido; **Solicitar cancelamento da corrida** cancela.
- [ ] **G2.6** Entrega paga na entrega: na volta, em **Acerto da entrega**, informar o **Valor recebido** e **Confirmar acerto**.

### G3. Pedido iFood

- [ ] ★ **G3.1** Mandar um **pedido de teste** pelo portal do iFood. **Confira** em até 1 min: o card na fila com o ícone do iFood e o aviso "Pedido de teste do iFood: avance as etapas normalmente, mas não produza nem entregue nada".
- [ ] ★ **G3.2** **Aceitar** e avançar até o fim. **Confira** no portal do iFood que cada etapa chegou lá.
- [ ] **G3.3** Num segundo pedido de teste, **Recusar**. **Confira:** os motivos vêm do iFood ("Escolha o motivo que o iFood exige…") e o portal mostra o pedido cancelado.
- [ ] **G3.4** Em **Canais**, conferir "A loja no iFood": aberta no horário.
- [ ] **G3.5** Se o iFood abrir uma negociação, **Confira:** "Negociações iFood" com **Aceitar solicitação** e **Recusar solicitação**; **Enviar resposta ao iFood** responde.

### G4. Cancelamento e estorno

No Gestor não existe botão "Estornar": **cancelar um pedido pago estorna sozinho** no mesmo
meio (Pix volta pela Efí, cartão pelo Stripe) e cancela a NFC-e se ela tiver menos de 30 min
e a mercadoria não tiver saído.

- [ ] ★ **G4.1** Num pedido **sem pagamento**, **Mais ações do pedido › Cancelar pedido**, motivo, **Confirmar**. **Confira:** "Cancelado", a cozinha recebe o aviso (Folha 3, K4.5), o cliente recebe o motivo.
- [ ] ★ **G4.2** Num pedido **pago com Pix**, **Cancelar pedido (pede gerente)**. **Confira:** "Esta ação precisa da autorização de um gerente."; depois do PIN, o pagamento passa a "Reembolsado" em alguns minutos.
- [ ] ★ **G4.3** O mesmo com um pedido **pago no cartão**. **Confira:** "Reembolsado".
- [ ] ★ **G4.4** Se a NFC-e já estava autorizada, **Confira:** a pílula vira "NFC-e cancelada". Se aparecer "O cancelamento da NFC-e do pedido … falhou", é ✗ que trava (a nota continua valendo).
- [ ] **G4.5** Venda do balcão em dinheiro cancelada: no PDV, **Devolver dinheiro de venda cancelada** com o caixa aberto. **Confira:** a gaveta abre e o movimento entra no caixa.
- [ ] **G4.6** No Admin, **Auditoria › Cobranças**, buscar o pedido. **Confira:** a transação de estorno está lá, com o ID do gateway.

### G5. Fim do dia

- [ ] ★ **G5.1** No PDV, **Fim do dia**. **Confira:** os passos "Fechar caixa", "Contar a vitrine", "Fechar o dia". Sem permissão aparece "Fechamento é do gerente".
- [ ] ★ **G5.2** Em "Quanto tem na gaveta?", contar e **Confirmar**. **Confira:** o valor esperado não aparece (contagem cega).
- [ ] ★ **G5.3** Em "O que sobrou na vitrine?", informar as sobras. **Confira:** cada item diz "Fica", "Parte vence" ou "Vira perda".
- [ ] ★ **G5.4** **Fechar o dia**. **Confira:** "Dia fechado"; **Ver relatório de caixa** abre a Leitura Z com "Vendas por método" e "Vendas sem conexão com ajuste".
- [ ] ★ **G5.5** No Admin, **Auditoria › Turnos de caixa**: **Confira** a diferença do turno e se ficou dentro da tolerância.
- [ ] **G5.6** **Auditoria › Fechamentos do dia**: **Confira** que o dia fechado está lá.

### G6. Admin no dia D

- [ ] ★ **G6.1** **A loja › Horários e operação**: horário de hoje certo (a loja abre e fecha pelo horário; não há chave manual).
- [ ] ★ **G6.2** **A loja › Loja e contato**: CNPJ certo (é o emitente da NFC-e).
- [ ] ★ **G6.3** **Diagnóstico**: Focus NFe, Efí, Stripe e iFood prontos, sem aviso de ambiente de teste.
- [ ] ★ **G6.4** **Auditoria › Ações pendentes**: **Confira** que a fila não cresce. Ações que não saem significam o processador parado ([directive-worker-parado](directive-worker-parado.md)).
- [ ] ★ **G6.5** **Alertas do operador**: nada vermelho sem dono.
- [ ] **G6.6** **Quem entra › Verificação em duas etapas**: gerente e dono com a verificação ligada.
- [ ] **G6.7** **Impressão › Agentes de impressão**: o agente do balcão visto há menos de 1 min.

---

## Folha 5 · Periféricos: impressão, gaveta, som e tablets

Quem faz: o gerente com o operador do balcão. No ensaio geral, faça esta folha **antes**
das outras: sem impressora e gaveta, o resto tropeça.

### P1. As três vias do pedido

Não existe "via do entregador": é a Via Pedido com o nome do cliente escondido. A DANFE é
um papel à parte.

| Via | Para quem | Onde sai | Como testar |
|---|---|---|---|
| **Via Recibo** | quem pagou | impressora do balcão | botão **Via Recibo** em "Venda concluída" |
| **Via Pedido** | viaja com a sacola (encomenda e entrega) | impressora do balcão | **Imprimir Via Pedido** na encomenda |
| **Via Cozinha** | estação sem tela (Lanches) | impressora da estação | sai sozinha quando o pedido chega à estação |

- [ ] ★ **P1.1** No PC do balcão, rodar o teste do agente (`counter_agent.py --test-print`; quem instalou o agente sabe onde). **Confira:** sai "TESTE DE IMPRESSAO" com corte.
- [ ] ★ **P1.2** **Via Recibo**: fazer uma venda e tocar em **Via Recibo**. **Confira:** itens, total, forma de pagamento e troco legíveis; corte certo; nenhum texto cortado na largura do rolo.
- [ ] ★ **P1.3** **Via Pedido** de uma encomenda: em **Encomendas**, abrir uma e tocar em **Imprimir Via Pedido**. **Confira:** aviso "Via Pedido de … na bobina." e o papel tem código, data e itens.
- [ ] ★ **P1.4** **Via Pedido** de um pedido de teste do iFood. **Confira:** no lugar do nome, "iFood" com o localizador; **nenhum** telefone ou endereço do cliente; "NÃO É DOCUMENTO FISCAL" em destaque.
- [ ] **P1.5** Pedido marcado como presente. **Confira:** a via sai sem valores.
- [ ] ★ **P1.6** **Via Cozinha**: lançar um lanche e **Enviar à cozinha**. **Confira:** a impressora da Lanches imprime o ticket com o QR `KT-…` em até 10 s.
- [ ] ★ **P1.7** Bipar o QR da Via Cozinha no leitor do balcão. **Confira:** aviso "Lanches pronto · …" e o pedido anda no Gestor. Imprimir **não** dá baixa; só o leitor ou o **Marcar pronto** do Gestor.
- [ ] **P1.8** Tirar o lanche da comanda (**Cancelar envio à cozinha**). **Confira:** a impressora da Lanches imprime "CANCELADO" com o item.
- [ ] **P1.9** Reimprimir uma via. **Confira:** o papel diz "REIMPRESSÃO".
- [ ] ★ **P1.10** **DANFE**: numa venda com CPF na nota, **Imprimir DANFE**. **Confira:** o QR Code da nota abre a consulta da SEFAZ no celular.
- [ ] ★ **P1.11** Desligar a impressora do balcão e fazer uma venda. **Confira:** aviso "A impressora do balcão não respondeu…" e o recibo abre pela impressão do navegador. Religar.

### P2. Gaveta

- [ ] ★ **P2.1** Venda em dinheiro no PC do balcão. **Confira:** a gaveta abre sozinha. Se não abrir, conferir no Admin (**Equipamentos › Terminais do PDV**) se a abertura na venda em dinheiro está ligada.
- [ ] ★ **P2.2** Deixar a gaveta aberta e tentar a próxima venda. **Confira:** "Gaveta aberta" trava o PDV; fechar a gaveta libera sem PIN.
- [ ] **P2.3** Deixar aberta 3 min. **Confira:** o gerente recebe o alerta de gaveta esquecida.
- [ ] **P2.4** Em **Caixa**, **Abrir gaveta** com o motivo "Abrir para testar". **Confira:** abre e fica registrado.
- [ ] **P2.5** Venda em dinheiro no **tablet** do balcão. **Confira:** a gaveta **não** abre; aparece "Dinheiro da comanda … leve ao Balcão" com **Abrir gaveta do Balcão**.
- [ ] **P2.6** Desconectar o sensor da gaveta. **Confira:** aviso "O sensor da gaveta parou de responder. O gerente foi avisado." Reconectar.

### P3. Som

- [ ] ★ **P3.1** Em cada tablet da cozinha: volume no máximo, modo silencioso desligado, nenhum fone pareado por Bluetooth.
- [ ] ★ **P3.2** Pedido novo com a cozinha em movimento (forno, café, exaustor). **Confira:** quem está na bancada ouve a fanfarra na primeira vez.
- [ ] ★ **P3.3** Mudança no pedido (Folha 3, K4.1). **Confira:** o som de mudança é diferente da fanfarra e dá para distinguir de longe.
- [ ] ★ **P3.4** Gestor: o pedido novo da loja toca no PC do gerente; **Visto** para o som.
- [ ] **P3.5** Recarregar a página da Cozinha e não tocar em nada. **Confira:** aparece "O navegador bloqueou o som desta estação" com **Ativar o som**. É o esperado: o navegador exige um toque. Toda manhã, alguém toca na tela de cada tablet.

### P4. Tablets e dispositivos

- [ ] ★ **P4.1** Cada tablet com o app instalado na tela inicial (abre em tela cheia, sem a barra do navegador).
- [ ] ★ **P4.2** Deixar 10 min parado com a fila aberta. **Confira:** a tela continua acesa. Se apagar, ajustar o bloqueio automático do tablet para "nunca" durante o expediente.
- [ ] ★ **P4.3** Carregador ligado em cada tablet fixo; bateria acima de 80% no início.
- [ ] **P4.4** Vincular cada dispositivo ao seu posto: "Vincular este dispositivo a um posto de trabalho?" › **Vincular a este posto**. **Confira:** depois de fechar e abrir o app, ele pede só o PIN.
- [ ] **P4.5** Monitores da **Tela do cliente** e do **Painel de retirada**: legíveis a 3 m, sem nome de cliente.
- [ ] **P4.6** Maquininha: no dia D, uma cobrança real de R$ 1,00 e o estorno na própria maquininha (junto do canário).

---

## Folha 6 · Canário de um (dia D)

Quem faz: **o dono compra**, como cliente, com o próprio cartão e o próprio banco. O
**gerente confere** no Gestor e no Admin. Um **observador** anota cada número na tabela de
evidência. Acontece depois do deploy da virada e antes de abrir a loja.

**Regra de parada.** Parou de bater, parou o canário: pagamento duplicado, pedido pago que
não anda, estorno que não aparece no gateway, nota que não aparece na Focus, ou qualquer
estado "não sabemos" (efeito desconhecido). Anote, não repita a compra, e siga
[pagamento-divergente](pagamento-divergente.md) ou
[pedido-pago-sem-confirmacao](pedido-pago-sem-confirmacao.md). Resultado: **NO-GO** até
entender.

**Cada passo com dinheiro ou nota tem autorização própria** (cutover §4): antes de cada
um, o dono diz "pode" em voz alta e o observador anota a hora.

### Antes do canário

- [ ] **N0.1** Deploy da virada `ACTIVE`; `/ready/` ok; Admin **Diagnóstico** sem aviso de ambiente de teste (Folha 4, G6.3).
- [ ] **N0.2** Na loja, **nenhum** selo "Ambiente de teste" no login e no pagamento (Folha 1, C3.5 e C6.9).
- [ ] **N0.3** Gerente com o Gestor aberto e o som ativo; cozinha com uma estação ligada.
- [ ] **N0.4** Painéis abertos em outra aba, com login: **Efí** (Pix › cobranças), **Stripe** (modo **live**, Pagamentos) e **Focus NFe** (produção, NFC-e).

### Canário 1 · Pix real (retirada)

- [ ] **N1.1** Na loja, montar uma sacola pequena (um item barato), **Retirada**, horário mais cedo, **Pix**. Em "CPF ou CNPJ na nota?", informar o CPF do dono. **Enviar pedido**. Anote o código.
- [ ] **N1.2** Gerente: **Aceitar** no Gestor. **Confira:** a loja mostra o QR em segundos.
- [ ] **N1.3** Dono paga no app do banco. **Confira** sem recarregar: etapa "Pago" na loja; "Pix · Pago" no Gestor; WhatsApp de confirmação.
- [ ] **N1.4** **Confira na Efí:** uma cobrança só, valor certo, status concluída. O txid da Efí é igual ao **ID do gateway** em Admin › **Auditoria › Cobranças** (buscar pelo pedido). Anote o txid.
- [ ] **N1.5** Cozinha marca **Pronto**; gerente **Marcar como retirado**. **Confira:** pílula "NFC-e autorizada" no Gestor; link da nota no WhatsApp.
- [ ] **N1.6** **Confira na Focus:** a NFC-e com a referência igual ao código do pedido, status autorizada, valor certo, CPF do dono. Anote chave e protocolo.
- [ ] **N1.7** Abrir o QR da DANFE no celular. **Confira:** a consulta da SEFAZ-PR mostra a nota.

### Canário 2 · Cartão real (retirada)

- [ ] **N2.1** Novo pedido, **Retirada**, **Cartão**, CPF na nota. **Enviar pedido** e **Pagar com cartão**. **Confira:** a página do Stripe abre em modo real (sem faixa de teste). Pagar.
- [ ] **N2.2** **Confira** na loja: "Pagamento autorizado". Gerente: **Aceitar**.
- [ ] ★ **N2.3** **Confira no Stripe:** o pagamento `pi_…` está **capturado** ("Succeeded"), não só autorizado ("Uncaptured"). Autorizado e não capturado é ✗ que trava: o cliente não foi cobrado. Anote o `pi_…` e confira que é o **ID do gateway** em **Auditoria › Cobranças**.
- [ ] **N2.4** Cozinha **Pronto**; gerente **Marcar como retirado**. **Confira:** "NFC-e autorizada" no Gestor e na Focus (anote chave e protocolo).

### Canário 3 · Balcão real

- [ ] **N3.1** No PDV, venda de um item em **dinheiro** com **CPF na nota** (tecla F). **Confira:** a gaveta abre, sai a Via Recibo, "NFC-e autorizada" na tela; a nota na Focus.
- [ ] **N3.2** Venda de R$ 1,00 na **maquininha** (débito). **Confira:** a maquininha aprova; "Venda concluída"; a venda aparece em **Leitura X** como débito.

### Canário 4 · Estorno

Dentro de 30 min da nota do Canário 2 (depois disso a NFC-e não cancela; vira nota de
estorno, que é outro caminho).

- [ ] **N4.1** Gerente: no pedido do Canário 2, **Cancelar pedido (pede gerente)**, motivo "Canário: estorno de teste", PIN do gerente. **Confira:** "Cancelado".
- [ ] **N4.2** **Confira** em até 5 min: pagamento "Reembolsado" no Gestor.
- [ ] **N4.3** **Confira no Stripe:** um reembolso `re_…` do valor inteiro no `pi_…` do Canário 2. Um só. Anote.
- [ ] **N4.4** **Confira na Focus:** a NFC-e do Canário 2 com status cancelada; no Gestor, "NFC-e cancelada".
- [ ] **N4.5** **Confira** no cartão do dono (app do banco): a cobrança e o estorno, nos dias seguintes.
- [ ] **N4.6** (Se autorizado) Estorno de um Pix: cancelar o pedido do Canário 1 **antes** de marcar retirado em outro canário, ou repetir K1 até K1.4 e cancelar. **Confira na Efí:** a devolução no mesmo Pix (`e2eid`), valor inteiro, uma só.
- [ ] **N4.7** Maquininha: estornar a venda do Canário 3 na própria maquininha e, no PDV, registrar em "Estornos na maquininha".

### Evidência do canário

| Canário | Hora | Pedido | Gateway (txid / `pi_` / `re_`) | NFC-e (chave e protocolo) | Bateu? |
|---|---|---|---|---|---|
| 1 Pix | | | | | |
| 2 Cartão | | | | | |
| 3 Balcão dinheiro | | | dinheiro | | |
| 3 Maquininha | | | NSU: | | |
| 4 Estorno cartão | | | | cancelada: | |
| 4 Estorno Pix | | | | | |

Sem dados de cartão nesta tabela: só os códigos do gateway. **Decisão:** GO limitado
(abrir a loja) ou NO-GO ([rollback](rollback-de-deploy.md)). Assinatura do dono: ____________

---

## Folha de anotação

| Hora | Dispositivo | Folha e passo | O que tocou | O que apareceu (palavra por palavra) | Pedido ou comanda | Travou? |
|---|---|---|---|---|---|---|
| | | | | | | |
| | | | | | | |
| | | | | | | |
| | | | | | | |
| | | | | | | |
| | | | | | | |

**Assinaturas da rodada** · Data: ________ · Rodada: ensaio / dia D ·
Gerente: ____________ · Observador: ____________ · Resultado: GO / NO-GO
