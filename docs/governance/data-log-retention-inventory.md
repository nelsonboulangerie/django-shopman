# Inventário técnico de logs e retenção R12

**Estado:** inventário inicial verificável em 2026-09-14. A barreira de
redação está coberta por testes; prazos dos fornecedores, classificação de
registros persistidos e descarte automatizado continuam pendentes. Este
documento não autoriza exclusão nem comprova conformidade integral.

## Escopo e método

A busca
`rg -l '(?:logger|logging)\.(?:debug|info|warning|error|exception|critical)\(' config shopman packages -g '*.py'`
encontrou **312 arquivos Python** com chamadas de log. O número é um limite
inferior: bibliotecas, middleware e infraestrutura também podem emitir eventos.
O inventário separa logs de processo, telemetria externa e registros de banco;
eles não têm necessariamente a mesma finalidade ou o mesmo prazo.

## Superfícies inventariadas

| Superfície | Conteúdo/risco comprovado | Proteção atual | Prazo e descarte | Estado/ação necessária |
|---|---|---|---|---|
| `stdout/stderr` da aplicação e dos workers | mensagens e contexto adicional; chamadas existentes incluem referências a cliente, assinante, sessão, endereço, documento e coordenadas | handlers de logging próprios usam `JsonLogFormatter` ou `PrivacySafeFormatter`; Console/LogSender de teste não exibem mais OTP ou destino | a aplicação não controla o prazo do coletor da infraestrutura; saída direta de comandos não recebe formatter automaticamente | **Parcial:** confirmar no provedor o destino, acesso e TTL máximo de 180 dias; auditar comandos e não registrar payload bruto na origem |
| Sentry, somente quando `SENTRY_DSN` existe | exceção, rota e contexto de integrações | `send_default_pii=False`, corpo de requisição desativado e `before_send` remove usuário, query/fragmento, cabeçalhos não autorizados, PII e segredos | configuração de retenção da organização não está versionada neste repositório | **Parcial:** registrar owner, região/subprocessador e TTL de até 180 dias; provar a configuração fora do código |
| `django_admin_log` (`LogEntry`) | ator, objeto e texto de alteração administrativa | acesso pelo Admin e banco transacional; não passa pelo formatter de logs | sem descarte R12 comprovado | **Pendente de classificação:** separar prova administrativa ligada a R01/R03/R14 de mensagem pessoal descartável; só então definir contração |
| `backstage.SignInEvent` | trilha de autenticação e anomalia, potencialmente com identificadores técnicos/pessoais | modelo de segurança dedicado e acesso administrativo | rotina existente considera janela de 180 dias | **Parcial:** comprovar execução, alerta e legal hold; não misturar incidente R02 com log rotineiro R12 |
| `backstage.OperatorAlert` | alerta operacional, ator, referência e metadados variáveis | banco transacional e UI operacional | sem classe de retenção geral comprovada | **Pendente:** classificar alertas que viraram incidente/prova e redigir ou expurgar os demais em 180 dias |
| `backstage.PrintAgentCredential` | credencial e endereço de agente de impressão; risco de segredo operacional | modelo restrito; segredo não deve sair em log | ciclo de vida próprio, ainda sem vínculo demonstrado com R12 | **Pendente:** auditar campos, rotação e exclusão; segredo não pode depender apenas de redação na saída |
| recibos `DeliveryAttempt`, `DeliveryReconciliation`, `StockAlertDelivery` e `OutboundAttempt` | IDs do provedor, erro/recibo detalhado e possível destino | banco transacional e leitura operacional | pertencem à regra **R06**, com redução do detalhe aos 180 dias | **Fora de R12:** a futura contração R06 deve preservar apenas resultado técnico agregado e respeitar entrega não reconciliada/legal hold |

## Barreira única de saída

`shopman.shop.telemetry_redaction` é a fronteira canônica. Ela trata estruturas
e texto livre e cobre, entre outros, e-mail, telefone, CPF/CNPJ, identificador
de cliente/assinante, sessão, usuário, endereço, geolocalização, token e query
string. Referências técnicas deliberadamente permitidas, como `order_ref`, não
são apagadas por uma regra genérica.

Os testes exercitam tanto JSON de produção quanto o formatter legível usado em
desenvolvimento. A barreira reduz exposição acidental; ela **não** torna correto
registrar corpo, erro bruto ou dado pessoal desnecessário. Hotspots devem ser
corrigidos na origem conforme forem tocados.

### Emissores locais de autenticação

`ConsoleSender` e `LogSender` confirmam apenas que o caminho técnico local foi
alcançado. Eles não registram o código nem o destino e não comprovam entrega ao
usuário. Um fluxo interativo de desenvolvimento só pode depender deles quando a
resposta protegida de debug estiver deliberadamente habilitada; fora disso, a
cadeia precisa de SMS, e-mail ou outro canal real. O startup de produção recusa
esses emissores quando aparecem no caminho efetivo de entrega.

## Critérios ainda bloqueantes para R12

1. Confirmar e guardar evidência dos TTLs e acessos de DigitalOcean e Sentry.
2. Classificar cada tabela persistida por finalidade, regra R01–R15 e exceção de
   legal hold; nenhum job genérico pode preceder essa classificação.
3. Criar marcador e telemetria por rotina, com sucesso, falha e atraso sem PII.
4. Testar limites de 180 dias, idempotência, concorrência PostgreSQL e
   reaplicação de tombstones após restauração.
5. Executar dry-run sintético. Ativação e descarte produtivos continuam sob o
   gate humano separado já registrado.
