"""Builds the chatbot's context string. Mirrors lib/chatContext.ts — ratios
are precomputed and explicitly labeled "quote as-is, don't recompute",
because a general-purpose LLM re-deriving a percentage from Korean
조원/억원-formatted strings has been observed to get the unit conversion
wrong by 10x."""

from .companies import COMPANY_MAP
from .finance import FinancialLine, format_krw, format_percent

PROVIDER_LABEL = {
    "sec-edgar": "SEC EDGAR 공식 공시(실제 데이터)",
    "dart": "DART 전자공시(실제 데이터)",
    "mock": "샘플(mock) 데이터",
}


def build_chat_context(
    company_ids: list[str],
    mode: str,
    year: int,
    quarter: int,
    get_line_for,
    sources: dict | None,
) -> str:
    period_label = f"{year}년(연간)" if mode == "annual" else f"{year}년 Q{quarter}"
    lines = []
    for company_id in company_ids:
        l: FinancialLine | None = get_line_for(company_id, year, quarter, mode)
        c = COMPANY_MAP[company_id]
        info = sources.get(company_id) if sources else None
        if info is not None:
            source_label = PROVIDER_LABEL["mock"] if info.status in ("mock", "error") else PROVIDER_LABEL[info.provider]
        else:
            source_label = PROVIDER_LABEL["mock"]

        if l is None:
            lines.append(f"- {c.name_ko}: 데이터 없음")
            continue

        cb = l.krw.cost_breakdown
        raw_material_ratio = cb.raw_material_in_cogs / l.krw.revenue if l.krw.revenue else 0
        labor_ratio = (cb.labor_in_cogs + cb.labor_in_sga) / l.krw.revenue if l.krw.revenue else 0
        depr_ratio = (cb.depreciation_in_cogs + cb.depreciation_in_sga) / l.krw.revenue if l.krw.revenue else 0
        finance_ratio = cb.finance_cost_in_non_op_expense / l.krw.revenue if l.krw.revenue else 0

        lines.append(
            "\n".join(
                [
                    f"- {c.name_ko}({c.name_en}, {c.region}, {'자사' if c.is_self else '동종사'}, 출처: {source_label})",
                    f"  매출액 {format_krw(l.krw.revenue)}, 매출원가 {format_krw(l.krw.cogs)}, 매출총이익 {format_krw(l.krw.gross_profit)}",
                    f"  판관비 {format_krw(l.krw.sga_expense)}, 영업이익 {format_krw(l.krw.operating_income)}",
                    f"  영업외수익 {format_krw(l.krw.non_operating_income)}, 영업외비용 {format_krw(l.krw.non_operating_expense)}, 세전이익 {format_krw(l.krw.pretax_income)}",
                    f"  당기순이익 {format_krw(l.krw.net_income)}",
                    f"  자산 {format_krw(l.krw.assets)}, 부채 {format_krw(l.krw.liabilities)}, 자본 {format_krw(l.krw.equity)}",
                    f"  [계산된 비율 — 그대로 인용할 것, 재계산 금지] 매출총이익률 {format_percent(l.gross_margin)} · 영업이익률 {format_percent(l.operating_margin)} · 순이익률 {format_percent(l.net_margin)}",
                    f"  비용 성격별(매출액 대비, 계산됨): 원재료비 {format_percent(raw_material_ratio)}, 인건비 {format_percent(labor_ratio)}, 상각비 {format_percent(depr_ratio)}, 금융비용 {format_percent(finance_ratio)}",
                ]
            )
        )

    return f"[기간: {period_label}, 통화: 원화(KRW) 환산 기준]\n" + "\n".join(lines)
