"""KDS (Kitchen Display System) models."""

from __future__ import annotations

from django.db import models


class KDSInstance(models.Model):
    """Estação KDS: Prep (preparo), Picking (separação) ou Saída (``expedition``).

    A estação por onde o pedido pronto sai (entregar no balcão, despachar a
    entrega) se chama **Saída** na tela desde 26/09/2026 (decisão do dono):
    "Expedição" é o fechamento de lote da Produção, e as duas palavras iguais
    mandavam gente para o app errado. O valor gravado continua ``expedition``:
    é o identificador em inglês da função (a expedição do pedido), e trocá-lo
    migraria um valor de banco, o contrato gerado do kds-nuxt e o canal de SSE
    sem mudar uma letra do que o operador lê.
    """

    TYPE_CHOICES = [
        ("prep", "Preparo"),
        ("picking", "Separação"),
        ("expedition", "Saída"),
    ]

    ref = models.SlugField("ref", max_length=50, unique=True)
    name = models.CharField("nome", max_length=200)
    type = models.CharField("tipo", max_length=20, choices=TYPE_CHOICES)
    collections = models.ManyToManyField(
        "offerman.Collection",
        blank=True,
        verbose_name="coleções",
        help_text="Categorias de produto que esta estação processa. Vazio = catch-all.",
    )
    target_time_minutes = models.PositiveIntegerField(
        "tempo alvo (min)", default=10,
        help_text="Timer fica amarelo após este tempo, vermelho após 2x.",
    )
    sound_enabled = models.BooleanField("som ativo", default=True)
    is_active = models.BooleanField("ativa", default=True)
    # Posto sem tela (decisão do dono, 26/09/2026): o posto de Lanches tem só
    # uma impressora térmica de rede. Com um terminal aqui, cada ticket que cai
    # no posto sai impresso nele — a "Via Cozinha" de
    # ``services/order_documents.py``, composta por
    # ``receipt_escpos.kitchen_ticket`` e enviada pelo relay
    # (``services/kitchen_ticket_print.py``). Vazio = o posto lê a tela do KDS.
    print_terminal = models.ForeignKey(
        "cashman.Terminal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kds_print_stations",
        verbose_name="impressora da estação",
        help_text=(
            "Estação sem tela: os pedidos desta estação saem impressos nesta impressora. "
            "Deixe vazio quando a estação acompanha os pedidos pela tela do KDS."
        ),
    )
    config = models.JSONField(
        "configurações", default=dict, blank=True,
        help_text="text_size, dark_mode, refresh_interval, on_print, etc.",
    )

    class Meta:
        verbose_name = "estação KDS"
        verbose_name_plural = "estações KDS"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"


class KDSTicket(models.Model):
    """Ticket despachado para uma estação KDS com items de uma venda.

    Ancora em ``session_key`` (ref textual estável, não FK). A mesma chave
    resolve para a Session aberta (comanda em andamento) antes do commit e
    para o Order selado depois — ``Order.session_key`` é copiado verbatim no
    commit. Isso unifica o KDS para qualquer canal e permite disparo
    progressivo (prato-a-prato) a partir da comanda, sem re-apontar tickets.
    """

    STATUS_CHOICES = [
        ("pending", "Pendente"),
        ("in_progress", "Em andamento"),
        ("done", "Concluído"),
        ("cancelled", "Cancelado"),
    ]

    # Por onde o ticket foi concluído. A estação de tela conclui o próprio
    # ticket; a estação SEM tela (``KDSInstance.print_terminal``) recebe o
    # papel e quem dá baixa é outra porta (decisão do dono, 26/09/2026): a
    # Saída, o PDV ou o leitor de código da bancada. E o pedido que o Gestor
    # marca pronto por fora do KDS fecha os tickets que ficaram abertos.
    COMPLETED_VIA_STATION = "station"
    COMPLETED_VIA_EXIT = "exit"
    COMPLETED_VIA_POS = "pos"
    COMPLETED_VIA_SCANNER = "scanner"
    COMPLETED_VIA_ORDER_ADVANCED = "order_advanced"
    COMPLETED_VIA_CHOICES = [
        (COMPLETED_VIA_STATION, "Tela da estação"),
        (COMPLETED_VIA_EXIT, "Saída"),
        (COMPLETED_VIA_POS, "PDV"),
        (COMPLETED_VIA_SCANNER, "Leitor de código"),
        (COMPLETED_VIA_ORDER_ADVANCED, "Pedido avançado fora do KDS"),
    ]

    session_key = models.CharField(
        "chave da venda", max_length=64, db_index=True,
        help_text="Resolve para a Session aberta (comanda) ou o Order selado.",
    )
    kds_instance = models.ForeignKey(
        KDSInstance,
        on_delete=models.CASCADE,
        related_name="tickets",
        verbose_name="estação KDS",
    )
    items = models.JSONField(
        "items", default=list,
        help_text='[{"sku", "name", "qty", "notes", "line_id"}]',
    )
    status = models.CharField(
        "status", max_length=20, choices=STATUS_CHOICES, default="pending",
    )
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    completed_at = models.DateTimeField("concluído em", null=True, blank=True)
    completed_by = models.CharField(
        "concluído por", max_length=150, blank=True, default="",
        help_text="Quem deu a baixa (usuário do operador, ou o ator do sistema).",
    )
    completed_via = models.CharField(
        "concluído pela", max_length=20, blank=True, default="",
        choices=COMPLETED_VIA_CHOICES,
    )
    cancelled_at = models.DateTimeField("cancelado em", null=True, blank=True)
    acknowledged_at = models.DateTimeField(
        "ciente em", null=True, blank=True,
        help_text="Operador deu baixa no card cancelado — sai do board.",
    )

    class Meta:
        verbose_name = "ticket KDS"
        verbose_name_plural = "tickets KDS"
        ordering = ["created_at"]
        permissions = [("operate_kds", "Pode operar telas KDS (check, done, expedition)")]

    def __str__(self):
        return f"KDS #{self.pk} · {self.session_key} → {self.kds_instance.ref}"
