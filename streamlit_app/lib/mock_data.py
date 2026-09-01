"""Deterministic sample data — placeholder shaped like what DART/SEC EDGAR
provide, used to fill any quarter a live source can't resolve. Mirrors the
Next.js version's lib/mockData.ts (same scale assumptions), reimplemented
with Python's stdlib random instead of porting the exact PRNG — exact
numbers don't need to match between the two apps, only the shape/behavior.
"""

import math
import random
from dataclasses import dataclass

from .companies import QUARTERS, YEARS
from .types import CostBreakdown, QuarterRecord


@dataclass
class Profile:
    currency: str
    annual_revenue: float  # millions of original currency
    gross_margin_base: float
    sga_ratio: float
    raw_material_ratio: float
    labor_ratio: float
    depr_ratio: float
    finance_cost_ratio: float
    tax_rate: float
    asset_turnover: float
    equity_ratio: float


PROFILES: dict[str, Profile] = {
    "hyundai-steel": Profile("KRW", 25_000_000, 0.10, 0.045, 0.58, 0.075, 0.045, 0.012, 0.24, 0.75, 0.42),
    "posco": Profile("KRW", 40_000_000, 0.09, 0.04, 0.55, 0.07, 0.05, 0.010, 0.23, 0.65, 0.55),
    "dongkuk": Profile("KRW", 7_000_000, 0.11, 0.05, 0.52, 0.06, 0.03, 0.015, 0.24, 0.85, 0.40),
    "nucor": Profile("USD", 30_000, 0.14, 0.045, 0.44, 0.09, 0.035, 0.006, 0.24, 0.90, 0.58),
    "cleveland-cliffs": Profile("USD", 22_000, 0.07, 0.03, 0.62, 0.10, 0.05, 0.020, 0.25, 0.75, 0.32),
    "us-steel": Profile("USD", 18_000, 0.08, 0.035, 0.58, 0.09, 0.045, 0.014, 0.24, 0.80, 0.40),
}

FX_BASE = {"KRW": 1.0, "USD": 1370.0}
FX_NOISE_AMPLITUDE = {"KRW": 0.0, "USD": 30.0}


def _quarter_index(year: int, quarter: int) -> int:
    return (year - YEARS[0]) * 4 + (quarter - 1)


def _generate_for_company(company_id: str) -> list[QuarterRecord]:
    profile = PROFILES[company_id]
    rng = random.Random(hash(company_id) & 0xFFFFFFFF)
    quarterly_base = profile.annual_revenue / 4
    assets_base = profile.annual_revenue / profile.asset_turnover

    records: list[QuarterRecord] = []

    for year in YEARS:
        for quarter in QUARTERS:
            t = _quarter_index(year, quarter)
            cycle = math.sin((t / 12) * math.pi * 2)

            def noise() -> float:
                return rng.random() * 2 - 1

            revenue_multiplier = 1 + 0.018 * t + cycle * 0.06 + noise() * 0.03
            revenue = quarterly_base * revenue_multiplier

            gross_margin = max(0.02, profile.gross_margin_base + cycle * 0.02 + noise() * 0.012)
            cogs = revenue * (1 - gross_margin)
            sga_expense = revenue * (profile.sga_ratio + noise() * 0.003)

            non_operating_income = revenue * (0.003 + max(0.0, noise()) * 0.002)
            finance_cost = revenue * (profile.finance_cost_ratio + max(0.0, noise()) * 0.002)
            other_non_op_expense = revenue * 0.002
            non_operating_expense = finance_cost + other_non_op_expense

            operating_income = revenue - cogs - sga_expense
            pretax_income = operating_income + non_operating_income - non_operating_expense
            tax_expense = (
                pretax_income * profile.tax_rate
                if pretax_income > 0
                else pretax_income * profile.tax_rate * 0.3
            )

            assets = assets_base * (1 + 0.015 * t + noise() * 0.01)
            equity = assets * (profile.equity_ratio + noise() * 0.01)
            liabilities = assets - equity

            depr_total = revenue * profile.depr_ratio
            labor_total = revenue * profile.labor_ratio
            raw_material_in_cogs = revenue * profile.raw_material_ratio

            amp = FX_NOISE_AMPLITUDE[profile.currency]
            fx_to_krw = FX_BASE[profile.currency] + (
                0.0 if amp == 0 else math.sin((t / 12) * math.pi * 2 + 1) * amp
            )

            records.append(
                QuarterRecord(
                    company_id=company_id,
                    year=year,
                    quarter=quarter,
                    fx_to_krw=fx_to_krw,
                    revenue=revenue,
                    cogs=cogs,
                    sga_expense=sga_expense,
                    non_operating_income=non_operating_income,
                    non_operating_expense=non_operating_expense,
                    tax_expense=tax_expense,
                    assets=assets,
                    liabilities=liabilities,
                    equity=equity,
                    cost_breakdown=CostBreakdown(
                        depreciation_in_cogs=depr_total * 0.7,
                        depreciation_in_sga=depr_total * 0.3,
                        labor_in_cogs=labor_total * 0.65,
                        labor_in_sga=labor_total * 0.35,
                        raw_material_in_cogs=raw_material_in_cogs,
                        finance_cost_in_non_op_expense=finance_cost,
                    ),
                )
            )

    return records


_cache: list[QuarterRecord] | None = None


def get_mock_data() -> list[QuarterRecord]:
    global _cache
    if _cache is None:
        _cache = [r for company_id in PROFILES for r in _generate_for_company(company_id)]
    return _cache
