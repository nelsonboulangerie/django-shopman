# Ensaio preparado — não executado

Revisão central obrigatória antes de instalar esta instrumentação temporária em staging. Nenhuma mudança de configuração, deploy, probe remoto ou tentativa de login foi executada nesta preparação. Não aplicar em produção.

## Por que observabilidade existente não basta

SignInEvent depende de tentativa/autenticação e registra IP bruto via XFF esquerdo. SHOPMAN_LOG_CLIENT_IP também imprime IP bruto. Logs HTTP comuns registram resposta/caminho, não a origem dos campos META necessários. Nenhum deles comprova substituição de um DO-Connecting-IP fornecido pelo cliente.

## Patch temporário

`services/admin_ip_probe.py` observa exclusivamente GET anônimo para a view existente `/admin/login/`. Não cria rota ou altera resposta. Só funciona com SHOPMAN_ENVIRONMENT exatamente staging, allowlist explícita SHOPMAN_ADMIN_IP_PROBE_HOSTS (vazia por padrão), token de pelo menos 32 caracteres, marcador hexadecimal sintético de 16 caracteres e prazo restante entre zero e 900 segundos. Ausência, erro de configuração, expiração, token incorreto, usuário autenticado, POST ou outro ambiente tornam a observação inerte.

O logger existente `shopman` recebe o marcador e HMAC-SHA256 de IPs normalizados em REMOTE_ADDR, DO-Connecting-IP, CF-Connecting-IP, X-Real-IP e até oito posições de XFF. Não recebe token, URL, nome, senha, cookie, IP bruto ou header bruto. O segredo temporário impede correlacionar esses fingerprints depois de sua destruição. A operação ainda deve tratar fingerprints como dados restritos e eliminá-los após o registro do resultado agregado.

## Preparação pela coordenação

1. Inventariar os hosts Admin, API, domínio padrão DO e qualquer BFF que exponha o login. Exigir app ID isolado aprovado, diferente de 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f; conferir via API/CLI DO que os destinos pertencem a esse app. Não basta confiar no Host fornecido pelo cliente. Nenhum host do app online pode entrar no ensaio. Identificar quais rotas são permitidas e quais têm bloqueio real. Host HTTP sozinho não autentica o ingress. Comparar topologia de staging com produção; diferenças impedem extrapolar o resultado.
2. Revisar o diff exclusivo da instrumentação e seu rollback. Preservar os segredos existentes; não reaplicar o spec do repositório. Instalar apenas em staging com fonte Admin ainda não liberada para produção.
3. Configurar somente os hosts isolados aprovados em SHOPMAN_ADMIN_IP_PROBE_HOSTS e token aleatório temporário pelo canal de segredos existente e prazo Unix de no máximo 15 minutos. Não colocar o token em argv, comandos salvos ou logs. Compartilhá-lo com os dois clientes do ensaio por canal autorizado. Não usar contas, senhas, PIN, cookies ou sessões.
4. Executar `python scripts/probe_admin_ingress.py --app-id APP-ID-ISOLADO-APROVADO --url https://HOST-STAGING/admin/login/ --staging-host HOST-STAGING` em duas redes externas independentes. O token é lido da variável SHOPMAN_ADMIN_IP_PROBE_TOKEN no cliente. Repetir para cada entrada permitida, uma a uma. O script não segue redirects nem usa proxy HTTP de ambiente; faz sete GETs e imprime somente caso, marcador, status e fingerprint de um endereço documental sintético. Redirecionamento é observado, não seguido com o segredo.
5. Recolher somente registros `admin_ip_probe` associados aos marcadores gerados, usando acesso de logs já existente e restrito. Um 200 sozinho não constitui evidência; ausência de registro é inconclusiva. Não habilitar log de headers ou usar endpoint echo.

## Critérios objetivos

| Prova | Resultado exigido |
|---|---|
| Estabilidade por origem | Campo `do` é estável entre baseline, forged-do, forged-forwarded, forged-all, duplicate-do, duplicate-do-reverse e baseline-repeat da mesma rede; não é `absent_or_invalid`. |
| Separação | Duas origens reais distintas têm fingerprints `do` distintos sob o mesmo segredo. Registrar apenas igualdade/desigualdade no laudo final. |
| Sobrescrita de input | Campo `do` nunca coincide com `synthetic_spoof_fingerprint`, mesmo quando o cliente enviou DO-Connecting-IP em campo único ou duplicado nas duas ordens. XFF, CF e X-Real-IP forjados não mudam `do`. |
| Entradas alternativas | Toda rota que alcança a view satisfaz a mesma prova; uma rota não equivalente deve estar bloqueada antes da view, com evidência de regra e resposta. Não inferir bloqueio apenas pela ausência do log. |
| Ausência de efeitos | Nenhuma tentativa de autenticação, criação de sessão de usuário, alerta de senha ou consumo do bucket de POST. GET pode ter os efeitos normais da página, como cookie CSRF descartado pelo cliente. |

Não forçar a conclusão: campo `do` igual ao proxy, valor fornecido pelo cliente preservado, cliente repartido entre buckets ou caminho desconhecido mantém #655 retido. A documentação do header não substitui essas provas nem a equivalência do ingress real.

## Remoção e liberação

1. A janela expira automaticamente. Apagar allowlist, token e prazo temporários do staging pelo fluxo central.
2. Reverter este commit de instrumentação: remover o serviço/middleware, settings temporários, script, testes e este runbook. Este PR é independente do contrato permanente do #655: não instala rate-limit, seletor IP ou deploy check do contrato.
3. Conferir GET normal sem registros de probe, inclusive enviando o token antigo. Destruir o segredo e remover os logs/fingerprints do ensaio conforme acesso disponível; conservar somente conclusões e marcadores necessários à auditoria, sem endereços.
4. Revisar o commit permanente, as configurações propostas e a prova de todas as entradas antes de liberar `do`. Não há alteração automática de produção. Atomicidade/TTL Redis continuam no contrato de throttling existente e precisam dos gates normais; probes GET não exercitam senha nem carga de rate limiting.


## Inventário read-only de 14/09

A conta DO consultada contém shopman-nelson, nb-catalog-app e nb-site; não foi localizado Django staging separado. O default ingress shopman-staging-cdjpy.ondigitalocean.app pertence a shopman-nelson, que atende os domínios reais de operação. Esse app tem SHOPMAN_ENVIRONMENT=staging global: o nome e a flag não comprovam isolamento e NÃO autorizam instalar token/probe nessa instalação. Admin e API chegam ao web, backup também, e o catch-all chega ao storefront. Escolher destino novo/isolado exige revisão central; este patch não cria apps, muda DNS ou configura serviços.

Presença física do usuário não é necessária: uma origem controlada pode ser um runner GitHub hospedado e a outra uma máquina/remota já disponível. A independência dos endereços deve ser confirmada pelos fingerprints e não presumida de dois processos ou containers na mesma saída NAT.
