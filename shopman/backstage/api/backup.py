"""Download do cofre de dados curados — persona GESTOR.

Um GET devolve o XLSX inteiro (uma aba por entidade registrada no cofre), o
mesmo arquivo do ``manage.py export_backup`` — é o caminho prático de tirar o
backup de um deploy sem shell: o gestor logado baixa, guarda no Drive/Sheets, e
a volta (import) fica no comando, deliberadamente: restaurar um banco por upload
de planilha não é gesto de navegador.

Só existe o verbo de LEITURA aqui. Gate fino ``backstage.export_backup`` —
baixar a curadoria inteira (catálogo, custos de fornecedor, regras) é mais que
``view`` de um model, e menos que ser superusuário.
"""

from __future__ import annotations

import json

from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.shop.backup import workbook

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class BackupXLSXRenderer(BaseRenderer):
    """Pass-through do XLSX pronto; erros (403 etc.) chegam como dict e viram JSON."""

    media_type = _XLSX_MEDIA_TYPE
    format = "xlsx"
    charset = None
    render_style = "binary"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if isinstance(data, bytes):
            return data
        return json.dumps(data).encode("utf-8")


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Download the curated-data backup workbook (XLSX)",
        responses={200: OpenApiResponse(description="XLSX workbook, one sheet per curated entity.")},
    ),
)
class BackupExportView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.export_backup"
    renderer_classes = [BackupXLSXRenderer, JSONRenderer]

    def get(self, request):
        payload = workbook.write_xlsx(workbook.export_datasets())
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        return Response(
            payload,
            content_type=_XLSX_MEDIA_TYPE,
            headers={"Content-Disposition": f'attachment; filename="backup-{stamp}.xlsx"'},
        )
