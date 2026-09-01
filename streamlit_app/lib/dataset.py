"""Orchestrates per-company live-vs-sample data merging. Mirrors
app/api/financials/route.ts. Quarters are merged individually — a company
that partially fails still shows its real quarters, only the missing ones
fall back to sample data (never zero-filled, never faked)."""

from dataclasses import dataclass

from .companies import COMPANIES, QUARTERS, YEARS
from .mock_data import get_mock_data
from .sources.dart import fetch_dart_company, is_dart_covered
from .sources.edgar import fetch_edgar_company, is_edgar_covered
from .sources.fx import fetch_current_fx_to_krw
from .types import QuarterRecord

TOTAL_QUARTER_COUNT = len(YEARS) * len(QUARTERS)


@dataclass
class CompanySourceInfo:
    company_id: str
    provider: str  # "sec-edgar" | "dart" | "mock"
    status: str  # "live" | "partial" | "mock" | "error"
    live_quarter_count: int
    total_quarter_count: int
    notes: list[str]


def _fetch_live_for_company(company_id: str) -> tuple[list[QuarterRecord], list[str], str]:
    if is_edgar_covered(company_id):
        records, notes = fetch_edgar_company(company_id, YEARS, QUARTERS)
        return records, notes, "sec-edgar"
    if is_dart_covered(company_id):
        records, notes = fetch_dart_company(company_id, YEARS, QUARTERS)
        return records, notes, "dart"
    return [], ["실시간 소스 미지원"], "mock"


def load_dataset() -> tuple[list[QuarterRecord], dict[str, CompanySourceInfo]]:
    """Not cached itself — wrap the call site with st.cache_data so Streamlit
    controls the TTL/spinner without this module depending on Streamlit."""
    mock_all = get_mock_data()
    records: list[QuarterRecord] = []
    sources: dict[str, CompanySourceInfo] = {}

    for company in COMPANIES:
        mock_for_company = [r for r in mock_all if r.company_id == company.id]

        try:
            live_records, notes, provider = _fetch_live_for_company(company.id)
        except Exception as err:  # noqa: BLE001 - surface as a source note, don't crash the page
            live_records, notes, provider = [], [f"실시간 조회 오류: {err}"], "mock"

        fx = 0.0
        if live_records:
            fetched_fx = fetch_current_fx_to_krw(company.currency)
            fx = fetched_fx or 0.0

        live_has_fx = fx > 0
        for r in live_records:
            r.fx_to_krw = fx

        live_keys = {(r.year, r.quarter) for r in live_records} if live_has_fx else set()
        merged = list(live_records) if live_has_fx else []
        for m in mock_for_company:
            if (m.year, m.quarter) not in live_keys:
                merged.append(m)

        live_quarter_count = len(live_records) if live_has_fx else 0
        if live_quarter_count == 0:
            status = "error" if notes and provider != "mock" else "mock"
        elif live_quarter_count >= TOTAL_QUARTER_COUNT:
            status = "live"
        else:
            status = "partial"

        final_notes = list(notes) if live_has_fx else [*notes, *(["환율 조회 실패"] if live_records and fx == 0 else [])]

        sources[company.id] = CompanySourceInfo(
            company_id=company.id,
            provider=provider,
            status=status,
            live_quarter_count=live_quarter_count,
            total_quarter_count=TOTAL_QUARTER_COUNT,
            notes=final_notes,
        )
        records.extend(merged)

    return records, sources
