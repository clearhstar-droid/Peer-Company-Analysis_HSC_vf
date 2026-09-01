"""Derived financial lines + KRW formatting. Mirrors lib/finance.ts."""

from dataclasses import dataclass, field

from .companies import COMPANY_MAP
from .types import CostBreakdown, QuarterRecord


def _scale_cb(cb: CostBreakdown, factor: float) -> CostBreakdown:
    return CostBreakdown(
        depreciation_in_cogs=cb.depreciation_in_cogs * factor,
        depreciation_in_sga=cb.depreciation_in_sga * factor,
        labor_in_cogs=cb.labor_in_cogs * factor,
        labor_in_sga=cb.labor_in_sga * factor,
        raw_material_in_cogs=cb.raw_material_in_cogs * factor,
        finance_cost_in_non_op_expense=cb.finance_cost_in_non_op_expense * factor,
    )


def _add_cb(a: CostBreakdown, b: CostBreakdown) -> CostBreakdown:
    return CostBreakdown(
        depreciation_in_cogs=a.depreciation_in_cogs + b.depreciation_in_cogs,
        depreciation_in_sga=a.depreciation_in_sga + b.depreciation_in_sga,
        labor_in_cogs=a.labor_in_cogs + b.labor_in_cogs,
        labor_in_sga=a.labor_in_sga + b.labor_in_sga,
        raw_material_in_cogs=a.raw_material_in_cogs + b.raw_material_in_cogs,
        finance_cost_in_non_op_expense=a.finance_cost_in_non_op_expense + b.finance_cost_in_non_op_expense,
    )


@dataclass
class KrwLine:
    revenue: float = 0.0
    cogs: float = 0.0
    gross_profit: float = 0.0
    sga_expense: float = 0.0
    operating_income: float = 0.0
    non_operating_income: float = 0.0
    non_operating_expense: float = 0.0
    pretax_income: float = 0.0
    net_income: float = 0.0
    assets: float = 0.0
    liabilities: float = 0.0
    equity: float = 0.0
    cost_breakdown: CostBreakdown = field(default_factory=CostBreakdown)


@dataclass
class FinancialLine:
    company_id: str
    year: int
    quarter: int
    currency: str
    fx_to_krw: float
    revenue: float
    cogs: float
    gross_profit: float
    sga_expense: float
    operating_income: float
    non_operating_income: float
    non_operating_expense: float
    pretax_income: float
    net_income: float
    assets: float
    liabilities: float
    equity: float
    gross_margin: float
    operating_margin: float
    net_margin: float
    cost_breakdown: CostBreakdown
    krw: KrwLine


def _to_financial_line(r: QuarterRecord) -> FinancialLine:
    company = COMPANY_MAP[r.company_id]
    gross_profit = r.revenue - r.cogs
    operating_income = gross_profit - r.sga_expense
    pretax_income = operating_income + r.non_operating_income - r.non_operating_expense
    net_income = pretax_income - r.tax_expense
    fx = r.fx_to_krw

    return FinancialLine(
        company_id=r.company_id,
        year=r.year,
        quarter=r.quarter,
        currency=company.currency,
        fx_to_krw=fx,
        revenue=r.revenue,
        cogs=r.cogs,
        gross_profit=gross_profit,
        sga_expense=r.sga_expense,
        operating_income=operating_income,
        non_operating_income=r.non_operating_income,
        non_operating_expense=r.non_operating_expense,
        pretax_income=pretax_income,
        net_income=net_income,
        assets=r.assets,
        liabilities=r.liabilities,
        equity=r.equity,
        gross_margin=gross_profit / r.revenue if r.revenue else 0.0,
        operating_margin=operating_income / r.revenue if r.revenue else 0.0,
        net_margin=net_income / r.revenue if r.revenue else 0.0,
        cost_breakdown=r.cost_breakdown,
        krw=KrwLine(
            revenue=r.revenue * fx,
            cogs=r.cogs * fx,
            gross_profit=gross_profit * fx,
            sga_expense=r.sga_expense * fx,
            operating_income=operating_income * fx,
            non_operating_income=r.non_operating_income * fx,
            non_operating_expense=r.non_operating_expense * fx,
            pretax_income=pretax_income * fx,
            net_income=net_income * fx,
            assets=r.assets * fx,
            liabilities=r.liabilities * fx,
            equity=r.equity * fx,
            cost_breakdown=_scale_cb(r.cost_breakdown, fx),
        ),
    )


def get_quarter_lines(records: list[QuarterRecord]) -> list[FinancialLine]:
    return [_to_financial_line(r) for r in records]


FLOW_KEYS = [
    "revenue",
    "cogs",
    "gross_profit",
    "sga_expense",
    "operating_income",
    "non_operating_income",
    "non_operating_expense",
    "pretax_income",
    "net_income",
]


def get_annual_lines(quarter_lines: list[FinancialLine]) -> list[FinancialLine]:
    groups: dict[tuple[str, int], list[FinancialLine]] = {}
    for line in quarter_lines:
        groups.setdefault((line.company_id, line.year), []).append(line)

    result: list[FinancialLine] = []
    for (_company_id, _year), lines in groups.items():
        sorted_lines = sorted(lines, key=lambda l: l.quarter)
        q4 = sorted_lines[-1]

        base_cb = CostBreakdown()
        base_krw_cb = CostBreakdown()
        for l in sorted_lines:
            base_cb = _add_cb(base_cb, l.cost_breakdown)
            base_krw_cb = _add_cb(base_krw_cb, l.krw.cost_breakdown)

        sums = {k: sum(getattr(l, k) for l in sorted_lines) for k in FLOW_KEYS}
        krw_sums = {k: sum(getattr(l.krw, k) for l in sorted_lines) for k in FLOW_KEYS}

        revenue = sums["revenue"] or 1e-9
        result.append(
            FinancialLine(
                company_id=q4.company_id,
                year=q4.year,
                quarter=4,
                currency=q4.currency,
                fx_to_krw=sum(l.fx_to_krw for l in sorted_lines) / len(sorted_lines),
                revenue=sums["revenue"],
                cogs=sums["cogs"],
                gross_profit=sums["gross_profit"],
                sga_expense=sums["sga_expense"],
                operating_income=sums["operating_income"],
                non_operating_income=sums["non_operating_income"],
                non_operating_expense=sums["non_operating_expense"],
                pretax_income=sums["pretax_income"],
                net_income=sums["net_income"],
                assets=q4.assets,
                liabilities=q4.liabilities,
                equity=q4.equity,
                gross_margin=sums["gross_profit"] / revenue,
                operating_margin=sums["operating_income"] / revenue,
                net_margin=sums["net_income"] / revenue,
                cost_breakdown=base_cb,
                krw=KrwLine(
                    revenue=krw_sums["revenue"],
                    cogs=krw_sums["cogs"],
                    gross_profit=krw_sums["gross_profit"],
                    sga_expense=krw_sums["sga_expense"],
                    operating_income=krw_sums["operating_income"],
                    non_operating_income=krw_sums["non_operating_income"],
                    non_operating_expense=krw_sums["non_operating_expense"],
                    pretax_income=krw_sums["pretax_income"],
                    net_income=krw_sums["net_income"],
                    assets=q4.krw.assets,
                    liabilities=q4.krw.liabilities,
                    equity=q4.krw.equity,
                    cost_breakdown=base_krw_cb,
                ),
            )
        )
    return result


def format_krw(millions: float) -> str:
    sign = "-" if millions < 0 else ""
    abs_v = abs(millions)
    if abs_v >= 1_000_000:
        return f"{sign}{abs_v / 1_000_000:.1f}조원"
    if abs_v >= 100:
        return f"{sign}{round(abs_v / 100):,}억원"
    return f"{sign}{round(abs_v):,}백만원"


def format_original(amount: float, currency: str) -> str:
    unit_label = {"KRW": "백만원", "USD": "백만달러"}
    return f"{round(amount):,} {unit_label.get(currency, currency)}"


def format_percent(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:.1f}%"
