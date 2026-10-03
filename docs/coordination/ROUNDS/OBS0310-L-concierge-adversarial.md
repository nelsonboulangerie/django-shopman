# OBS0310-L: Concierge, rodada adversarial (estudo, rodada 2)

- **id:** OBS0310-L
- **sessão:** shopman-improvements-fixes-bd04d4 (Claude; subagente em worktree próprio)
- **branch:** claude/obs0310-concierge-arquitetura-v2
- **início (UTC):** 2026-10-03
- **tipo:** análise e proposta; nenhum código de produção
- **base:** rodada 1, OBS0310-J (PR #1435, `docs/plans/CONCIERGE-ARQUITETURA-ALVO.md`)

## Pedido do dono (03/10)
Memória da conversa (cerca de 20% das mensagens), perguntas com várias intenções, nova
rodada adversarial à proposta, pesquisa mais funda (Deeliv a fundo, testar um fluxo real),
"concierge absolutamente confiável", mecanismo simples, robusto e elegante.

## Enquadramento do dono (03/10, via coordenador), espinha dorsal do V2
Confiável = nunca afirmar algo falso; "não sei, vou verificar" como caminho de primeira classe;
pilares: intenções no plural e memória; mais um esquema rígido de regras da casa. O V2 foi
reorganizado nesses quatro blocos (seções 5 a 8), cada um com contrato e meta no placar da
OBS0310-K (#1437, 209 mensagens reais).

## Entrega
- `docs/plans/CONCIERGE-ARQUITETURA-ALVO-V2.md`: ataque à rodada 1 e às hipóteses do
  coordenador, dados reais medidos, pesquisa (Deeliv, Ailo, Anota AI, ManyChat, Meta,
  Rasa CALM e outros), arquitetura v2, contratos (estado, atos, verificador), custo,
  latência, fatias revisadas e decisões do dono.
- `docs/plans/concierge-teste-deeliv.md`: roteiro de teste com mensagens exatas. Nada foi
  enviado; o envio é do coordenador, com autorização do dono.

Arquivo V2 separado (e não edição do v1) porque o #1435 ainda não estava no `main` quando
esta frente começou (um check vermelho alheio a ele, "Marketing, cadeia completa"); assim
este PR não depende da fila do outro. Quando os dois estiverem no `main`, o v1 fica como
histórico e o V2 é o vigente (o V2 diz isso no topo).

## Medições (alpha, conexão direta 25060, banco `shopman`, transação somente leitura)
- 224 entradas no total; 168 da observação passiva (26/09 a 03/10, 84 conversas).
- 39 das 168 (23%) só se entendem com contexto. De onde vem o contexto: bolha anterior do
  próprio cliente (10), resposta da equipe que o sistema não viu (11), pedido de outro dia
  ou de outro canal (10), cobrança por demora (4), referente invisível (story, foto) (4).
- Rajadas: 21 das 168 chegaram até 60 s depois da anterior; nenhuma em até 30 s; 18
  rajadas em 35 conversas com mais de uma mensagem.
- Várias intenções numa bolha só (duas ações que não são cortesia): cerca de 3% na
  observação; na conversa de teste do dono com o bot respondendo, 6 de cerca de 25.
  Espalhadas em várias bolhas da mesma rajada: cerca de 10 rajadas.

## Fontes externas
Três subagentes de pesquisa (Deeliv e plataformas brasileiras; fornecedores e literatura;
Anota AI, Ailo, ManyChat, Meta). Links no documento. Cobrança da Meta por mensagem de
serviço a partir de 01/10/2026 conferida na página oficial.

## Estado
PR de documentação (#1438). Decisões do dono na seção 13 do V2.
