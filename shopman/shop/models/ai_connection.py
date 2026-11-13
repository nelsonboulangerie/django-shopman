"""Conexão de IA: formato, endereço, chave e modelo, configuráveis no Admin.

Antes havia uma chave só, ``AI_ASSIST_API_KEY``, lida de variável de ambiente em
vinte arquivos, cada um criando o próprio cliente da Anthropic. Trocar de
provedor (DeepSeek, Kimi, GLM) pedia código, e configuração de loja entrava por
env, o que a ADR-042 proíbe. Agora a loja cadastra conexões e diz, por
propósito, qual delas cada função usa (``Shop.ai_routes``). Quem chama passa
por ``shopman.shop.ai``, nunca pelo SDK direto.

A chave fica cifrada no banco (``shopman.shop.secret_box``) e nunca volta ao
Admin: o formulário só a substitui e mostra os quatro últimos caracteres.
"""

from __future__ import annotations

from django.db import models


class AIProtocol(models.TextChoices):
    #: A API de mensagens da Anthropic. DeepSeek, Kimi (Moonshot), GLM (Z.ai) e
    #: MiniMax aceitam o mesmo formato com outro endereço.
    ANTHROPIC = "anthropic", "Formato Anthropic (Anthropic, DeepSeek, Kimi, GLM, MiniMax…)"
    #: O modelo de decisão da TypeSafe (Jev): escolhe entre opções tipadas.
    JEV = "jev", "Jev (TypeSafe)"


class AIConnection(models.Model):
    ref = models.SlugField(
        "referência",
        max_length=40,
        unique=True,
        help_text="Nome curto e estável, usado nas rotas por propósito. Ex.: anthropic, deepseek.",
    )
    name = models.CharField("nome", max_length=80)
    protocol = models.CharField(
        "formato", max_length=20, choices=AIProtocol.choices, default=AIProtocol.ANTHROPIC
    )
    base_url = models.URLField(
        "endereço",
        blank=True,
        help_text=(
            "Vazio usa o endereço oficial do formato. Para DeepSeek no formato Anthropic: "
            "https://api.deepseek.com/anthropic"
        ),
    )
    api_key_encrypted = models.TextField("chave (cifrada)", blank=True, editable=False)
    api_key_last4 = models.CharField("final da chave", max_length=4, blank=True, editable=False)
    model = models.CharField(
        "modelo padrão",
        max_length=80,
        help_text="Usado quando a rota do propósito não diz outro. Ex.: claude-opus-5, deepseek-flash.",
    )
    customer_text_approved = models.BooleanField(
        "pode receber mensagem de cliente",
        default=False,
        help_text=(
            "Concierge, triagem e leitura de intenções mandam o texto do cliente a este provedor. "
            "Só marque depois de aceitar a política de dados dele (LGPD)."
        ),
    )
    is_active = models.BooleanField("ativa", default=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizada em", auto_now=True)

    class Meta:
        app_label = "shop"
        verbose_name = "conexão de IA"
        verbose_name_plural = "conexões de IA"
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.ref})"

    @property
    def api_key(self) -> str:
        from shopman.shop.secret_box import open_secret

        return open_secret(self.api_key_encrypted)

    def set_api_key(self, value: str) -> None:
        from shopman.shop.secret_box import seal_secret

        value = (value or "").strip()
        self.api_key_encrypted = seal_secret(value) if value else ""
        self.api_key_last4 = value[-4:] if value else ""
