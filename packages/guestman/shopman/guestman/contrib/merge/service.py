"""MergeService — consolidate two customer records into one."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone
from shopman.guestman.exceptions import CustomerError
from shopman.guestman.gates import Gates
from shopman.guestman.models import (
    ContactPoint,
    Customer,
    CustomerAddress,
    ExternalIdentity,
)

logger = logging.getLogger(__name__)


#: Os campos de identidade que NÃO têm dono no Core — e o que, em cada um,
#: quer dizer "vazio".
#:
#: A distinção é a regra deste arquivo, e é ela que decide o que se escreve
#: aqui. ``Customer.phone``/``email`` também moram na linha, mas NÃO entram
#: nesta lista: eles são cache de um ``ContactPoint``, o Core já sabe propagá-lo
#: (``ContactPoint.set_as_primary`` → ``_sync_to_customer``), e reimplementar a
#: propagação aqui criaria uma segunda régua para a mesma verdade. O que o merge
#: fazia de errado com eles não era deixar de copiar: era mover o
#: ``ContactPoint`` sem avisar o Core. Ver ``_adopt_contact_cache``.
#:
#: Já ``document`` e ``birthday`` não têm mecanismo nenhum atrás — ``document``
#: é coluna escrita à mão por ``create_customer`` e zerada por ``purge_pii``, e
#: ``CustomerIdentifier`` não o espelha. Sem dono no Core, o dono é o merge:
#: por isso o cadastro largado só com um CPF era unificado sem que o CPF
#: chegasse na cara do sobrevivente.
_IDENTITY_GAP_FIELDS: tuple[tuple[str, object], ...] = (
    ("document", ""),
    ("birthday", None),
)

#: O "vazio" de cada campo que a unificação pode mover, para o desfazer repor.
#: Inclui o par do nome e o cache de contato, que não estão na lista acima.
_IDENTITY_EMPTY: dict[str, object] = {
    **dict(_IDENTITY_GAP_FIELDS),
    "first_name": "",
    "last_name": "",
    "phone": "",
    "email": "",
}


@dataclass(frozen=True)
class MergeResult:
    """Summary of a completed merge."""

    source_ref: str
    target_ref: str
    migrated_contact_points: int
    migrated_external_identities: int
    migrated_identifiers: int
    migrated_addresses: int
    migrated_preferences: int
    migrated_consents: int
    migrated_timeline_events: int
    loyalty_merged: bool
    migrated_orders: int = 0
    audit_id: str = ""


class MergeService:
    """
    Service for merging duplicate customers.

    Consolidates all related data from source into target, then
    deactivates the source. Requires strong evidence (Gate G6).

    All operations run inside a single transaction.atomic().
    """

    @classmethod
    def merge(
        cls,
        source_customer: Customer,
        target_customer: Customer,
        evidence: dict,
        actor: str = "",
    ) -> MergeResult:
        """
        Merge source_customer into target_customer.

        Args:
            source_customer: Customer to be deactivated (donor).
            target_customer: Customer to receive all data (survivor).
            evidence: Dict with evidence keys for G6 gate.
            actor: Who initiated the merge (audit trail).

        Returns:
            MergeResult with counts of migrated records.

        Raises:
            CustomerError: If gate validation fails or customers are invalid.
        """
        # --- Validate via G6 ---
        Gates.merge_safety(
            source_id=str(source_customer.pk),
            target_id=str(target_customer.pk),
            evidence=evidence,
        )

        if not source_customer.is_active:
            raise CustomerError(
                "MERGE_DENIED",
                message="Source customer is already inactive.",
            )
        if not target_customer.is_active:
            raise CustomerError(
                "MERGE_DENIED",
                message="Target customer is inactive.",
            )

        with transaction.atomic():
            # Lock both canonical rows in deterministic order before any child.
            # The checks above were only hints: deletion may have won while this
            # request waited, so active state must be revalidated under lock.
            locked = {
                customer.pk: customer
                for customer in Customer.objects.select_for_update()
                .filter(pk__in=(source_customer.pk, target_customer.pk))
                .order_by("pk")
            }
            source = locked.get(source_customer.pk)
            target = locked.get(target_customer.pk)
            if source is None or not source.is_active:
                raise CustomerError("MERGE_FAILED", message="Source customer is inactive.")
            if target is None or not target.is_active:
                raise CustomerError("MERGE_FAILED", message="Target customer is inactive.")

            # Snapshot tracks migrated PKs for undo
            snapshot: dict[str, list] = {}

            counts = {
                "contact_points": cls._migrate_contact_points(source, target, snapshot),
                "external_identities": cls._migrate_external_identities(source, target, snapshot),
                "identifiers": cls._migrate_identifiers(source, target, snapshot),
                "addresses": cls._migrate_addresses(source, target, snapshot),
                "preferences": cls._migrate_preferences(source, target, snapshot),
                "consents": cls._migrate_consents(source, target, snapshot),
                "timeline_events": cls._migrate_timeline_events(source, target, snapshot),
                "orders": cls._migrate_orders(source, target, snapshot),
            }
            loyalty_merged = cls._merge_loyalty(source, target, snapshot)

            # Recalculate insights for target
            cls._recalculate_insights(target)

            # Audit trail — timeline event on target
            cls._log_merge_event(source, target, evidence, actor)

            # ⚠️ DEPOIS do evento de timeline, e isso é ordem, não estilo: o
            # evento nomeia o doador ("Customer X (Ana) merged into…") e esta
            # etapa esvazia a linha dele. Invertida, a trilha registraria um
            # doador sem nome — justo no lugar onde alguém vai procurar o que
            # foi desfeito.
            cls._fill_identity_gaps(source, target, snapshot)

            # Deactivate source — use .update() to bypass _sync_contact_points()
            # which would fail since source's CPs were migrated to target.
            merge_note = f"{source.notes}\n[MERGED] → {target.ref} by {actor}".strip()
            Customer.objects.filter(pk=source.pk).update(
                is_active=False,
                notes=merge_note,
            )
            source.refresh_from_db()

            # Create audit record
            audit = cls._create_audit(source, target, evidence, actor, counts, loyalty_merged, snapshot)

        logger.info(
            "Merged customer %s → %s by %s: %s (audit=%s)",
            source.ref,
            target.ref,
            actor,
            counts,
            audit.pk,
        )

        return MergeResult(
            source_ref=source.ref,
            target_ref=target.ref,
            migrated_contact_points=counts["contact_points"],
            migrated_external_identities=counts["external_identities"],
            migrated_identifiers=counts["identifiers"],
            migrated_addresses=counts["addresses"],
            migrated_preferences=counts["preferences"],
            migrated_consents=counts["consents"],
            migrated_timeline_events=counts["timeline_events"],
            loyalty_merged=loyalty_merged,
            migrated_orders=counts["orders"],
            audit_id=str(audit.pk),
        )

    @classmethod
    def undo(cls, audit_id: str, actor: str = "") -> None:
        """
        Partially revert a merge within the undo window.

        Moves migrated records back to the source customer and
        reactivates it. Loyalty is NOT reverted (too complex, manual only).

        Args:
            audit_id: UUID of the MergeAudit record.
            actor: Who initiated the undo.

        Raises:
            CustomerError: If audit not found, already reverted, or window expired.
        """
        from shopman.guestman.contrib.merge.models import MergeAudit, MergeStatus

        try:
            audit = MergeAudit.objects.get(pk=audit_id)
        except MergeAudit.DoesNotExist as e:
            raise CustomerError("UNDO_FAILED", message="Merge audit record not found.") from e

        if audit.status != MergeStatus.COMPLETED:
            raise CustomerError("UNDO_FAILED", message="Merge already reverted.")

        if not audit.can_undo:
            raise CustomerError(
                "UNDO_FAILED",
                message=f"Undo window expired at {audit.undo_deadline}.",
            )

        with transaction.atomic():
            # MergeAudit's historical UUID fields store the integer Customer PK
            # encoded as a UUID.  Convert explicitly before building the lock
            # map; comparing the UUID object to integer dict keys always misses.
            source_pk = int(audit.source_id)
            target_pk = int(audit.target_id)
            locked = {
                customer.pk: customer
                for customer in Customer.objects.select_for_update()
                .filter(pk__in=(source_pk, target_pk))
                .order_by("pk")
            }
            source = locked.get(source_pk)
            target = locked.get(target_pk)
            if source is None or target is None or not target.is_active:
                raise CustomerError(
                    "UNDO_FAILED",
                    message="Merge participants are no longer available.",
                )

            snapshot = audit.snapshot

            # Revert contact points
            cp_pks = snapshot.get("contact_points", [])
            if cp_pks:
                ContactPoint.objects.filter(pk__in=cp_pks, customer=target).update(
                    customer=source,
                )

            # Revert external identities
            eid_pks = snapshot.get("external_identities", [])
            if eid_pks:
                ExternalIdentity.objects.filter(pk__in=eid_pks, customer=target).update(
                    customer=source,
                )

            # Revert identifiers
            ident_pks = snapshot.get("identifiers", [])
            if ident_pks:
                try:
                    from shopman.guestman.contrib.identifiers.models import CustomerIdentifier

                    CustomerIdentifier.objects.filter(pk__in=ident_pks, customer=target).update(
                        customer=source,
                    )
                except ImportError:
                    logger.warning("Merge optional component unavailable: identifiers; related operation was not performed")

            # Revert addresses
            addr_pks = snapshot.get("addresses", [])
            if addr_pks:
                CustomerAddress.objects.filter(pk__in=addr_pks, customer=target).update(
                    customer=source,
                )

            # Revert preferences
            pref_pks = snapshot.get("preferences", [])
            if pref_pks:
                try:
                    from shopman.guestman.contrib.preferences.models import CustomerPreference

                    CustomerPreference.objects.filter(pk__in=pref_pks, customer=target).update(
                        customer=source,
                    )
                except ImportError:
                    logger.warning("Merge optional component unavailable: preferences; related operation was not performed")

            # Revert consents (only non-conflicting ones that were moved)
            consent_pks = snapshot.get("consents_moved", [])
            if consent_pks:
                try:
                    from shopman.guestman.contrib.consent.models import CommunicationConsent

                    CommunicationConsent.objects.filter(pk__in=consent_pks, customer=target).update(
                        customer=source,
                    )
                except ImportError:
                    logger.warning("Merge optional component unavailable: consent; related operation was not performed")

            # Revert timeline events
            te_pks = snapshot.get("timeline_events", [])
            if te_pks:
                try:
                    from shopman.guestman.contrib.timeline.models import TimelineEvent

                    TimelineEvent.objects.filter(pk__in=te_pks, customer=target).update(
                        customer=source,
                    )
                except ImportError:
                    logger.warning("Merge optional component unavailable: timeline; related operation was not performed")

            # Revert order identity links
            order_snapshots = snapshot.get("orders", [])
            if order_snapshots:
                try:
                    from shopman.orderman.models import Order

                    for order_snapshot in order_snapshots:
                        Order.objects.filter(pk=order_snapshot["pk"]).update(
                            handle_type=order_snapshot.get("handle_type"),
                            handle_ref=order_snapshot.get("handle_ref"),
                            data=order_snapshot.get("data") or {},
                        )
                except ImportError:
                    logger.warning("Merge optional component unavailable: orderman; related operation was not performed")

            # NOTE: Loyalty is NOT reverted automatically — too complex.
            # Manual adjustment via LoyaltyService if needed.

            # Devolver o documento / contato / nome / aniversário que a
            # unificação tirou da linha do doador para tapar a lacuna do
            # sobrevivente. A ordem é a da ida ao contrário — limpa no
            # sobrevivente ANTES de repor no doador — pelo mesmo motivo de lá: o
            # UNIQUE do telefone é global e recusaria os dois juntos.
            cls._restore_identity_gaps(source, target, snapshot)

            # Reactivate source
            Customer.objects.filter(pk=source.pk).update(is_active=True)

            # Log undo event on target timeline
            cls._log_undo_event(source, target, actor)

            # Update audit
            audit.status = MergeStatus.REVERTED
            audit.reverted_at = timezone.now()
            audit.reverted_by = actor
            audit.save(update_fields=["status", "reverted_at", "reverted_by"])

        logger.info("Reverted merge %s (audit=%s) by %s", audit, audit.pk, actor)

    # ======================================================================
    # Audit
    # ======================================================================

    @classmethod
    def _create_audit(
        cls,
        source: Customer,
        target: Customer,
        evidence: dict,
        actor: str,
        counts: dict,
        loyalty_merged: bool,
        snapshot: dict,
    ):
        from shopman.guestman.contrib.merge.models import MergeAudit

        return MergeAudit.objects.create(
            source_ref=source.ref,
            target_ref=target.ref,
            source_id=source.pk,
            target_id=target.pk,
            actor=actor,
            evidence={k: v for k, v in evidence.items() if v},
            snapshot=snapshot,
            migrated_contact_points=counts["contact_points"],
            migrated_external_identities=counts["external_identities"],
            migrated_identifiers=counts["identifiers"],
            migrated_addresses=counts["addresses"],
            migrated_preferences=counts["preferences"],
            migrated_consents=counts["consents"],
            migrated_timeline_events=counts["timeline_events"],
            loyalty_merged=loyalty_merged,
        )

    # ======================================================================
    # Migration helpers
    # ======================================================================

    @classmethod
    def _fill_identity_gaps(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> dict:
        """O que o doador tinha, o sobrevivente NÃO tinha, e o Core não governa.

        Aqui mora SÓ o que não tem mecanismo atrás (``document``, ``birthday``,
        o nome). O contato não entra: ele é cache de ``ContactPoint`` e quem o
        propaga é o Core, em ``_adopt_contact_cache``.

        Só LACUNA. Quem sobrevive nunca é sobrescrito: é ele que está na
        comanda, é dele que o operador acabou de falar com o cliente, e um
        merge que troca o CPF de quem fica não unifica — adultera.

        É por isto que o caso mais comum do balcão existia e não tinha conserto.
        O cadastro largado só com um CPF é um FANTASMA: um documento sem rosto,
        nascido de uma nota pedida no balcão. Quando ele reencontra o dono, a
        unificação movia contato, pedido e fidelidade — e deixava o documento
        para trás, na linha do doador que ela mesma acabava de desativar. O
        operador unificava, via "cadastros unificados", e o CPF que ele queria
        cadastrar continuava fora do cadastro.

        ⚠️ O valor é LIMPO no doador antes de ser escrito no sobrevivente.
        Limpar mantém UM dono por dado — dois cadastros respondendo "este CPF é
        meu" é exatamente a pergunta que o conflito do PDV faz, e ela precisa de
        uma resposta só.

        O que saiu de onde fica no ``snapshot``, que é o que o ``undo`` lê.
        """
        moved: dict[str, object] = {}

        for field, empty in _IDENTITY_GAP_FIELDS:
            donor_value = getattr(source, field, empty)
            if donor_value in (empty, None):
                continue
            if getattr(target, field, empty) not in (empty, None):
                continue
            moved[field] = donor_value

        # O NOME anda inteiro ou não anda. Emprestar só o sobrenome de um
        # cadastro para o primeiro nome de outro constrói uma pessoa que não
        # existe — "Fulano" + "Silva" de outra ficha vira "Fulano Silva".
        if not target.first_name and not target.last_name and (source.first_name or source.last_name):
            moved["first_name"] = source.first_name
            moved["last_name"] = source.last_name

        # ⚠️ `setdefault`, nunca atribuição: `_adopt_contact_cache` já pode ter
        # anotado o contato que o doador cedeu, e sobrescrever aqui apagaria do
        # desfazer justamente o que o Core moveu.
        filled = snapshot.setdefault("identity_filled", {})
        if not moved:
            return {}

        Customer.objects.filter(pk=source.pk).update(
            **{field: _IDENTITY_EMPTY.get(field, "") for field in moved}
        )
        for field, value in moved.items():
            setattr(target, field, value)
        target.save(update_fields=[*moved, "updated_at"])

        # `birthday` é date e não atravessa JSON sozinho.
        filled.update({
            field: value.isoformat() if hasattr(value, "isoformat") else value
            for field, value in moved.items()
        })
        logger.info(
            "Merge filled identity gaps on %s from %s: %s",
            target.ref,
            source.ref,
            sorted(moved),
        )
        return moved

    @classmethod
    def _restore_identity_gaps(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> None:
        """Desfaz ``_fill_identity_gaps``: o dado volta para o doador.

        ⚠️ Só volta o que NINGUÉM mexeu depois. Entre a unificação e o desfazer
        cabem 24 horas de balcão, e se alguém corrigiu o CPF do sobrevivente
        nesse meio-tempo o valor que está lá agora é uma decisão de alguém — não
        o resíduo de um merge. Devolver por cima dela apagaria o trabalho de
        quem corrigiu, calado, dentro de um "desfazer" que prometia o contrário.
        """
        filled = snapshot.get("identity_filled") or {}
        if not filled:
            return

        cleared: dict[str, object] = {}
        restored: dict[str, object] = {}
        for field, raw in filled.items():
            current = getattr(target, field, None)
            # O snapshot passou por JSON: `birthday` voltou como texto.
            stored = current if str(current) == str(raw) else None
            if stored is None:
                continue
            cleared[field] = _IDENTITY_EMPTY.get(field, "")
            restored[field] = current

        if not restored:
            logger.info(
                "Undo kept identity fields on %s: changed since the merge", target.ref
            )
            return

        # `.update()` dos dois lados: `save()` espelharia o contato num
        # ContactPoint novo, e os ContactPoints originais já voltaram para o
        # doador alguns passos acima.
        Customer.objects.filter(pk=target.pk).update(**cleared)
        Customer.objects.filter(pk=source.pk).update(**restored)
        for field, value in cleared.items():
            setattr(target, field, value)

    @classmethod
    def _migrate_contact_points(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> int:
        """
        Migrate contact points from source to target.

        Strategy:
        - If target already has the same (type, value_normalized), skip (source's is deleted).
        - If source CP is_primary but target already has a primary for that type,
          demote source's to non-primary before moving.
        """
        source_cps = list(source.contact_points.all())
        migrated = 0
        moved_pks: list[str] = []

        for cp in source_cps:
            # Check if target already has this exact contact
            duplicate = ContactPoint.objects.filter(
                customer=target,
                type=cp.type,
                value_normalized=cp.value_normalized,
            ).exists()

            if duplicate:
                # Target already has it — delete source's copy
                cp.delete()
                continue

            # Check global uniqueness — another customer might have this value
            global_exists = ContactPoint.objects.filter(
                type=cp.type,
                value_normalized=cp.value_normalized,
            ).exclude(pk=cp.pk).exists()

            if global_exists:
                # Can't move — unique constraint would fail, delete source's
                cp.delete()
                continue

            # If source's CP is primary, check if target already has a primary for this type
            if cp.is_primary:
                target_has_primary = ContactPoint.objects.filter(
                    customer=target,
                    type=cp.type,
                    is_primary=True,
                ).exists()
                if target_has_primary:
                    cp.is_primary = False

            cp.customer = target
            cp.save(update_fields=["customer", "is_primary", "updated_at"])
            # Continuou PRINCIPAL no alvo? Então ele passa a ser o contato do
            # cadastro, e o cache do `Customer` tem de acompanhar. Quem sabe
            # fazer isso é o Core, não este arquivo.
            if cp.is_primary:
                cls._adopt_contact_cache(source, target, cp, snapshot)
            moved_pks.append(str(cp.pk))
            migrated += 1

        snapshot["contact_points"] = moved_pks
        return migrated

    @classmethod
    def _adopt_contact_cache(
        cls, source: Customer, target: Customer, cp: ContactPoint, snapshot: dict
    ) -> None:
        """O sobrevivente assume o contato que chegou — pela porta do Core.

        ``Customer.phone``/``email`` são cache: quem manda é o ``ContactPoint``
        principal. O Core já tem o caminho (``set_as_primary`` chama
        ``_sync_to_customer``, e o docstring dele diz para quê: manter o
        ``get_by_phone``/``get_by_email`` consistentes). O merge movia o
        ``ContactPoint`` e não chamava ninguém — o contato mudava de dono na
        tabela e o cadastro do sobrevivente seguia com o campo vazio, que é
        justamente o campo que a tela lê.

        Não se copia o valor à mão aqui. Pede-se ao Core que propague.

        Só LACUNA: com o campo já preenchido, quem manda é o principal que o
        sobrevivente já tinha — e nesse caso o que chegou foi demovido antes de
        mudar de dono, então nem chega até aqui.

        ⚠️ Só o TELEFONE sai do doador, e sai porque o banco obriga:
        ``unique_customer_phone`` é global e não olha ``is_active``, então os
        dois com o mesmo número por um instante já é o ``IntegrityError``. O
        e-mail do doador FICA — não há UNIQUE que o force, e o Core guarda o
        cache do doador de propósito, como registro histórico do que era dele.
        Limpar o que ninguém pediu já foi proposto e recusado nesta casa; o que
        se limpa aqui é o mínimo que o esquema não deixa em paz, e mesmo esse
        vai para o ``snapshot`` para o desfazer repor.
        """
        field = {
            ContactPoint.Type.PHONE: "phone",
            ContactPoint.Type.WHATSAPP: "phone",
            ContactPoint.Type.EMAIL: "email",
        }.get(cp.type)
        if not field or getattr(target, field, ""):
            return

        if field == "phone" and getattr(source, field, "") == cp.value_normalized:
            Customer.objects.filter(pk=source.pk).update(phone="")
            source.phone = ""
            snapshot.setdefault("identity_filled", {})["phone"] = cp.value_normalized

        cp.set_as_primary()
        setattr(target, field, cp.value_normalized)

    @classmethod
    def _migrate_external_identities(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> int:
        """
        Migrate external identities from source to target.

        Skip duplicates (same provider+uid already on target).
        """
        source_ids = list(source.external_identities.all())
        migrated = 0
        moved_pks: list[str] = []

        for eid in source_ids:
            duplicate = ExternalIdentity.objects.filter(
                customer=target,
                provider=eid.provider,
                provider_uid=eid.provider_uid,
            ).exists()

            if duplicate:
                eid.delete()
                continue

            eid.customer = target
            try:
                eid.save(update_fields=["customer", "updated_at"])
                moved_pks.append(str(eid.pk))
                migrated += 1
            except IntegrityError:
                # Global unique constraint (provider, provider_uid) — skip
                logger.warning(
                    "Merge: skipped external identity %s/%s (integrity error)",
                    eid.provider,
                    eid.provider_uid,
                )

        snapshot["external_identities"] = moved_pks
        return migrated

    @classmethod
    def _migrate_identifiers(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> int:
        """
        Migrate CustomerIdentifiers from source to target.

        Skip if target already has identifier with same (type, value).
        Demote is_primary if target already has a primary of that type.
        """
        try:
            from shopman.guestman.contrib.identifiers.models import CustomerIdentifier
        except ImportError:
            snapshot["identifiers"] = []
            return 0

        source_ids = list(CustomerIdentifier.objects.filter(customer=source))
        migrated = 0
        moved_pks: list[str] = []

        for ident in source_ids:
            duplicate = CustomerIdentifier.objects.filter(
                customer=target,
                identifier_type=ident.identifier_type,
                identifier_value=ident.identifier_value,
            ).exists()

            if duplicate:
                ident.delete()
                continue

            # Check global uniqueness
            global_exists = CustomerIdentifier.objects.filter(
                identifier_type=ident.identifier_type,
                identifier_value=ident.identifier_value,
            ).exclude(pk=ident.pk).exists()

            if global_exists:
                ident.delete()
                continue

            if ident.is_primary:
                target_has_primary = CustomerIdentifier.objects.filter(
                    customer=target,
                    identifier_type=ident.identifier_type,
                    is_primary=True,
                ).exists()
                if target_has_primary:
                    ident.is_primary = False

            ident.customer = target
            ident.save(update_fields=["customer", "is_primary"])
            moved_pks.append(str(ident.pk))
            migrated += 1

        snapshot["identifiers"] = moved_pks
        return migrated

    @classmethod
    def _migrate_addresses(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> int:
        """
        Migrate addresses from source to target.

        If source address is_default but target already has a default,
        demote source's.
        """
        source_addrs = list(source.addresses.all())
        migrated = 0
        moved_pks: list[str] = []

        for addr in source_addrs:
            if addr.is_default:
                target_has_default = CustomerAddress.objects.filter(
                    customer=target,
                    is_default=True,
                ).exists()
                if target_has_default:
                    addr.is_default = False

            addr.customer = target
            addr.save(update_fields=["customer", "is_default", "updated_at"])
            moved_pks.append(str(addr.pk))
            migrated += 1

        snapshot["addresses"] = moved_pks
        return migrated

    @classmethod
    def _migrate_preferences(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> int:
        """
        Migrate preferences. Target wins on conflict (same category+key).
        """
        try:
            from shopman.guestman.contrib.preferences.models import CustomerPreference
        except ImportError:
            snapshot["preferences"] = []
            return 0

        source_prefs = list(CustomerPreference.objects.filter(customer=source))
        migrated = 0
        moved_pks: list[str] = []

        for pref in source_prefs:
            conflict = CustomerPreference.objects.filter(
                customer=target,
                category=pref.category,
                key=pref.key,
            ).exists()

            if conflict:
                # Target wins — discard source's preference
                pref.delete()
                continue

            pref.customer = target
            pref.save(update_fields=["customer", "updated_at"])
            moved_pks.append(str(pref.pk))
            migrated += 1

        snapshot["preferences"] = moved_pks
        return migrated

    @classmethod
    def _migrate_consents(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> int:
        """
        Migrate consents. More restrictive wins on conflict.

        Restrictiveness order: opted_out > pending > opted_in.
        If source is more restrictive, update target's record.
        """
        try:
            from shopman.guestman.contrib.consent.models import (
                CommunicationConsent,
                ConsentStatus,
            )
        except ImportError:
            snapshot["consents_moved"] = []
            return 0

        _RESTRICTIVENESS = {
            ConsentStatus.OPTED_OUT: 3,
            ConsentStatus.PENDING: 2,
            ConsentStatus.OPTED_IN: 1,
        }

        source_consents = list(CommunicationConsent.objects.filter(customer=source))
        migrated = 0
        moved_pks: list[str] = []  # Only non-conflict moves (reversible)

        for consent in source_consents:
            try:
                target_consent = CommunicationConsent.objects.get(
                    customer=target,
                    channel=consent.channel,
                )
            except CommunicationConsent.DoesNotExist:
                # No conflict — move to target
                consent.customer = target
                consent.save(update_fields=["customer", "updated_at"])
                moved_pks.append(str(consent.pk))
                migrated += 1
                continue

            # Conflict — more restrictive wins
            source_level = _RESTRICTIVENESS.get(consent.status, 0)
            target_level = _RESTRICTIVENESS.get(target_consent.status, 0)

            if source_level > target_level:
                target_consent.status = consent.status
                target_consent.revoked_at = consent.revoked_at
                target_consent.save(update_fields=["status", "revoked_at", "updated_at"])

            # Either way, delete source's consent record
            consent.delete()
            migrated += 1

        snapshot["consents_moved"] = moved_pks
        return migrated

    @classmethod
    def _migrate_timeline_events(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> int:
        """Reassign all timeline events from source to target."""
        try:
            from shopman.guestman.contrib.timeline.models import TimelineEvent
        except ImportError:
            snapshot["timeline_events"] = []
            return 0

        event_pks = list(
            TimelineEvent.objects.filter(customer=source).values_list("pk", flat=True)
        )
        count = TimelineEvent.objects.filter(pk__in=event_pks).update(customer=target)
        snapshot["timeline_events"] = [str(pk) for pk in event_pks]
        return count

    @classmethod
    def _migrate_orders(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> int:
        """
        Reassign customer-facing order identity from source to target.

        Order history is sealed through ``Order.data["customer_ref"]`` with
        ``handle_ref`` as the phone fallback used by storefront access checks.
        A customer merge that leaves those fields behind fragments history.
        """
        try:
            from django.apps import apps

            # Orderman is an optional integration: the module may be importable
            # as a namespace package while its app (and tables) are absent —
            # e.g. guestman running standalone. Skip order migration gracefully
            # in that case instead of hitting "no such table: orderman_order".
            if not apps.is_installed("shopman.orderman"):
                snapshot["orders"] = []
                return 0
            from django.db.models import Q
            from shopman.orderman.models import Order
        except ImportError:
            snapshot["orders"] = []
            return 0

        source_uuid = str(source.uuid)
        target_uuid = str(target.uuid)
        identity_query = (
            Q(data__customer_ref=source.ref)
            | Q(data__customer__ref=source.ref)
            | Q(data__customer__uuid=source_uuid)
            | Q(data__customer__id=source_uuid)
            | Q(handle_type__in=["phone", "whatsapp"], handle_ref=source.phone)
            | Q(handle_type="customer", handle_ref=source_uuid)
        )

        moved: list[dict] = []
        migrated = 0
        # Identity predicates use only Order columns/JSON, so each row appears
        # once even when several predicates match. DISTINCT is unnecessary and
        # PostgreSQL rejects it together with FOR UPDATE; keep the row lock.
        for order in Order.objects.select_for_update().filter(identity_query):
            previous = {
                "pk": order.pk,
                "handle_type": order.handle_type,
                "handle_ref": order.handle_ref,
                "data": order.data or {},
            }
            data = cls._order_data_for_merge(order.data or {}, source, target)
            handle_ref = order.handle_ref

            if order.handle_type in {"phone", "whatsapp"} and order.handle_ref == source.phone:
                handle_ref = target.phone
            elif order.handle_type == "customer" and str(order.handle_ref or "") == source_uuid:
                handle_ref = target_uuid

            if data == (order.data or {}) and handle_ref == order.handle_ref:
                continue

            order.data = data
            order.handle_ref = handle_ref
            order.save(update_fields=["data", "handle_ref", "updated_at"])
            moved.append(previous)
            migrated += 1

        snapshot["orders"] = moved
        return migrated

    @staticmethod
    def _order_data_for_merge(data: dict, source: Customer, target: Customer) -> dict:
        next_data = dict(data)
        source_uuid = str(source.uuid)
        target_uuid = str(target.uuid)

        if next_data.get("customer_ref") == source.ref:
            next_data["customer_ref"] = target.ref
        for key in ("customer_uuid", "customer_id"):
            if str(next_data.get(key) or "") == source_uuid:
                next_data[key] = target_uuid

        customer_data = next_data.get("customer")
        if isinstance(customer_data, dict):
            customer_next = dict(customer_data)
            if customer_next.get("ref") == source.ref:
                customer_next["ref"] = target.ref
            for key in ("uuid", "id"):
                if str(customer_next.get(key) or "") == source_uuid:
                    customer_next[key] = target_uuid
            if customer_next.get("phone") == source.phone:
                customer_next["phone"] = target.phone
            next_data["customer"] = customer_next

        return next_data

    @classmethod
    def _merge_loyalty(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> bool:
        """
        Merge loyalty accounts: sum points, keep higher tier.

        Source's transactions are reassigned to target's account.
        """
        try:
            from shopman.guestman.contrib.loyalty.models import (
                LoyaltyAccount,
                LoyaltyTier,
                LoyaltyTransaction,
                TransactionType,
            )
        except ImportError:
            return False

        try:
            source_account = LoyaltyAccount.objects.select_for_update().get(
                customer=source,
            )
        except LoyaltyAccount.DoesNotExist:
            return False

        # Get or create target account
        target_account, _ = LoyaltyAccount.objects.get_or_create(
            customer=target,
        )
        target_account = LoyaltyAccount.objects.select_for_update().get(
            pk=target_account.pk,
        )

        # Save pre-merge state for reference (loyalty undo is manual)
        snapshot["loyalty"] = {
            "source_account_id": str(source_account.pk),
            "target_account_id": str(target_account.pk),
            "source_points": source_account.points_balance,
            "source_lifetime": source_account.lifetime_points,
            "source_stamps": source_account.stamps_current,
            "source_stamps_completed": source_account.stamps_completed,
            "source_tier": source_account.tier,
            "target_points_before": target_account.points_balance,
            "target_tier_before": target_account.tier,
        }

        # Sum points
        target_account.points_balance += source_account.points_balance
        target_account.lifetime_points += source_account.lifetime_points

        # Sum stamps
        target_account.stamps_current += source_account.stamps_current
        target_account.stamps_completed += source_account.stamps_completed

        # Keep higher tier
        _TIER_ORDER = {
            LoyaltyTier.BRONZE: 0,
            LoyaltyTier.SILVER: 1,
            LoyaltyTier.GOLD: 2,
            LoyaltyTier.PLATINUM: 3,
        }
        if _TIER_ORDER.get(source_account.tier, 0) > _TIER_ORDER.get(target_account.tier, 0):
            target_account.tier = source_account.tier

        target_account.save(update_fields=[
            "points_balance",
            "lifetime_points",
            "stamps_current",
            "stamps_completed",
            "tier",
            "updated_at",
        ])

        # Reassign transactions to target account
        LoyaltyTransaction.objects.filter(account=source_account).update(
            account=target_account,
        )

        # Record a merge adjustment transaction
        LoyaltyTransaction.objects.create(
            account=target_account,
            transaction_type=TransactionType.ADJUST,
            points=source_account.points_balance,
            balance_after=target_account.points_balance,
            description=f"Merge: absorbed {source.ref}",
            reference=f"merge:{source.ref}",
        )

        # Deactivate source account
        source_account.is_active = False
        source_account.save(update_fields=["is_active", "updated_at"])

        return True

    @classmethod
    def _recalculate_insights(cls, target: Customer) -> None:
        """Recalculate insights for the merged target customer."""
        try:
            from shopman.guestman.contrib.insights.service import InsightService

            InsightService.recalculate(target.ref)
        except ImportError:
            logger.warning("Merge optional component unavailable: insights; related operation was not performed")
        except Exception as exc:
            # Non-fatal — insights can be recalculated later
            logger.warning(
                "Merge: could not recalculate insights for %s: %s",
                target.ref,
                exc,
            )

    @classmethod
    def _log_merge_event(
        cls,
        source: Customer,
        target: Customer,
        evidence: dict,
        actor: str,
    ) -> None:
        """Record the merge as a timeline event on the target."""
        try:
            from shopman.guestman.contrib.timeline.models import EventType, TimelineEvent

            TimelineEvent.objects.create(
                customer=target,
                event_type=EventType.SYSTEM,
                title=f"Merge: {source.ref} → {target.ref}",
                description=(
                    f"Customer {source.ref} ({source.name}) merged into "
                    f"{target.ref} ({target.name})."
                ),
                channel="admin",
                reference=f"merge:{source.ref}",
                metadata={
                    "source_ref": source.ref,
                    "source_name": source.name,
                    "evidence": {k: v for k, v in evidence.items() if v},
                },
                created_by=actor,
            )
        except ImportError:
            logger.warning("Merge optional component unavailable: timeline; related operation was not performed")

    @classmethod
    def _log_undo_event(
        cls,
        source: Customer,
        target: Customer,
        actor: str,
    ) -> None:
        """Record the undo as a timeline event on the target."""
        try:
            from shopman.guestman.contrib.timeline.models import EventType, TimelineEvent

            TimelineEvent.objects.create(
                customer=target,
                event_type=EventType.SYSTEM,
                title=f"Merge reverted: {source.ref} ← {target.ref}",
                description=(
                    f"Merge of {source.ref} into {target.ref} was reverted."
                ),
                channel="admin",
                reference=f"undo-merge:{source.ref}",
                metadata={"source_ref": source.ref, "target_ref": target.ref},
                created_by=actor,
            )
        except ImportError:
            logger.warning("Merge optional component unavailable: timeline; related operation was not performed")
