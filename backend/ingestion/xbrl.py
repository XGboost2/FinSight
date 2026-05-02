"""
XBRL financial facts fetcher.

Pulls structured financial data directly from SEC EDGAR's XBRL API.
No LLM needed — every figure is deterministic and machine-readable.

API: https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
"""

import logging
import httpx

logger = logging.getLogger(__name__)

FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
HEADERS = {"User-Agent": "FinSight kuralarasu.venkatesh@gmail.com"}

# Revenue concepts in priority order — companies use different XBRL tags
REVENUE_CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenueFromContractWithCustomerNetOfTax",
]


async def fetch_company_facts(cik: str) -> dict | None:
    url = FACTS_URL.format(cik=cik.zfill(10))
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error("XBRL fetch failed for CIK %s: %s", cik, e)
        return None


def _annual_values(us_gaap: dict, concept: str) -> list[dict]:
    """Return 10-K annual entries for a concept, newest first, deduplicated by period."""
    try:
        units = us_gaap[concept]["units"]
        unit_key = next(iter(units))
        entries = [
            e for e in units[unit_key]
            if e.get("form") in ("10-K", "10-K/A")
            and e.get("val", 0) != 0
        ]
        entries.sort(key=lambda x: x.get("end", ""), reverse=True)
        seen, deduped = set(), []
        for e in entries:
            if e["end"] not in seen:
                seen.add(e["end"])
                deduped.append(e)
        return deduped
    except (KeyError, StopIteration):
        return []


def _fmt_usd(val: float) -> str:
    sign = "-" if val < 0 else ""
    v = abs(val)
    if v >= 1e12:
        return f"{sign}${v/1e12:.2f}T"
    if v >= 1e9:
        return f"{sign}${v/1e9:.2f}B"
    if v >= 1e6:
        return f"{sign}${v/1e6:.1f}M"
    return f"{sign}${v:,.0f}"


def _yoy(current: float, prior: float) -> str | None:
    if not prior:
        return None
    pct = ((current - prior) / abs(prior)) * 100
    return f"+{pct:.1f}%" if pct >= 0 else f"{pct:.1f}%"


async def get_xbrl_metrics(cik: str) -> dict:
    """
    Return the 4 quantitative dashboard metrics from XBRL.
    Returns empty dict if XBRL data unavailable.
    """
    facts = await fetch_company_facts(cik)
    if not facts:
        return {}

    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    metrics = {}

    # Revenue + YoY
    for concept in REVENUE_CONCEPTS:
        values = _annual_values(us_gaap, concept)
        if values:
            current_rev = values[0]["val"]
            metrics["revenue_latest_year"] = _fmt_usd(current_rev)
            if len(values) > 1:
                metrics["revenue_yoy_change"] = _yoy(current_rev, values[1]["val"])
            break

    # Net Income
    values = _annual_values(us_gaap, "NetIncomeLoss")
    if values:
        metrics["net_income_latest_year"] = _fmt_usd(values[0]["val"])

    # Gross Margin (GrossProfit / Revenue)
    gp_values = _annual_values(us_gaap, "GrossProfit")
    if gp_values and "revenue_latest_year" in metrics:
        for concept in REVENUE_CONCEPTS:
            rev_values = _annual_values(us_gaap, concept)
            if rev_values and rev_values[0]["val"]:
                margin = (gp_values[0]["val"] / rev_values[0]["val"]) * 100
                metrics["gross_margin_pct"] = f"{margin:.1f}%"
                break

    logger.info(
        "XBRL metrics: CIK=%s revenue=%s net_income=%s margin=%s yoy=%s",
        cik,
        metrics.get("revenue_latest_year", "—"),
        metrics.get("net_income_latest_year", "—"),
        metrics.get("gross_margin_pct", "—"),
        metrics.get("revenue_yoy_change", "—"),
    )
    return metrics
