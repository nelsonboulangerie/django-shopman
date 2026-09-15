"""Grava captura completa em arquivo novo privado, sem sobrescrever evidências."""

import os
import stat
import uuid
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from shopman.shop.services.ifood_catalog_capture import CaptureError, capture_catalog


class Command(BaseCommand):
    help = "Captura catálogo iFood por GET para revisão local; não altera catálogo nem banco."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--merchant-id", required=True)
        parser.add_argument("--catalog-id", required=True)
        parser.add_argument("--context", required=True)
        parser.add_argument("--output", required=True, help="Arquivo novo em diretório privado já existente.")

    def handle(self, *args, **options):
        target = Path(options["output"])
        directory = None
        temporary = None
        created = False
        try:
            directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            info = os.fstat(directory)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise CaptureError("Diretório de saída deve pertencer ao usuário e ter modo privado 0700.")
            try:
                os.stat(target.name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:  # silêncio-deliberado: destino ausente é pré-condição da criação exclusiva.
                pass  # Ausência é obrigatória; o link exclusivo abaixo também protege a corrida.
            else:
                raise CaptureError("Arquivo de saída já existe; não será sobrescrito.")
            raw = capture_catalog(merchant_id=options["merchant_id"], catalog_id=options["catalog_id"],
                                  context=options["context"])
            temporary = f".ifood-capture-{uuid.uuid4().hex}.tmp"
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            created = True
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            # Só publica o nome final depois da captura validada e da gravação integral.
            os.link(temporary, target.name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            os.fsync(directory)
        except CaptureError as exc:
            raise CommandError(str(exc)) from None
        except OSError:
            raise CommandError("Não foi possível gravar a captura privada; confira destino e permissões.") from None
        finally:
            if directory is not None:
                if created:
                    try:
                        os.unlink(temporary, dir_fd=directory)
                    except FileNotFoundError:  # silêncio-deliberado: temporário já removido não deve ocultar o erro original.
                        pass  # A remoção prévia não deve ocultar a falha original.
                os.close(directory)
        self.stdout.write("Captura completa salva para revisão local. Nenhuma escrita de catálogo executada.")
