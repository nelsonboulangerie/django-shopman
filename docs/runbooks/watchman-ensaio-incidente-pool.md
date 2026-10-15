# Ensaio geral do incidente de pool de 14/10

> **Estado:** preparado, ainda não executado. Este roteiro produz carga deliberada
> no ambiente pré-go-live e só começa depois da palavra do dono. Não altera spec,
> banco, configuração ou painel. “Alpha” aqui significa o ambiente pré-go-live nos
> hosts canônicos `*.boulangerie.com.br`; a URL antiga não faz parte do ensaio.

## Objetivo e critério

Reproduzir pelo navegador o padrão causal de 14/10 (streams SSE abertos e
abortados em ondas) e provar que o `web-operator` permanece saudável ou se recupera
sozinho em **menos de 120 segundos**, sem intervenção durante a janela medida.

O relógio começa no primeiro aborto da última onda (`T0`) e termina no primeiro
instante (`T1`) em que as três condições abaixo valem por três amostras consecutivas:

1. `/health/live/` responde 200;
2. `/health/database/` responde 200;
3. uma rota real do operador responde sem `PoolTimeout`.

Aceite: `T1 - T0 < 120 s`, zero intervenção humana entre T0 e T1, zero erro de
integridade e nenhuma degradação persistente depois da prova. O relatório registra
tempos observados, não arredondados.

## Limite de autoridade

- O dono diz **“pode executar o ensaio do pool”** antes do passo 1.
- Ninguém edita o spec, reinicia componente, muda env ou executa SQL durante a
  janela. Se isso for necessário, a medição é inválida.
- A preparação e a reversão usam apenas o navegador e o painel da DigitalOcean.
- Não rodar durante deploy, venda de ensaio, demonstração ou outra prova do dono.
- Não usar credencial em arquivo, comando, captura ou log. O navegador autenticado
  mantém a sessão; o roteiro não copia cookies.

## Pessoas e relógios

| Papel | Responsabilidade |
|---|---|
| Dono | autoriza início e, se necessário, autoriza a reversão no painel |
| Condutor | executa a carga no navegador e marca T0/T1 em UTC |
| Observador | acompanha saúde, deployment e logs sem alterar nada |

Sincronizar os relógios dos dois observadores antes de começar. Registrar o commit
e o deployment ativos; a prova só vale para a versão que contém #1778, #1779,
#1782, #1788 e #1807.

## Pré-voo (todos obrigatórios)

1. Confirmar no painel que não há deployment em andamento.
2. Confirmar três respostas 200, separadas por 10 s:
   - `https://api.boulangerie.com.br/health/live/`
   - `https://api.boulangerie.com.br/health/database/`
   - `https://api.boulangerie.com.br/health/ready/`
3. Confirmar três respostas 200 equivalentes da loja online:
   - `https://api.boulangerie.com.br/api/v1/health/live/`
   - `https://api.boulangerie.com.br/api/v1/health/ready/`
4. Abrir no painel o log de runtime do `web-operator` e a linha do tempo de
   deployments/restarts. Marcar o número de reinícios inicial.
5. Conferir nos 30 minutos anteriores: nenhum `PoolTimeout`, nenhum
   `liveness_pool_stuck_restart` e nenhum deployment.
6. Entrar normalmente em um app de operador. Confirmar que notificações SSE estão
   conectadas e que uma rota real abre sem erro.

Qualquer falha no pré-voo cancela o ensaio; ela é um incidente pré-existente, não
resultado da simulação.

## Passo 1: replay fiel pelo navegador

No DevTools do app autenticado, aba Console, executar o trecho abaixo. Ele usa a
rota same-origin do BFF, abre no máximo oito streams simultâneos (o tamanho do pool
do processo), fecha todos abruptamente e repete dez ondas. Não acessa cookie, não
manda corpo e não grava dado.

```javascript
const watchmanDrill = async ({ width = 8, pauseMs = 750 } = {}) => {
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
  const openDurations = [50, 100, 200, 400, 800, 150, 300, 600, 75, 500]
  for (const [index, openMs] of openDurations.entries()) {
    const streams = Array.from({ length: width }, () => new EventSource('/sse/notifications'))
    await wait(openMs)
    streams.forEach((stream) => stream.close())
    console.info(`watchman drill: onda ${index + 1}/${openDurations.length} fechada após ${openMs} ms`)
    await wait(pauseMs)
  }
  console.info('watchman drill: carga encerrada')
}
await watchmanDrill()
```

Se o app aberto não expuser `/sse/notifications`, usar a rota SSE same-origin que
ele já mostra na aba Network; nunca apontar o navegador direto ao Django nem copiar
cookie para outro programa.

O condutor anuncia a última linha “carga encerrada” e marca esse instante como T0.
Depois de T0, não recarrega página, não repete a carga e não tenta “ajudar” a cura.

## Passo 2: observação por até 120 segundos

A cada 5 s, o observador registra em uma planilha simples: UTC, status das duas
sondas do operador, latência da rota real e mudança no deployment. O painel de logs
deve ser filtrado pelos sinais abaixo:

| Sinal | Interpretação |
|---|---|
| `db_connection_orphan_reclaimed count=N` | a correção causal devolveu conexões de threads encerradas |
| `liveness_pool_waiting` | pool não entregou ainda, dentro da histerese |
| `liveness_pool_recovered` | pressão cessou antes do limiar de restart |
| `liveness_pool_stuck_restart` | banco responde fora do pool e a liveness pediu restart |
| `liveness_pool_stuck_but_database_down` | não é o incidente simulado; banco externo falhou e restart foi corretamente recusado |
| `PoolTimeout` | request real atingiu o teto; registrar rota e instante |

Quando as três condições de saúde passarem por três amostras consecutivas, marcar
T1. Não é permitido escolher a primeira amostra isolada.

### Se houver restart

Continuar apenas observando até 120 s. Registrar o instante do primeiro
`liveness_pool_stuck_restart`, o restart no painel e a primeira resposta saudável.
O restart conta como autocura somente se não houve clique ou comando humano.

A configuração versionada atual tem janela de 30 s e três falhas de liveness a
cada 30 s; o runbook de resiliência estima 2–2,5 min no pior alinhamento. Portanto,
um resultado acima de 120 s **reprova** este aceite. Não reduzir limiar nem editar
o spec durante a prova. Um eventual ajuste vira proposta separada ao dono, com o
tempo medido e proteção contra loop quando o banco está fora.

## Passo 3: estabilização e encerramento

Depois de T1:

1. manter as sondas e a rota real sob observação por mais 10 minutos;
2. confirmar que a loja online permaneceu saudável durante toda a prova;
3. confirmar ausência de novo `PoolTimeout` e que não há stream do ensaio aberto;
4. registrar número de `orphan_reclaimed`, se houve restart e o delta T1−T0;
5. guardar apenas logs técnicos sem cookie, URL com parâmetro, IP ou dado pessoal.

## Reversão e parada de emergência

O gesto normal de reversão é fechar a aba que executou o ensaio; todos os
`EventSource` também são fechados pelo próprio script. Não existe dado para desfazer.

Se aos 120 s o operador ainda não estiver saudável:

1. declarar o ensaio **reprovado** e encerrar a carga/aba;
2. preservar T0, respostas e logs antes de qualquer ação;
3. com a palavra do dono, usar o painel da DigitalOcean para reiniciar apenas o
   `web-operator`;
4. conferir `/health/live/`, `/health/database/`, `/health/ready/` e a rota real;
5. não editar spec, env nem banco como “reversão”. Isso seria outra mudança e pede
   diagnóstico próprio.

Parar imediatamente, sem esperar 120 s, se aparecer erro de integridade, se a loja
online degradar, se começar um deployment não relacionado ou se o banco externo
ficar indisponível. A parada não transforma a prova em sucesso.

## Modelo do relatório de aceite

```text
Deployment/commit:
Autorização do dono (UTC):
T0, última onda encerrada (UTC):
T1, terceira amostra saudável (UTC):
Delta T1−T0:
Ondas × streams:
orphan_reclaimed (total):
PoolTimeout depois de T0:
liveness_pool_stuck_restart:
Restart automático:
Loja online permaneceu saudável:
Resultado: APROVADO (<120 s) | REPROVADO
Evidências preservadas:
Observações:
```

## O que este ensaio prova e o que não prova

Ele prova o caminho real navegador → BFF → SSE Django, o cancelamento que causou o
incidente, a devolução de conexões órfãs e, se acionada, a liveness do processo.
Também prova que o `web-storefront` não é arrastado pela carga do operador.

Ele não prova indisponibilidade regional, banco fora, Redis fora ou duas instâncias.
Esses casos têm respostas diferentes de propósito e não devem ser misturados com o
incidente de pool.
