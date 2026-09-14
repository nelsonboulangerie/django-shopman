# Ensaio preparado — não executado

Revisão central obrigatória antes de instalar esta instrumentação temporária em staging. Nenhuma mudança de configuração, deploy, probe remoto ou tentativa de login foi executada nesta preparação. Não aplicar em produção.

## Por que observabilidade existente não basta

SignInEvent depende de tentativa/autenticação e registra IP bruto via XFF esquerdo. SHOPMAN_LOG_CLIENT_IP também imprime IP bruto. Logs HTTP comuns registram resposta/caminho, não a origem dos campos META necessários. Nenhum deles comprova substituição de um DO-Connecting-IP fornecido pelo cliente.

## Patch temporário

`services/admin_ip_probe.py` observa exclusivamente GET anônimo para a view existente `/admin/login/`. Não cria rota ou altera resposta. Só funciona com SHOPMAN_ENVIRONMENT exatamente staging, token de pelo menos 32 caracteres, marcador hexadecimal sintético de 16 caracteres e prazo restante entre zero e 900 segundos. Ausência, erro de configuração, expiração, token incorreto, usuário autenticado, POST ou outro ambiente tornam a observação inerte.

O logger existente `shopman` recebe o marcador e HMAC-SHA256 de IPs normalizados em REMOTE_ADDR, DO-Connecting-IP, CF-Connecting-IP, X-Real-IP e até oito posições de XFF. Não recebe token, URL, nome, senha, cookie, IP bruto ou header bruto. O segredo temporário impede correlacionar esses fingerprints depois de sua destruição. A operação ainda deve tratar fingerprints como dados restritos e eliminá-los após o registro do resultado agregado.

## Preparação pela coordenação

1. Inventariar os hosts Admin, API, domínio padrão DO e qualquer BFF que exponha o login. Identificar quais rotas são permitidas e quais têm bloqueio real. Host HTTP sozinho não autentica o ingress. Comparar topologia de staging com produção; diferenças impedem extrapolar o resultado.
2. Revisar o diff exclusivo da instrumentação e seu rollback. Preservar os segredos existentes; não reaplicar o spec do repositório. Instalar apenas em staging com fonte Admin ainda não liberada para produção.
3. Configurar token aleatório temporário pelo canal de segredos existente e prazo Unix de no máximo 15 minutos. Não colocar o token em argv, comandos salvos ou logs. Compartilhá-lo com os dois clientes do ensaio por canal autorizado. Não usar contas, senhas, PIN, cookies ou sessões.
4. Executar `python scripts/probe_admin_ingress.py --url https://HOST-STAGING/admin/login/ --staging-host HOST-STAGING` em duas redes externas independentes. O token é lido da variável SHOPMAN_ADMIN_IP_PROBE_TOKEN no cliente. Repetir para cada entrada permitida, uma a uma. O script não segue redirects nem usa proxy HTTP de ambiente; faz cinco GETs e imprime somente caso, marcador, status e fingerprint de um endereço documental sintético. Redirecionamento é observado, não seguido com o segredo.
5. Recolher somente registros `admin_ip_probe` associados aos marcadores gerados, usando acesso de logs já existente e restrito. Um 200 sozinho não constitui evidência; ausência de registro é inconclusiva. Não habilitar log de headers ou usar endpoint echo.

## Critérios objetivos

| Prova | Resultado exigido |
|---|---|
| Estabilidade por origem | Campo `do` é estável entre baseline, forged-do, forged-forwarded, forged-all e baseline-repeat da mesma rede; não é `absent_or_invalid`. |
| Separação | Duas origens reais distintas têm fingerprints `do` distintos sob o mesmo segredo. Registrar apenas igualdade/desigualdade no laudo final. |
| Sobrescrita de input | Campo `do` nunca coincide com `synthetic_spoof_fingerprint`, mesmo quando o cliente enviou DO-Connecting-IP. XFF, CF e X-Real-IP forjados não mudam `do`. |
| Entradas alternativas | Toda rota que alcança a view satisfaz a mesma prova; uma rota não equivalente deve estar bloqueada antes da view, com evidência de regra e resposta. Não inferir bloqueio apenas pela ausência do log. |
| Ausência de efeitos | Nenhuma tentativa de autenticação, criação de sessão de usuário, alerta de senha ou consumo do bucket de POST. GET pode ter os efeitos normais da página, como cookie CSRF descartado pelo cliente. |

Não forçar a conclusão: campo `do` igual ao proxy, valor fornecido pelo cliente preservado, cliente repartido entre buckets ou caminho desconhecido mantém #655 retido. A documentação do header não substitui essas provas nem a equivalência do ingress real.

## Remoção e liberação

1. A janela expira automaticamente. Apagar token e prazo temporários do staging pelo fluxo central.
2. Reverter somente o commit de instrumentação: remover o serviço, a chamada no middleware, settings temporários, script, testes e este runbook. Manter o commit permanente do contrato de IP.
3. Conferir GET normal sem registros de probe, inclusive enviando o token antigo. Destruir o segredo e remover os logs/fingerprints do ensaio conforme acesso disponível; conservar somente conclusões e marcadores necessários à auditoria, sem endereços.
4. Revisar o commit permanente, as configurações propostas e a prova de todas as entradas antes de liberar `do`. Não há alteração automática de produção. Atomicidade/TTL Redis continuam no contrato de throttling existente e precisam dos gates normais; probes GET não exercitam senha nem carga de rate limiting.
