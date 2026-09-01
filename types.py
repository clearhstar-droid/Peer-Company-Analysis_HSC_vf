"""Shared data shapes. Mirrors the Next.js version's lib/types.ts."""

from dataclasses import dataclass, field


@dataclass
class CostBreakdown:
    depreciation_in_cogs: float = 0.0
    depreciation_in_sga: float = 0.0
    labor_in_cogs: float = 0.0
    labor_in_sga: float = 0.0
    raw_material_in_cogs: float = 0.0
    finance_cost_in_non_op_expense: float = 0.0


@dataclass
class QuarterRecord:
    """All monetary fields are in millions of the company's original currency."""

    company_id: str
    year: int
    quarter: int
    fx_to_krw: float
    revenue: float
    cogs: float
    sga_expense: float
    non_operating_income: float
    non_operating_expense: float
    tax_expense: float
    assets: float
    liabilities: float
    equity: float
    cost_breakdown: CostBreakdown = field(default_factory=CostBreakdown)
