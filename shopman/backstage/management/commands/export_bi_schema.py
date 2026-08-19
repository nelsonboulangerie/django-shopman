"""Generate the B.I. contract mirror consumed by the bi-nuxt surface.

Single source of truth: the projection dataclasses in
``shopman.backstage.projections.bi_*``. The drift test
(``test_bi_schema_export``) regenerates the file in-memory and compares it to
disk. Run::

    python manage.py export_bi_schema

after touching the B.I. projection dataclasses.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from shopman.backstage.contracts import render_contract_module, run_contract_export
from shopman.backstage.projections.bi_cash import (
    BICashDay,
    BICashHourRow,
    BICashMethodRow,
    BICashOperatorRow,
    BICashPrevious,
    BICashReport,
)
from shopman.backstage.projections.bi_change import (
    BIChangeReport,
    ChangeHabit,
    ChangeMix,
    DayChangeForecast,
)
from shopman.backstage.projections.bi_customers import (
    BICustomerSegmentRow,
    BICustomersReport,
    BICustomersWeekRow,
)
from shopman.backstage.projections.bi_explore import (
    BIExploreMetricOption,
    BIExploreReport,
    BIExploreRow,
)
from shopman.backstage.projections.bi_forecast import (
    BIForecastReport,
    DayForecast,
    Expectation,
    ForecastBasis,
    ForecastBranch,
    ForecastOccasion,
    OccasionYear,
)
from shopman.backstage.projections.bi_production import (
    BIOvenTimeRow,
    BIProductionDay,
    BIProductionPrevious,
    BIProductionReport,
)
from shopman.backstage.projections.bi_profiles import (
    BIConsumptionProfilesReport,
    BIProfileBand,
    BIProfileBeverage,
    BIProfileCategoryRow,
    BIProfileEstimate,
    BIProfileRange,
    BIProfileReading,
    BIProfileRow,
    BIProfileSensitivity,
    BIProfilesPrevious,
    BIRevpashRow,
    BIStrikeCell,
)
from shopman.backstage.projections.bi_sales import (
    BISalesChannelRow,
    BISalesDay,
    BISalesPrevious,
    BISalesReport,
    BITopSkuRow,
)

#: Generated artifact, relative to the repository root (``BASE_DIR``).
OUTPUT_RELATIVE_PATH = Path("surfaces/bi-nuxt/app/generated/biContract.ts")

#: Every dataclass exported to the surface, dependencies first.
CONTRACT_DATACLASSES = (
    BIOvenTimeRow,
    BIProductionDay,
    BIProductionPrevious,
    BIProductionReport,
    BISalesDay,
    BISalesChannelRow,
    BITopSkuRow,
    BISalesPrevious,
    BISalesReport,
    BICashDay,
    BICashOperatorRow,
    BICashHourRow,
    BICashMethodRow,
    BICashPrevious,
    BICashReport,
    BICustomerSegmentRow,
    BICustomersWeekRow,
    BICustomersReport,
    BIExploreRow,
    BIExploreMetricOption,
    BIExploreReport,
    Expectation,
    ForecastBranch,
    ForecastBasis,
    OccasionYear,
    ForecastOccasion,
    DayForecast,
    BIForecastReport,
    ChangeHabit,
    ChangeMix,
    DayChangeForecast,
    BIChangeReport,
    BIProfileReading,
    BIProfileBand,
    BIProfileRow,
    BIProfileRange,
    BIProfileSensitivity,
    BIProfileCategoryRow,
    BIStrikeCell,
    BIProfileBeverage,
    BIRevpashRow,
    BIProfileEstimate,
    BIProfilesPrevious,
    BIConsumptionProfilesReport,
)


def output_path() -> Path:
    return Path(settings.BASE_DIR) / OUTPUT_RELATIVE_PATH


def render_bi_contract_ts() -> str:
    """Render the generated TypeScript contract mirror (deterministic)."""
    return render_contract_module(
        source="shopman/backstage/projections/bi_*.py",
        command="export_bi_schema",
        dataclasses=CONTRACT_DATACLASSES,
    )


class Command(BaseCommand):
    help = "Generate the B.I. contract mirror (TypeScript) from the projections."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--check",
            action="store_true",
            help="Exit non-zero if the generated file is stale (do not write).",
        )

    def handle(self, *args, **options) -> None:
        run_contract_export(
            self,
            relative_path=OUTPUT_RELATIVE_PATH,
            rendered=render_bi_contract_ts(),
            check=bool(options.get("check")),
        )
