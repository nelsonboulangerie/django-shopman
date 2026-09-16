# Piloto individual de 2FA no Admin

Este PR prepara adesão individual ao 2FA existente. Não liga `SHOPMAN_ADMIN_REQUIRE_2FA`, não muda allowlist, login público, PDV ou ingress. Não retoma #655/#671. O piloto de uma conta **não significa que todo o Admin esteja protegido**.

## Problema e comportamento novo

`setup_admin_totp` confirmava o dispositivo sem prova de posse, imprimia URI/QR no terminal e `--force` apagava o fator anterior antes de validar a reposição. Agora o comando apenas prepara um dispositivo pendente. O titular, já autenticado como staff ativo, confirma novamente sua senha no navegador, valida o TOTP e guarda/testa a recuperação. A página usa layout, tema, campos e botões Unfold.

A confirmação consome um dos dez códigos de recuperação de 96 bits e deixa nove disponíveis. Só então uma transação confirma o novo autenticador, substitui os fatores anteriores e cria `AdminTwoFactorEnrollment`, marcador persistente da adesão individual. Esgotar ou apagar os códigos/dispositivos não remove esse marcador nem desliga a exigência. Ele não tem tela de edição no Admin.

O segundo fator passa a ser exigido em cada nova sessão que acesse `/admin/` para a conta inscrita. As sessões ainda não verificadas dessa conta também passam pelo gate na próxima requisição Admin. As APIs do PDV e o login público mantêm seu contrato. A inscrição de substituição exige o segundo fator anterior ou um código de recuperação, mesmo quando a flag global está desligada.

A verificação utiliza a API transacional de django-otp (lock de dispositivo, proteção contra replay e throttling). A confirmação de senha na inscrição utiliza o throttle persistente do dispositivo pendente. TOTPDevice e StaticDevice não possuem ModelAdmin: nem superusuários podem criar, confirmar, transferir ou apagar fatores por POST direto de CRUD. O card de configurações aponta para a inscrição pessoal. A recuperação é de uso único; seu conteúdo não fica exposto nas telas de gestão. Os dados de TOTP/static device são armazenados conforme os modelos nativos de django-otp: isso exige proteção do banco e dos backups, não implica criptografia adicional introduzida por este PR.

A página exige CSRF, não permite cache ou referência externa, e marca os POSTs/variáveis sensíveis para os filtros de erro Django. Nenhum comando imprime URI, QR, TOTP ou código de recuperação. A lista de recuperação aparece apenas na resposta de confirmação do TOTP; recarregar a página não reapresenta a lista. Não copiar tela, segredo ou códigos para PR, CI, chat ou log.

## Publicação e dependências

Publicação serializada pela coordenação. Os deploys estavam pausados por credencial DOCR rejeitada quando este PR foi preparado; isso não autoriza contornar o problema ou mudar credenciais.

Aplicar as migrações antes de servir a versão nova: `backstage.0068_admin_two_factor_enrollment` depende de `0067_alter_operatoralert_type`, e o plugin nativo `otp_static` traz suas migrações. Não há migração de adesão automática para dispositivos antigos: possuir um TOTP confirmado pelo comando antigo não comprova recuperação nem inscreve a conta no piloto.

A flag global continua OFF. Antes de um rollout global futuro, `python manage.py check_admin_2fa_ready` deve confirmar autenticador usado, adesão e recuperação testada/disponível para **todos os staff ativos**, não apenas superusuários. O comando é somente leitura e não ativa nada.

## Única etapa humana do piloto, após deploy aprovado

A operação prepara a conta correta, em console privado, com `python manage.py setup_admin_totp <usuario>`. Se já houver um autenticador, usar `--force` somente para preparar sua substituição: o anterior permanece válido até concluir. Não há segredo no retorno do comando. Nunca executar isso como ação automática de CI, seed ou deploy.

Pablo abre `https://admin.boulangerie.com.br/admin/2fa/enroll/` no próprio navegador e segue o assistente: entra com sua conta, confirma sua senha, escaneia o QR no autenticador, digita o TOTP, guarda os dez códigos fora do celular e usa um deles para concluir. **Não enviar nenhum código, QR ou senha à tarefa.** A mensagem de conclusão informa a ativação individual. Uma nova sessão deve solicitar o segundo fator; a sessão que concluiu já está verificada.

O titular deve confirmar à operação apenas que concluiu e guardou a recuperação; não é necessário compartilhar os códigos. Até essa conclusão, o marcador individual não é criado. Uma inscrição abandonada pode ser preparada novamente pelo comando sem revogar fatores atuais.

## Recuperação e manutenção

Se perder o autenticador, entrar com a senha e selecionar “Código de recuperação” na verificação. Usar um dos nove códigos guardados; ele é consumido uma única vez. A operação então prepara `setup_admin_totp <usuario> --force`, e o titular cadastra o substituto na sessão verificada. Apenas a conclusão completa troca o fator e os códigos antigos.

Se perder **todos** os fatores e códigos, a conta permanece bloqueada no Admin. Não apagar `AdminTwoFactorEnrollment`, não desligar a flag para tentar desbloquear o piloto e não confirmar um TOTP por edição de banco. É necessária recuperação supervisionada com identidade verificada e acesso operacional legítimo, restaurando um fator de backup antes de reinscrever. Este PR não oferece um reset remoto baseado apenas em senha nem automatiza esse procedimento de exceção. A proteção contra bloqueio inicial é guardar e provar a recuperação antes de aderir.

Reverter código depois de contas inscritas pode retirar a proteção individual: rollback deve manter o gate/marcador ou bloquear o Admin durante manutenção. Não reverter a migração ou apagar o marcador como rollback automático.

## Validação

Testes focais em PostgreSQL cobrem inscrição completa, ausência de segredos no comando, preservação do fator anterior, CSRF, recuperação/replay/throttle, concorrência, limites de `next`, exceções exatas do middleware, falha fechada sem rota de verificação, adesão individual e persistência após exaustão/deleção dos fatores. O gate canônico completo `make admin` e a inspeção visual local são executados antes da publicação; os resultados finais ficam no PR.
