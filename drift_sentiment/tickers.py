"""Ticker search for the autocomplete box.

Matches the user's typed value against the symbol first, then the company
name, and returns the best few candidates. Uses Massive's reference-tickers
endpoint as the source, with a small offline fallback so the box still works
if that endpoint is unavailable or rate-limited.
"""

from __future__ import annotations

import requests

from .polygon_client import BASE_URL, PolygonError, _headers

# Small offline fallback (symbol, name) — popular US names. Keeps autocomplete
# useful even without a live reference API response.
_FALLBACK: list[tuple[str, str]] = [
    ("AAPL", "Apple Inc."), ("MSFT", "Microsoft Corporation"),
    ("AMZN", "Amazon.com Inc."), ("NVDA", "NVIDIA Corporation"),
    ("GOOGL", "Alphabet Inc. (Class A)"), ("GOOG", "Alphabet Inc. (Class C)"),
    ("META", "Meta Platforms Inc."), ("TSLA", "Tesla Inc."),
    ("BRK.B", "Berkshire Hathaway Inc."), ("JPM", "JPMorgan Chase & Co."),
    ("V", "Visa Inc."), ("MA", "Mastercard Incorporated"),
    ("UNH", "UnitedHealth Group Inc."), ("HD", "The Home Depot Inc."),
    ("PG", "Procter & Gamble Company"), ("XOM", "Exxon Mobil Corporation"),
    ("CVX", "Chevron Corporation"), ("KO", "The Coca-Cola Company"),
    ("PEP", "PepsiCo Inc."), ("COST", "Costco Wholesale Corporation"),
    ("WMT", "Walmart Inc."), ("DIS", "The Walt Disney Company"),
    ("NFLX", "Netflix Inc."), ("AMD", "Advanced Micro Devices Inc."),
    ("INTC", "Intel Corporation"), ("BA", "The Boeing Company"),
    ("NKE", "NIKE Inc."), ("CRM", "Salesforce Inc."),
    ("ORCL", "Oracle Corporation"), ("ADBE", "Adobe Inc."),
    ("PYPL", "PayPal Holdings Inc."), ("BAC", "Bank of America Corporation"),
    ("WFC", "Wells Fargo & Company"), ("GS", "The Goldman Sachs Group Inc."),
    ("PFE", "Pfizer Inc."), ("MRNA", "Moderna Inc."),
    ("T", "AT&T Inc."), ("VZ", "Verizon Communications Inc."),
    ("SPY", "SPDR S&P 500 ETF Trust"), ("QQQ", "Invesco QQQ Trust"),
    ("IWM", "iShares Russell 2000 ETF"), ("DIA", "SPDR Dow Jones Industrial Average ETF"),
    ("GLD", "SPDR Gold Shares"), ("SLV", "iShares Silver Trust"),
    ("PLTR", "Palantir Technologies Inc."), ("COIN", "Coinbase Global Inc."),
    ("UBER", "Uber Technologies Inc."), ("SHOP", "Shopify Inc."),
    ("SOFI", "SoFi Technologies Inc."), ("F", "Ford Motor Company"),
]


def _search_massive(q: str, *, timeout: int) -> list[dict]:
    """Query Massive's reference-tickers endpoint (Polygon-compatible)."""
    url = f"{BASE_URL}/v3/reference/tickers"
    params = {"search": q, "market": "stocks", "active": "true", "limit": 30}
    resp = requests.get(url, params=params, headers=_headers(), timeout=timeout)
    if resp.status_code != 200:
        raise PolygonError(f"Ticker search failed ({resp.status_code}).")
    out: list[dict] = []
    for r in resp.json().get("results", []):
        t = r.get("ticker")
        if not t:
            continue
        out.append({"ticker": t, "name": r.get("name") or "", "type": r.get("type") or ""})
    return out


def _search_fallback(q: str) -> list[dict]:
    ql = q.lower()
    return [
        {"ticker": t, "name": n, "type": ""}
        for t, n in _FALLBACK
        if ql in t.lower() or ql in n.lower()
    ]


def _rank(q: str, results: list[dict]) -> list[dict]:
    """Rank symbol matches ahead of name matches; de-duplicate by ticker."""
    ql = q.lower()

    def key(item: dict) -> tuple:
        t = item["ticker"].lower()
        n = item["name"].lower()
        if t == ql:
            group = 0
        elif t.startswith(ql):
            group = 1
        elif ql in t:
            group = 2
        elif n.startswith(ql):
            group = 3
        elif ql in n:
            group = 4
        else:
            group = 5
        return (group, len(item["ticker"]), item["ticker"])

    seen: dict[str, dict] = {}
    for it in results:
        seen.setdefault(it["ticker"], it)
    return sorted(seen.values(), key=key)


def search_tickers(query: str, *, limit: int = 8, timeout: int = 15) -> list[dict]:
    """Return up to `limit` ticker candidates for `query` (symbol first, name next)."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        results = _search_massive(q, timeout=timeout)
    except Exception:
        results = []
    if not results:
        results = _search_fallback(q)
    return _rank(q, results)[:limit]
