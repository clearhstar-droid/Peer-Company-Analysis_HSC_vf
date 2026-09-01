"""SEC EDGAR (XBRL company-facts) integration — US 3 companies. No API key
required, only an identifying User-Agent. Mirrors lib/sources/edgar.ts,
including two live-verified fixes:
  - "best coverage" tag selection instead of "first non-empty tag" (US
    Steel's primary revenue tag goes quiet for exactly 2023-2024; a lower
    priority candidate covers it).
  - a grossProfit-minus-SG&A fallback for operating income (Nucor doesn't
    tag OperatingIncomeLoss under any standard concept at all).
"""

import os
from datetime import date, datetime

import requests

from ..types import CostBreakdown, QuarterRecord

EDGAR_CIK = {
    "nucor": "0000073309",
    "cleveland-cliffs": "0000764065",
    "us-steel": "0001163302",
}

TAGS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "gross_profit": ["GrossProfit"],
    "cogs": ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"],
    "operating_income": ["OperatingIncomeLoss"],
    "sga": ["SellingGeneralAndAdministrativeExpense"],
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
    ],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "interest_expense": ["InterestExpense", "InterestExpenseDebt", "InterestAndDebtExpense"],
    "depreciation": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
    ],
}


def _contact_header() -> str:
    contact = os.environ.get("EDGAR_CONTACT_EMAIL", "dashboard-contact@example.com")
    return f"HyundaiSteel-PeerDashboard/1.0 ({contact})"


def _fetch_concept_facts(cik: str, tag: str) -> list[dict] | None:
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
    try:
        res = requests.get(
            url,
            headers={"User-Agent": _contact_header(), "Accept": "application/json"},
            timeout=15,
        )
    except requests.RequestException:
        return None
    if not res.ok:
        return None
    try:
        return res.json().get("units", {}).get("USD")
    except ValueError:
        return None


def _duration_days(f: dict) -> float | None:
    start = f.get("start")
    if not start:
        return None
    d0 = datetime.fromisoformat(start)
    d1 = datetime.fromisoformat(f["end"])
    return (d1 - d0).days


def resolve_quarterly(facts: list[dict] | None) -> dict[str, float]:
    result: dict[str, float] = {}
    if not facts:
        return result
    best_filed: dict[str, str] = {}

    for f in facts:
        if f.get("form") not in ("10-Q", "10-K"):
            continue
        days = _duration_days(f)
        if days is None:
            continue
        key = None
        if f.get("fp") == "FY" and days > 300:
            key = f"{f['fy']}-FY"
        elif f.get("fp") in ("Q1", "Q2", "Q3") and 75 <= days <= 100:
            key = f"{f['fy']}-{f['fp']}"
        if not key:
            continue
        if key not in best_filed or f["filed"] >= best_filed[key]:
            best_filed[key] = f["filed"]
            result[key] = f["val"] / 1_000_000  # raw dollars -> millions

    years = {int(k.split("-")[0]) for k in result}
    for year in years:
        fy = result.get(f"{year}-FY")
        q1 = result.get(f"{year}-Q1")
        q2 = result.get(f"{year}-Q2")
        q3 = result.get(f"{year}-Q3")
        if None not in (fy, q1, q2, q3):
            result[f"{year}-Q4"] = fy - q1 - q2 - q3
    return result


def resolve_instant(facts: list[dict] | None) -> dict[str, float]:
    """Balance-sheet concepts are point-in-time (no `start`); all four
    quarter-end snapshots are reported directly, no Q4 derivation needed."""
    result: dict[str, float] = {}
    if not facts:
        return result
    best_filed: dict[str, str] = {}
    for f in facts:
        if f.get("form") not in ("10-Q", "10-K"):
            continue
        if f.get("start"):
            continue
        key = None
        if f.get("fp") == "FY":
            key = f"{f['fy']}-Q4"
        elif f.get("fp") in ("Q1", "Q2", "Q3"):
            key = f"{f['fy']}-{f['fp']}"
        if not key:
            continue
        if key not in best_filed or f["filed"] >= best_filed[key]:
            best_filed[key] = f["filed"]
            result[key] = f["val"] / 1_000_000
    return result


def _fetch_best_coverage(cik: str, tags: list[str], years: list[int], instant: bool = False) -> list[dict] | None:
    resolver = resolve_instant if instant else resolve_quarterly
    best, best_score = None, -1
    for tag in tags:
        facts = _fetch_concept_facts(cik, tag)
        if not facts:
            continue
        resolved = resolver(facts)
        score = sum(1 for k in resolved if int(k.split("-")[0]) in years)
        if score > best_score:
            best_score, best = score, facts
    return best


def _get(m: dict[str, float], year: int, quarter: int) -> float | None:
    return m.get(f"{year}-Q{quarter}")


def fetch_edgar_company(company_id: str, years: list[int], quarters: list[int]) -> tuple[list[QuarterRecord], list[str]]:
    cik = EDGAR_CIK.get(company_id)
    notes: list[str] = []
    if not cik:
        return [], ["SEC EDGAR CIK가 매핑되어 있지 않은 기업입니다."]

    revenue = resolve_quarterly(_fetch_best_coverage(cik, TAGS["revenue"], years))
    gross_profit = resolve_quarterly(_fetch_best_coverage(cik, TAGS["gross_profit"], years))
    cogs = resolve_quarterly(_fetch_best_coverage(cik, TAGS["cogs"], years))
    operating_income = resolve_quarterly(_fetch_best_coverage(cik, TAGS["operating_income"], years))
    sga_fallback = resolve_quarterly(_fetch_best_coverage(cik, TAGS["sga"], years))
    pretax_income = resolve_quarterly(_fetch_best_coverage(cik, TAGS["pretax_income"], years))
    net_income = resolve_quarterly(_fetch_best_coverage(cik, TAGS["net_income"], years))
    assets = resolve_instant(_fetch_best_coverage(cik, TAGS["assets"], years, instant=True))
    liabilities = resolve_instant(_fetch_best_coverage(cik, TAGS["liabilities"], years, instant=True))
    equity = resolve_instant(_fetch_best_coverage(cik, TAGS["equity"], years, instant=True))
    interest = resolve_quarterly(_fetch_best_coverage(cik, TAGS["interest_expense"], years))
    depr = resolve_quarterly(_fetch_best_coverage(cik, TAGS["depreciation"], years))

    if not gross_profit and not cogs:
        notes.append("매출총이익/매출원가 태그를 찾지 못했습니다.")
    if not interest:
        notes.append("이자비용(금융비용) 태그가 공시되지 않아 0으로 처리됩니다.")
    if not depr:
        notes.append("상각비 태그가 공시되지 않아 0으로 처리됩니다.")

    records: list[QuarterRecord] = []

    for year in years:
        for quarter in quarters:
            rev = _get(revenue, year, quarter)
            op_inc = _get(operating_income, year, quarter)
            pretax = _get(pretax_income, year, quarter)
            net = _get(net_income, year, quarter)
            a = _get(assets, year, quarter)
            e = _get(equity, year, quarter)
            l = _get(liabilities, year, quarter)

            if a is not None and e is not None and l is None:
                l = a - e
            if a is not None and l is not None and e is None:
                e = a - l

            gp = _get(gross_profit, year, quarter)
            cg = _get(cogs, year, quarter)
            resolved_gp = gp if gp is not None else (rev - cg if rev is not None and cg is not None else None)

            if op_inc is None and resolved_gp is not None:
                sga_fetched = _get(sga_fallback, year, quarter)
                if sga_fetched is not None:
                    op_inc = resolved_gp - sga_fetched

            if None in (rev, op_inc, pretax, net, a, e, l, resolved_gp):
                continue

            resolved_cogs = rev - resolved_gp
            sga_expense = resolved_gp - op_inc

            non_op_net = pretax - op_inc
            interest_expense = _get(interest, year, quarter) or 0.0
            remainder = non_op_net + interest_expense
            if remainder >= 0:
                non_op_income, non_op_expense = remainder, interest_expense
            else:
                non_op_income, non_op_expense = 0.0, interest_expense - remainder

            tax_expense = pretax - net
            depr_total = _get(depr, year, quarter) or 0.0

            records.append(
                QuarterRecord(
                    company_id=company_id,
                    year=year,
                    quarter=quarter,
                    fx_to_krw=0.0,  # filled in by the caller with a current FX rate
                    revenue=rev,
                    cogs=resolved_cogs,
                    sga_expense=sga_expense,
                    non_operating_income=non_op_income,
                    non_operating_expense=non_op_expense,
                    tax_expense=tax_expense,
                    assets=a,
                    liabilities=l,
                    equity=e,
                    cost_breakdown=CostBreakdown(
                        depreciation_in_cogs=depr_total * 0.7,
                        depreciation_in_sga=depr_total * 0.3,
                        finance_cost_in_non_op_expense=interest_expense,
                    ),
                )
            )

    return records, notes


def is_edgar_covered(company_id: str) -> bool:
    return company_id in EDGAR_CIK
