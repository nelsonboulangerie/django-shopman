# Watchman: credenciais, certificados e outros vencimentos

O sistema não considera uma integração saudável só porque ela funciona hoje.
Todo recurso externo cuja expiração possa interromper uma capacidade entra no
inventário do Watchman sem que seu valor secreto seja lido, salvo ou registrado.

## Contrato acionável

Cada item declara:

- data-limite de vencimento ou de rotação;
- responsável;
- capacidade que para;
- ação exata de renovação;
- runbook;
- prova que precisa ficar verde antes de revogar o item anterior.

O relatório JSON inclui esses campos e nunca inclui o token, certificado, senha
ou chave privada. Metadado ausente é `unknown`, nunca falso verde.

## Régua

O padrão reaproveitável é:

| Distância | Estado | Resposta |
|---|---|---|
| mais de 60 dias | `pass` | nenhuma ação |
| 60 a 15 dias | `warn` | aviso acionável pelo Sentry; job continua verde |
| 14 dias até vencido | `fail` | aviso crítico e job vermelho |
| vencido | `fail` | incidente; restaurar capacidade e provar |

Um deployment pode escolher limites mais conservadores por recurso. O alerta
leva nome, impacto, responsável, ação, runbook e verificação. A repetição e a
resolução pertencem ao workflow de alertas do Sentry.

## Rotação sem interrupção

Para tokens que aceitam sobreposição:

1. criar o substituto com o menor escopo possível;
2. guardar o novo valor no secret do consumidor;
3. atualizar a data pública de expiração;
4. executar a prova indicada pelo inventário;
5. observar uma execução saudável;
6. só então revogar o anterior;
7. executar a prova novamente.

O Watchman nunca renova credenciais sozinho. Renovar pode criar autoridade e
invalidar consumidores; sua função é antecipar, conduzir e provar a ação.

## DigitalOcean do Watchman

- valor: secret `DIGITALOCEAN_READ_TOKEN` no GitHub;
- vencimento: variable `DIGITALOCEAN_READ_TOKEN_EXPIRES_AT` (`AAAA-MM-DD`);
- escopos: leitura de App Platform e Managed Databases, mais dependências de
  leitura exigidas pela DigitalOcean;
- prova: workflow **Watchman Infrastructure**, com todos os checks verdes;
- impacto: sem ele, drift e contrato de infraestrutura deixam de ser conferidos.

O token deve ter um ano de validade. A antecedência de 60 dias dá tempo para
rodar a sobreposição sem depender da memória de uma pessoa.

## Credenciais existentes da DigitalOcean

O inventário inicial também cobre os consumidores que já mantêm a entrega viva:

| Recurso | Metadado público | Prova mínima |
|---|---|---|
| imagens e leitura do app | `DIGITALOCEAN_ACCESS_TOKEN_EXPIRES_AT` | `deploy-images` e `alpha-smoke` |
| promoção do App Platform | `DIGITALOCEAN_APP_DEPLOY_TOKEN_EXPIRES_AT` | deploy completo e saudável |
| operações administrativas | `DIGITALOCEAN_APP_ADMIN_TOKEN_EXPIRES_AT` | prova de cada consumidor identificado |

O token administrativo exige inventariar seus consumidores durante a próxima
rotação. Esse trabalho deve reduzir o privilégio e separar responsabilidades;
não se copia automaticamente o escopo amplo para a nova credencial.

O token de leitura do Sentry não informa vencimento, então recebe uma política
explícita de rotação anual em `SENTRY_AUTH_TOKEN_ROTATE_BY`. O Watchman trata a
data do mesmo modo: troca sobreposta, prova de `external_monitoring=pass` e só
depois revogação do anterior.

## Certificados locais

Os certificados da Efí e o e-CNPJ A1 de Compras já têm a validade extraída do
próprio X.509 pelo runtime. O ciclo `check_integration_drift`, executado pelo
`maintenance_worker`, transforma os marcos em `OperatorAlert` com consequência
e ação de renovação. Nenhum byte do certificado entra no alerta.

Novos recursos com vencimento entram primeiro neste inventário. Não se cria um
lembrete isolado em agenda, comentário de código ou memória humana.
