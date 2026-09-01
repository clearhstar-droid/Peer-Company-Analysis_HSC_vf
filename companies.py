"""Peer company roster. Kept in sync with the Next.js version's lib/companies.ts —
same 6 companies (China/Japan/ArcelorMittal dropped: no working free data source)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Company:
    id: str
    name_ko: str
    name_en: str
    region: str
    currency: str  # "KRW" | "USD"
    is_self: bool
    accounting_standard: str


COMPANIES: list[Company] = [
    Company("hyundai-steel", "현대제철", "Hyundai Steel", "한국", "KRW", True, "K-IFRS"),
    Company("posco", "POSCO홀딩스", "POSCO Holdings", "한국", "KRW", False, "K-IFRS"),
    Company("dongkuk", "동국제강", "Dongkuk Steel", "한국", "KRW", False, "K-IFRS"),
    Company("nucor", "뉴코", "Nucor", "미국", "USD", False, "US GAAP"),
    Company("cleveland-cliffs", "클리블랜드클리프스", "Cleveland-Cliffs", "미국", "USD", False, "US GAAP"),
    Company("us-steel", "US스틸", "US Steel", "미국", "USD", False, "US GAAP"),
]

COMPANY_MAP: dict[str, Company] = {c.id: c for c in COMPANIES}

YEARS = [2023, 2024, 2025]
QUARTERS = [1, 2, 3, 4]
