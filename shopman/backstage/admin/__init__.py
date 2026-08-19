"""Backstage admin — KDS, closing, alerts, terminal do PDV, operation, dashboard."""

from shopman.backstage.admin.accounts import (  # noqa: F401
    GroupAdmin,
    UserAdmin,
    register_totp_admin,
)
from shopman.backstage.admin.alerts import OperatorAlertAdmin  # noqa: F401
from shopman.backstage.admin.aliases import (  # noqa: F401
    CategoryAliasAdmin,
    PaymentMethodAliasAdmin,
    ProductAliasAdmin,
)
from shopman.backstage.admin.bi_alerts import (  # noqa: F401
    BIAlertEventAdmin,
    BIAlertRuleAdmin,
    BIScenarioReportAdmin,
)
from shopman.backstage.admin.closing import DayClosingAdmin  # noqa: F401
from shopman.backstage.admin.consumption import (  # noqa: F401
    ConsumptionRoleAdmin,
    ProductConsumptionTagAdmin,
)
from shopman.backstage.admin.curation import hide_curated_screens  # noqa: F401
from shopman.backstage.admin.episodes import (  # noqa: F401
    OperationEpisodeAdmin,
    OperationEpisodeKindAdmin,
)
from shopman.backstage.admin.imports import (  # noqa: F401
    DailySalesFactAdmin,
    HistoricalSaleAdmin,
    ImportBatchAdmin,
)
from shopman.backstage.admin.kds import KDSInstanceAdmin  # noqa: F401
from shopman.backstage.admin.operation import (  # noqa: F401
    OperationChecklistRunAdmin,
    OperationChecklistTemplateAdmin,
    OperationTaskRunAdmin,
    OperationTaskTemplateAdmin,
)
from shopman.backstage.admin.operators import PinCredentialAdmin  # noqa: F401
from shopman.backstage.admin.pos import POSTabAdmin  # noqa: F401
from shopman.backstage.admin.seating import SeatingSpotAdmin  # noqa: F401
from shopman.backstage.admin.terminal import TerminalAdmin  # noqa: F401

register_totp_admin()

# Depois de todo mundo registrar: o backstage é o último app do INSTALLED_APPS, e
# esta chamada é a última linha do módulo, então Core e shop já colocaram no site
# tudo que tinham para colocar. Tirar antes disso não tiraria nada.
hide_curated_screens()
