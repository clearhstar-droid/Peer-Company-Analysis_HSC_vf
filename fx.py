"""Free, no-key FX rates (Frankfurter.app, ECB-sourced). Applies a single
*current* rate uniformly across all quarters — not period-specific. Mirrors
lib/sources/fx.ts."""

import requests


def fetch_current_fx_to_krw(currency: str) -> float | None:
    if currency == "KRW":
        return 1.0
    try:
        res = requests.get(
            "https://api.frankfurter.app/latest",
            params={"from": currency, "to": "KRW"},
            timeout=10,
        )
        if not res.ok:
            return None
        rate = res.json().get("rates", {}).get("KRW")
        return float(rate) if rate is not None else None
    except requests.RequestException:
        return None
