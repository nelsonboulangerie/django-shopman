"""Passkey — a identidade que mora no aparelho e viaja com a pessoa.

O que ela resolve, e por que ela é diferente de tudo o mais que temos aqui:

- **Não tem código para ler nem digitar.** Rosto ou digital, um toque. O OTP existe porque
  não havia melhor; isto é melhor.
- **Atravessa navegador e aparelho.** A credencial mora no chaveiro do sistema e sincroniza
  (iCloud, Google) — então "reconhecer" deixa de depender de cookie, que é justamente o que
  se perde entre o navegador embutido do WhatsApp e o Safari.
- **É imune a phishing.** A credencial só assina para o NOSSO domínio, verificado pelo
  sistema operacional. Link encaminhado, site clonado, engenharia social por telefone: nada
  disso produz uma assinatura válida. Nem o OTP nem o link de acesso dão isso.

⚠️ **Não substitui o WhatsApp, complementa.** O cadastro exige um navegador de verdade (dentro
de webview o suporte é irregular), e nem toda pessoa vai ativar. Quem não ativar segue pelo
caminho de sempre — link pessoal + confirmação por mensagem. Passkey é o atalho de quem quer,
nunca o pedágio de quem não pediu.

Sobre criar entidade: atende os quatro critérios sem esforço — **histórico** (quando foi
usada), **auditoria** (a pessoa vê e revoga), **query indexada** (`credential_id` é o que o
navegador manda para achar a chave) e **cardinalidade > 1** (o celular dela, o computador da
loja, o tablet). Guardar isso em JSON seria perder o índice e a integridade do `credential_id`,
que é a chave primária lógica do protocolo.
"""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Passkey(models.Model):
    """Uma credencial WebAuthn de um cliente, num aparelho.

    O par de chaves é assimétrico: a **privada nunca sai do aparelho** (e nem nós nem a Meta
    nem ninguém a vê). Aqui fica só a pública, que serve para verificar assinatura — vazar
    esta tabela não permite entrar como ninguém, e é isso que faz passkey ser categoricamente
    diferente de guardar senha ou hash de senha.
    """

    #: Sujeito tipado, sem FK — mesmo desacoplamento do resto do doorman (`TrustedDevice`,
    #: `AccessLink`): o doorman não importa o guestman.
    customer_id = models.UUIDField(_("ID do cliente"), db_index=True)

    #: O identificador que o NAVEGADOR manda no login para dizer qual chave ele vai usar.
    #: Base64url, como o protocolo entrega. Único porque é a identidade da credencial.
    credential_id = models.CharField(
        _("ID da credencial"), max_length=512, unique=True, db_index=True,
    )
    #: A chave PÚBLICA (base64url do formato COSE). Só verifica assinatura; não entra em nada.
    public_key = models.TextField(_("chave pública"))

    #: Contador anti-replay do autenticador. Se uma assinatura vier com contador MENOR que o
    #: guardado, a credencial foi clonada — e o protocolo manda recusar.
    #:
    #: ⚠️ Passkey sincronizada (iCloud/Google) legitimamente reporta 0 sempre, porque existe em
    #: vários aparelhos. Então `0` não é sinal de clonagem: só comparamos quando os dois lados
    #: são maiores que zero.
    sign_count = models.BigIntegerField(_("contador de assinatura"), default=0)

    #: Como ela se apresenta ("internal" = biometria do próprio aparelho, "hybrid" = QR com o
    #: celular, "usb" = chave física). Serve para a tela dizer algo reconhecível.
    transports = models.JSONField(_("transportes"), default=list, blank=True)

    #: Nome que a PESSOA reconhece na lista ("iPhone da Ana"). Sem isto, revogar credencial é
    #: escolher entre dois identificadores base64 — ou seja, não é escolha.
    label = models.CharField(_("apelido"), max_length=100, blank=True, default="")

    created_at = models.DateTimeField(_("criada em"), auto_now_add=True)
    last_used_at = models.DateTimeField(_("usada em"), null=True, blank=True)

    class Meta:
        verbose_name = _("passkey")
        verbose_name_plural = _("passkeys")
        ordering = ["-last_used_at", "-created_at"]
        indexes = [models.Index(fields=["customer_id", "-created_at"])]

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        return self.label or f"passkey {self.credential_id[:12]}…"

    def touch(self, *, sign_count: int | None = None) -> None:
        """Registrar uso. O contador só sobe — nunca desce."""
        fields = ["last_used_at"]
        self.last_used_at = timezone.now()
        if sign_count is not None and sign_count > self.sign_count:
            self.sign_count = sign_count
            fields.append("sign_count")
        self.save(update_fields=fields)
