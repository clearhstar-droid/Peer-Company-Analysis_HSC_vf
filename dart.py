"""DART (전자공시시스템) OpenAPI integration — Korean domestic 3 companies.

Requires a free API key from https://opendart.fss.or.kr (회원가입 → "오픈API
이용신청") set as DART_API_KEY. Mirrors lib/sources/dart.ts, including four
bugs found and fixed against a real key during development (see
README.md "검증된 버그" section for the full story) — this Python port
carries the same fixes, don't reintroduce them:

  1. DART stores some names with the Latin brand spelling ("POSCO홀딩스", not
     "포스코홀딩스"). A loose substring fallback on the wrong hint matched an
     unrelated subsidiary ("포스코티엠씨"). List the verified real name first.
  2. Some companies (Dongkuk Steel post-2023 spin-off) have no CFS
     (consolidated) statement for a given period — fall back to OFS.
  3. `thstrm_amount` on a quarterly filing (Q1/H1/Q3 report types) is
     already the DISCRETE current period, not year-to-date;
     `thstrm_add_amount` is the cumulative. Only Q4 needs derivation:
     FY.thstrm_amount − Q3.thstrm_add_amount.
  4. The same account name can appear in the income statement (IS/CIS),
     cash-flow statement (CF), and equity-changes statement (SCE) sections
     with DIFFERENT values (CF's "당기순이익" starting line is often
     cumulative even on a quarterly filing) — every lookup MUST scope to
     the right section(s) via sj_div, never search the whole flat list.
  Equity is derived as assets − liabilities rather than label-matched:
  some interim filings only carry "부채및자본총계" (= total assets restated)
  and omit "자본총계" outright; a loose match previously picked up the
  former and silently set equity = assets.
"""

import io
import os
import re
import zipfile

import requests

from ..types import CostBreakdown, QuarterRecord

# DART's real stored names (verified live) come first; loose fallbacks after.
DART_NAME_HINTS = {
    "hyundai-steel": ["현대제철"],
    "posco": ["POSCO홀딩스", "포스코홀딩스"],
    "dongkuk": ["동국제강"],
}

REPRT_CODES = {"Q1": "11013", "H1": "11012", "Q3CUM": "11014", "FY": "11011"}

IS_SECTIONS = {"IS", "CIS"}
BS_SECTIONS = {"BS"}

ACCOUNT_MATCHERS = {
    "revenue": ["매출액", "수익(매출액)"],
    "cogs": ["매출원가"],
    "sga": ["판매비와관리비", "관리비및판매비", "판매비와 관리비"],
    "operating_income": ["영업이익"],
    "pretax_income": ["법인세비용차감전순이익", "법인세비용차감전순손익"],
    # Quarterly filings label this "분기순이익"/"반기순이익", not "당기순이익".
    "net_income": ["당기순이익", "당기순손익", "분기순이익", "반기순이익"],
    "assets": ["자산총계"],
    "liabilities": ["부채총계"],
}

FLOW_KEYS = ["revenue", "cogs", "sga", "operating_income", "pretax_income", "net_income"]

_corp_code_cache: list[dict] | None = None


def _load_corp_code_map(api_key: str) -> list[dict]:
    global _corp_code_cache
    if _corp_code_cache is not None:
        return _corp_code_cache

    res = requests.get(
        "https://opendart.fss.or.kr/api/corpCode.xml", params={"crtfc_key": api_key}, timeout=30
    )
    res.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        xml = zf.read(zf.namelist()[0]).decode("utf-8")

    entries = []
    for block in re.findall(r"<list>([\s\S]*?)</list>", xml):
        corp_code = re.search(r"<corp_code>(.*?)</corp_code>", block)
        corp_name = re.search(r"<corp_name>(.*?)</corp_name>", block)
        stock_code = re.search(r"<stock_code>(.*?)</stock_code>", block)
        if corp_code and stock_code and stock_code.group(1).strip():
            entries.append(
                {
                    "corp_code": corp_code.group(1),
                    "corp_name": corp_name.group(1) if corp_name else "",
                    "stock_code": stock_code.group(1).strip(),
                }
            )
    _corp_code_cache = entries
    return entries


def _resolve_corp_code(company_id: str, api_key: str) -> str | None:
    hints = DART_NAME_HINTS.get(company_id)
    if not hints:
        return None
    all_entries = _load_corp_code_map(api_key)
    for hint in hints:
        for e in all_entries:
            if e["corp_name"] == hint:
                return e["corp_code"]
    for hint in hints:
        for e in all_entries:
            if hint in e["corp_name"]:
                return e["corp_code"]
    return None


def _fetch_statement_with_div(api_key: str, corp_code: str, year: int, reprt_code: str, fs_div: str) -> list[dict] | None:
    res = requests.get(
        "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json",
        params={
            "crtfc_key": api_key,
            "corp_code": corp_code,
            "bsns_year": year,
            "reprt_code": reprt_code,
            "fs_div": fs_div,
        },
        timeout=20,
    )
    if not res.ok:
        return None
    data = res.json()
    if data.get("status") != "000":
        return None
    return data.get("list")


def _fetch_statement(api_key: str, corp_code: str, year: int, reprt_code: str) -> list[dict] | None:
    cfs = _fetch_statement_with_div(api_key, corp_code, year, reprt_code, "CFS")
    if cfs:
        return cfs
    return _fetch_statement_with_div(api_key, corp_code, year, reprt_code, "OFS")


def _to_millions(raw: str) -> float:
    return float(raw.replace(",", "")) / 1_000_000


def _find_amount(lines: list[dict], candidates: list[str], sj_divs: set[str], field: str = "thstrm_amount") -> float | None:
    scoped = [l for l in lines if l.get("sj_div") in sj_divs]
    for c in candidates:
        for l in scoped:
            if l.get("account_nm", "").replace(" ", "") == c.replace(" ", "") and l.get(field):
                return _to_millions(l[field])
    for c in candidates:
        for l in scoped:
            if c in l.get("account_nm", "") and l.get(field):
                return _to_millions(l[field])
    return None


def _extract_flow(lines: list[dict] | None) -> dict[str, float | None]:
    if lines is None:
        return {}
    return {k: _find_amount(lines, ACCOUNT_MATCHERS[k], IS_SECTIONS) for k in FLOW_KEYS}


def _extract_cumulative_flow(lines: list[dict] | None) -> dict[str, float | None]:
    if lines is None:
        return {}
    return {k: _find_amount(lines, ACCOUNT_MATCHERS[k], IS_SECTIONS, "thstrm_add_amount") for k in FLOW_KEYS}


def _extract_balance(lines: list[dict] | None) -> dict[str, float | None]:
    if lines is None:
        return {}
    assets = _find_amount(lines, ACCOUNT_MATCHERS["assets"], BS_SECTIONS)
    liabilities = _find_amount(lines, ACCOUNT_MATCHERS["liabilities"], BS_SECTIONS)
    equity = assets - liabilities if assets is not None and liabilities is not None else None
    return {"assets": assets, "liabilities": liabilities, "equity": equity}


def _subtract_flow(fy: dict, ninemonth_cum: dict) -> dict[str, float | None] | None:
    if not fy or not ninemonth_cum:
        return None
    out = {}
    for k in FLOW_KEYS:
        a, b = fy.get(k), ninemonth_cum.get(k)
        if a is None or b is None:
            return None
        out[k] = a - b
    return out


def fetch_dart_company(company_id: str, years: list[int], quarters: list[int]) -> tuple[list[QuarterRecord], list[str]]:
    api_key = os.environ.get("DART_API_KEY")
    notes: list[str] = []
    if not api_key:
        return [], ["DART_API_KEY가 설정되어 있지 않습니다."]

    try:
        corp_code = _resolve_corp_code(company_id, api_key)
    except requests.RequestException as err:
        return [], [f"DART corp_code 조회 실패: {err}"]
    if not corp_code:
        return [], ["DART corp_code를 찾지 못했습니다 (회사명 매칭 실패)."]

    records: list[QuarterRecord] = []

    for year in years:
        q1 = _fetch_statement(api_key, corp_code, year, REPRT_CODES["Q1"])
        h1 = _fetch_statement(api_key, corp_code, year, REPRT_CODES["H1"])
        q3cum = _fetch_statement(api_key, corp_code, year, REPRT_CODES["Q3CUM"])
        fy = _fetch_statement(api_key, corp_code, year, REPRT_CODES["FY"])

        discrete_by_quarter = {
            1: _extract_flow(q1),
            2: _extract_flow(h1),
            3: _extract_flow(q3cum),
            4: _subtract_flow(_extract_flow(fy), _extract_cumulative_flow(q3cum)),
        }
        balance_by_quarter = {
            1: _extract_balance(q1),
            2: _extract_balance(h1),
            3: _extract_balance(q3cum),
            4: _extract_balance(fy),
        }

        for quarter in quarters:
            flow = discrete_by_quarter.get(quarter)
            bal = balance_by_quarter.get(quarter)
            if not flow or not bal:
                continue
            if any(flow.get(k) is None for k in FLOW_KEYS):
                continue
            if any(bal.get(k) is None for k in ("assets", "liabilities", "equity")):
                continue

            non_op_net = flow["pretax_income"] - flow["operating_income"]
            non_op_income = max(0.0, non_op_net)
            non_op_expense = max(0.0, -non_op_net)
            tax_expense = flow["pretax_income"] - flow["net_income"]

            records.append(
                QuarterRecord(
                    company_id=company_id,
                    year=year,
                    quarter=quarter,
                    fx_to_krw=1.0,
                    revenue=flow["revenue"],
                    cogs=flow["cogs"],
                    sga_expense=flow["sga"],
                    non_operating_income=non_op_income,
                    non_operating_expense=non_op_expense,
                    tax_expense=tax_expense,
                    assets=bal["assets"],
                    liabilities=bal["liabilities"],
                    equity=bal["equity"],
                    cost_breakdown=CostBreakdown(),
                )
            )

    if not records:
        notes.append("공시 데이터를 찾았으나 계정 매칭에 실패했습니다 — ACCOUNT_MATCHERS 라벨을 실제 DART 응답과 대조해주세요.")
    return records, notes


def is_dart_covered(company_id: str) -> bool:
    return company_id in DART_NAME_HINTS
