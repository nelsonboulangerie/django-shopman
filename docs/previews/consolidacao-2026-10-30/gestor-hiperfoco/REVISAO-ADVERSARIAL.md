# Revisão adversarial da rodada 2 (Gestor por posto)

31/10/2026, pedida pelo dono. Régua: as leis L1 a L7 (SUITE-UX-FUNCTION-PLAN §2), a
forma FILA (§4.1), o teste de uma frase e os defeitos D1 a D8 (`omotenashi-copy.md`), as
três leis do vocabulário (`suite-vocabulary.md` §0) e o checklist de design D1 a D12.
Alvo: `posto.vue` e as capturas `posto-*.png`. Cada achado foi conferido no código.

## A. A tela mente ou esconde perigo

1. **Sem conexão, a tela diz que está tudo calmo.** A página não mostra conexão, leitura
   atrasada nem som bloqueado (nenhum uso de `realtime`/`soundBlocked`). Sem rede, o caixa
   lê "Nada pede você agora." sobre dados velhos. Contraria a regra comum 5 (conexão é
   estado real) e é o D1 do catálogo (rótulo que mente).
2. **"Nada pede você agora." aparece também enquanto carrega** (`posto.vue:146`, a lista
   está vazia antes da primeira leitura).
3. **Ação que falha não diz nada.** `actionError` não é lido: um Aceitar que não chega ao
   servidor some em silêncio. Contraria "erros explícitos" e a frase aprovada "<REF>
   continua novo: o Aceitar não chegou. Tente de novo.".
4. **Botões que não fazem o que dizem.** "Saiu D10" leva ao quadro (`:67`); "Recusar" e
   "Receber R$ 39,00" só abrem o pedido. O rótulo promete o ato e entrega uma navegação.
5. **"Já pagou, entregar" não registra a resposta.** O pedido conclui e o pagamento segue
   "não informado"; ninguém sabe depois quem conferiu nem quando. A pergunta dá sensação de
   controle sem deixar rastro (L7: o estado é da casa).
6. **"0:38 para cancelar sozinho" admite duas leituras**: "o sistema cancela" ou "você tem
   0:38 para cancelar". A ordem da rodada 1 ("cancela sozinho em 0:38", aprovada) não
   tinha esse problema; a inversão para caber na coluna o criou. O mesmo em "para aceitar
   sozinho". E o topo do caixa diz "cancela em 0:38": duas formas para o mesmo conceito.

## B. O lugar ou o gesto está errado para o momento

7. **No passe, só o primeiro pedido tem gesto.** Quem chega ao balcão não segue a ordem
   da fila: se é a Diego (A05) e o destaque é D10, as linhas de "Depois" não têm botão nem
   abrem nada. Falta LOCALIZAR (busca e leitor da Via Pedido), gesto transversal que a
   prévia tirou do passe e do caixa (o caixa também atende telefone).
8. **A entrega ignora a TaOn.** Não existe entregador da casa: a TaOn despacha sozinha
   quando coleta (evento E). O "Saiu" manual é quase sempre redundante (L1), e o que o
   passe precisa ver é a corrida: chamada? a caminho? chegou? Sem corrida, o gesto é
   "Chamar entregador", que o destaque não oferece.
9. **"Saiu" no caixa.** O caixa no computador não vê o entregador na porta; o fato é do
   passe (L1: o botão é o fato que só aquele humano vê).
10. **Três anatomias para o mesmo pedido.** O caixa tem o relógio à esquerda, o gerente
    no alto, e o destaque do passe não tem relógio (nem "pronto há 14 min"). A forma FILA
    varia a densidade por dispositivo, não a anatomia do item (L2).
11. **O gerente não tem o interruptor.** "Canais" leva a Ajustes; a função do celular do
    gerente (§10.4) é desligar o canal num toque quando a cozinha satura. E "recebendo" é
    palavra nova para o que o quadro chama de "ligado" (lei 1 do vocabulário).
12. **"4 na cozinha" conta o que não passa pela cozinha** (o próprio achado 8 da rodada 1,
    reintroduzido na frase do gerente).
13. **Prioridade do aviso vermelho.** A rodada 1 seguia a regra do quadro ("vermelho é só
    o bloqueio com motivo"); a prévia pinta o prazo de perda de vermelho. É provável que
    seja o certo, mas muda uma regra escrita: decisão do dono, não da prévia.

## C. Acabamento (D1 a D12 do checklist)

14. Cortes: "Saiu para entr…", "Entregador a 5 min do c…" (D12; status que muda o gesto
    não se corta).
15. A faixa vermelha do passe tem o "Aceitar" escuro; ação dentro de aviso acompanha a cor
    do aviso (D8).
16. "text-6xl" escrito à mão no código do destaque, fora da tipografia nomeada do kit
    (`op-figure`; D11).
17. O subtítulo do caixa "o que pode ser perdido vem primeiro" é nota de rodapé do
    engenheiro (D6 do catálogo de copy); e a contagem aparece duas vezes (topo e rodapé).
18. A página não tem cabeçalho: sem título acessível, sem busca, sem Avisos. As decisões
    de 30/10 (Avisos como botão próprio, cabeçalho claro) não chegaram aqui.
19. Na prévia, o posto se escolhe por botão. No produto, o posto vem do vínculo do
    dispositivo (Ajustes › Postos), o contrato de chrome da §3.3.

## O que resiste à revisão

- Abrir pelo posto, com a mesma fonte de dados: é o que a L6 pede.
- O destaque do próximo a sair, com sacolas, troco a levar e um gesto.
- A volta do entregador com o valor já somado.
- O Pix pendente fora de "Precisa de você".
