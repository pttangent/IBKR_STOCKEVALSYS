#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_http import request_bytes, request_json, source_packet, utc_now_iso, write_json

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_COMPANYFACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{primary_document}"

CANONICAL_CONCEPTS: dict[str, tuple[tuple[str, str], ...]] = {
    "revenue": (
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("us-gaap", "Revenues"),
        ("us-gaap", "SalesRevenueNet"),
    ),
    "gross_profit": (("us-gaap", "GrossProfit"),),
    "operating_income": (("us-gaap", "OperatingIncomeLoss"),),
    "net_income": (("us-gaap", "NetIncomeLoss"), ("us-gaap", "ProfitLoss")),
    "eps_diluted": (("us-gaap", "EarningsPerShareDiluted"),),
    "cash_and_equivalents": (
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
        ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    ),
    "assets": (("us-gaap", "Assets"),),
    "liabilities": (("us-gaap", "Liabilities"),),
    "equity": (
        ("us-gaap", "StockholdersEquity"),
        ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    ),
    "long_term_debt": (
        ("us-gaap", "LongTermDebtNoncurrent"),
        ("us-gaap", "LongTermDebtAndFinanceLeaseObligationsNoncurrent"),
    ),
    "current_debt": (
        ("us-gaap", "LongTermDebtCurrent"),
        ("us-gaap", "ShortTermBorrowings"),
    ),
    "operating_cash_flow": (("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),),
    "capex": (
        ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
        ("us-gaap", "PaymentsForAdditionsToPropertyPlantAndEquipment"),
    ),
    "shares_outstanding": (("dei", "EntityCommonStockSharesOutstanding"),),
}

ALLOWED_FORMS = {"10-K", "10-Q", "8-K", "4", "424B5", "S-3ASR", "FWP", "SC 13D", "SC 13G", "SC 13D/A", "SC 13G/A"}


def _headers_for(url: str, user_agent: str) -> dict[str, str]:
    # Do not force data.sec.gov Host when requesting www.sec.gov/archive paths.
    headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
    if "data.sec.gov" in url:
        headers["Host"] = "data.sec.gov"
    return headers


def normalize_cik(value: str | int) -> str:
    digits = re.sub(r"\D", "", str(value))
    if not digits:
        raise ValueError(f"Invalid CIK: {value!r}")
    return digits.zfill(10)


def resolve_ticker(symbol: str, user_agent: str) -> dict[str, Any]:
    payload = request_json(SEC_TICKERS_URL, headers=_headers_for(SEC_TICKERS_URL, user_agent))
    target = symbol.strip().upper()
    rows = payload.values() if isinstance(payload, dict) else payload
    for row in rows:
        if str(row.get("ticker", "")).upper() == target:
            return {
                "ticker": target,
                "cik": normalize_cik(row.get("cik_str")),
                "company_name": row.get("title"),
            }
    raise RuntimeError(f"SEC ticker map contains no exact ticker match for {target}")


def get_submissions(cik: str, user_agent: str) -> dict[str, Any]:
    url = SEC_SUBMISSIONS.format(cik=normalize_cik(cik))
    return request_json(url, headers=_headers_for(url, user_agent))


def get_companyfacts(cik: str, user_agent: str) -> dict[str, Any]:
    url = SEC_COMPANYFACTS.format(cik=normalize_cik(cik))
    return request_json(url, headers=_headers_for(url, user_agent))


def _recent_rows(submissions: dict[str, Any]) -> list[dict[str, Any]]:
    recent = ((submissions.get("filings") or {}).get("recent") or {})
    if not isinstance(recent, dict) or not recent:
        return []
    keys = list(recent.keys())
    length = max((len(v) for v in recent.values() if isinstance(v, list)), default=0)
    rows = []
    for idx in range(length):
        row = {}
        for key in keys:
            values = recent.get(key)
            row[key] = values[idx] if isinstance(values, list) and idx < len(values) else None
        rows.append(row)
    return rows


def recent_filings(
    submissions: dict[str, Any],
    *,
    as_of: str | None = None,
    forms: set[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    wanted = forms or ALLOWED_FORMS
    cutoff = as_of or "9999-12-31"
    rows = []
    for row in _recent_rows(submissions):
        form = row.get("form")
        filed = row.get("filingDate") or ""
        if form in wanted and filed <= cutoff:
            rows.append(row)
    rows.sort(key=lambda r: ((r.get("filingDate") or ""), (r.get("acceptanceDateTime") or "")), reverse=True)
    return rows[:limit]


def filing_document_url(cik: str, filing: dict[str, Any]) -> str | None:
    accession = str(filing.get("accessionNumber") or "")
    primary = str(filing.get("primaryDocument") or "")
    if not accession or not primary:
        return None
    return SEC_ARCHIVES.format(
        cik_int=int(normalize_cik(cik)),
        accession_nodash=accession.replace("-", ""),
        primary_document=quote(primary, safe="/"),
    )


def _facts_for_concept(companyfacts: dict[str, Any], taxonomy: str, concept: str) -> list[dict[str, Any]]:
    concept_payload = (((companyfacts.get("facts") or {}).get(taxonomy) or {}).get(concept) or {})
    units = concept_payload.get("units") or {}
    rows: list[dict[str, Any]] = []
    for unit, values in units.items():
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            rows.append({**item, "unit": unit, "taxonomy": taxonomy, "concept": concept})
    return rows


def _latest_reported_fact(
    companyfacts: dict[str, Any],
    concepts: tuple[tuple[str, str], ...],
    *,
    as_of: str | None,
) -> dict[str, Any] | None:
    cutoff = as_of or "9999-12-31"
    candidates: list[dict[str, Any]] = []
    for taxonomy, concept in concepts:
        for row in _facts_for_concept(companyfacts, taxonomy, concept):
            filed = str(row.get("filed") or "")
            form = str(row.get("form") or "")
            if filed and filed <= cutoff and form in {"10-K", "10-Q", "8-K", "20-F", "40-F", "6-K"}:
                candidates.append(row)
    if not candidates:
        return None
    # Prefer the latest information actually filed by the cutoff, then the latest period end.
    candidates.sort(
        key=lambda r: (
            str(r.get("filed") or ""),
            str(r.get("end") or ""),
            bool(r.get("frame")),
            str(r.get("frame") or ""),
        ),
        reverse=True,
    )
    return candidates[0]


def _candidate_rows(
    companyfacts: dict[str, Any],
    concepts: tuple[tuple[str, str], ...],
    *,
    as_of: str | None,
) -> list[dict[str, Any]]:
    cutoff = as_of or "9999-12-31"
    rows: list[dict[str, Any]] = []
    for taxonomy, concept in concepts:
        for row in _facts_for_concept(companyfacts, taxonomy, concept):
            filed = str(row.get("filed") or "")
            form = str(row.get("form") or "")
            if filed and filed <= cutoff and form in {"10-K", "10-Q", "8-K", "20-F", "40-F", "6-K"}:
                rows.append(row)
    return rows


def _group_key(row: dict[str, Any], *, instant: bool) -> tuple[str, ...]:
    accession = str(row.get("accn") or "")
    filed = str(row.get("filed") or "")
    form = str(row.get("form") or "")
    end = str(row.get("end") or "")
    start = "" if instant else str(row.get("start") or "")
    # Accession is the strongest filing identity. The remaining fields keep
    # synthetic/older companyfacts rows deterministic when accn is absent.
    return (accession, filed, form, start, end)


def _select_period_group(
    rows_by_canonical: dict[str, list[dict[str, Any]]],
    *,
    required: tuple[str, ...],
    instant: bool,
) -> tuple[tuple[str, ...] | None, dict[tuple[str, ...], list[dict[str, Any]]]]:
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for rows in rows_by_canonical.values():
        for row in rows:
            groups.setdefault(_group_key(row, instant=instant), []).append(row)
    if not groups:
        return None, groups

    def rank(item: tuple[tuple[str, ...], list[dict[str, Any]]]) -> tuple[int, str, str, int]:
        key, rows = item
        concepts = {str(row.get("canonical_key") or "") for row in rows}
        latest_filed = max((str(row.get("filed") or "") for row in rows), default="")
        latest_end = max((str(row.get("end") or "") for row in rows), default="")
        return (len(concepts.intersection(required)), latest_filed, latest_end, len(rows))

    selected = max(groups.items(), key=rank)[0]
    return selected, groups


def extract_canonical_financials(companyfacts: dict[str, Any], as_of: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    missing: list[str] = []
    duration_keys = ("revenue", "gross_profit", "operating_income", "net_income", "eps_diluted", "operating_cash_flow", "capex")
    instant_keys = tuple(key for key in CANONICAL_CONCEPTS if key not in duration_keys)
    duration_rows: dict[str, list[dict[str, Any]]] = {}
    instant_rows: dict[str, list[dict[str, Any]]] = {}
    for canonical, concepts in CANONICAL_CONCEPTS.items():
        rows = _candidate_rows(companyfacts, concepts, as_of=as_of)
        for row in rows:
            row["canonical_key"] = canonical
        (duration_rows if canonical in duration_keys else instant_rows)[canonical] = rows

    duration_required = ("revenue", "gross_profit", "net_income", "operating_cash_flow")
    instant_required = ("cash_and_equivalents", "assets", "liabilities", "equity")
    duration_group, duration_groups = _select_period_group(duration_rows, required=duration_required, instant=False)
    instant_group, instant_groups = _select_period_group(instant_rows, required=instant_required, instant=True)

    def selected_row(canonical: str, rows: list[dict[str, Any]], group: tuple[str, ...] | None) -> dict[str, Any] | None:
        matching = [row for row in rows if group is not None and _group_key(row, instant=canonical in instant_keys) == group]
        if not matching:
            return None
        matching.sort(key=lambda row: (str(row.get("filed") or ""), bool(row.get("frame")), str(row.get("frame") or "")), reverse=True)
        return matching[0]

    for canonical, concepts in CANONICAL_CONCEPTS.items():
        rows = (instant_rows if canonical in instant_keys else duration_rows).get(canonical, [])
        group = instant_group if canonical in instant_keys else duration_group
        row = selected_row(canonical, rows, group)
        if row is None:
            missing.append(canonical)
            continue
        out[canonical] = {
            "value": row.get("val"),
            "unit": row.get("unit"),
            "period_start": row.get("start"),
            "period_end": row.get("end"),
            "filed": row.get("filed"),
            "form": row.get("form"),
            "fiscal_year": row.get("fy"),
            "fiscal_period": row.get("fp"),
            "frame": row.get("frame"),
            "accession": row.get("accn"),
            "xbrl_taxonomy": row.get("taxonomy"),
            "xbrl_concept": row.get("concept"),
            "evidence_label": "FACT",
        }
    duration_concepts = {str(row.get("canonical_key")) for row in duration_groups.get(duration_group, [])} if duration_group else set()
    instant_concepts = {str(row.get("canonical_key")) for row in instant_groups.get(instant_group, [])} if instant_group else set()
    duration_valid = bool(duration_group and set(duration_required).issubset(duration_concepts))
    instant_valid = bool(instant_group and set(instant_required).issubset(instant_concepts))
    return {
        "facts": out,
        "missing_canonical_fields": missing,
        "quality": {
            "duration_period_alignment": duration_valid,
            "duration_group": {
                "accession": duration_group[0] if duration_group else None,
                "filed": duration_group[1] if duration_group else None,
                "form": duration_group[2] if duration_group else None,
                "period_start": duration_group[3] if duration_group else None,
                "period_end": duration_group[4] if duration_group else None,
                "concepts": sorted(duration_concepts),
            },
            "instant_filing_alignment": instant_valid,
            "instant_group": {
                "accession": instant_group[0] if instant_group else None,
                "filed": instant_group[1] if instant_group else None,
                "form": instant_group[2] if instant_group else None,
                "instant": instant_group[4] if instant_group else None,
                "concepts": sorted(instant_concepts),
            },
            "ratio_safe": duration_valid,
            "policy": "duration ratios require one accession/start/end/form group; balance-sheet facts require one latest filing/instant group",
        },
    }


def _text(root: ET.Element, tag: str) -> str | None:
    node = root.find(f".//{tag}")
    return node.text.strip() if node is not None and node.text else None


def parse_form4_xml(xml_text: str) -> dict[str, Any]:
    root = ET.fromstring(xml_text)
    issuer = {
        "cik": _text(root, "issuerCik"),
        "name": _text(root, "issuerName"),
        "ticker": _text(root, "issuerTradingSymbol"),
    }
    owner = {
        "cik": _text(root, "rptOwnerCik"),
        "name": _text(root, "rptOwnerName"),
        "is_director": _text(root, "isDirector"),
        "is_officer": _text(root, "isOfficer"),
        "is_ten_percent_owner": _text(root, "isTenPercentOwner"),
        "officer_title": _text(root, "officerTitle"),
    }
    transactions: list[dict[str, Any]] = []
    for txn in root.findall(".//nonDerivativeTransaction"):
        def t(path: str) -> str | None:
            node = txn.find(path)
            return node.text.strip() if node is not None and node.text else None

        transactions.append(
            {
                "security_title": t("securityTitle/value"),
                "transaction_date": t("transactionDate/value"),
                "transaction_code": t("transactionCoding/transactionCode"),
                "equity_swap_involved": t("transactionCoding/equitySwapInvolved"),
                "shares": t("transactionAmounts/transactionShares/value"),
                "price": t("transactionAmounts/transactionPricePerShare/value"),
                "acquired_disposed": t("transactionAmounts/transactionAcquiredDisposedCode/value"),
                "post_transaction_shares": t("postTransactionAmounts/sharesOwnedFollowingTransaction/value"),
                "ownership_nature": t("ownershipNature/directOrIndirectOwnership/value"),
            }
        )
    return {
        "issuer": issuer,
        "reporting_owner": owner,
        "period_of_report": _text(root, "periodOfReport"),
        "transactions": transactions,
        "warning": "Transaction codes require context; grants/exercises/tax withholding must not be treated as directional insider conviction.",
    }


def fetch_form4_details(cik: str, filings: list[dict[str, Any]], user_agent: str, limit: int) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    count = 0
    for filing in filings:
        if filing.get("form") != "4" or count >= limit:
            continue
        url = filing_document_url(cik, filing)
        if not url:
            continue
        try:
            raw = request_bytes(url, headers=_headers_for(url, user_agent), retries=1)
            text = raw.decode("utf-8", errors="replace")
            # Ownership forms normally expose XML as the primary document. If HTML wraps XML,
            # retain metadata and fail gracefully rather than fabricating parsed fields.
            if "<ownershipDocument" not in text:
                output.append({"filing": filing, "url": url, "parsed": None, "warning": "primary document is not ownership XML"})
            else:
                start = text.find("<ownershipDocument")
                end = text.rfind("</ownershipDocument>")
                xml = text[start : end + len("</ownershipDocument>")]
                output.append({"filing": filing, "url": url, "parsed": parse_form4_xml(xml)})
        except Exception as exc:  # individual filing failure should not discard the SEC packet
            output.append({"filing": filing, "url": url, "parsed": None, "warning": str(exc)})
        count += 1
    return output


def download_primary_documents(cik: str, filings: list[dict[str, Any]], user_agent: str, output_dir: Path) -> list[dict[str, Any]]:
    """Freeze primary SEC documents locally so replay does not depend on URLs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    captured: list[dict[str, Any]] = []
    for filing in filings:
        if filing.get("form") == "4":
            continue
        url = filing_document_url(cik, filing)
        if not url:
            continue
        accession = str(filing.get("accessionNumber") or "unknown").replace("-", "")
        primary = Path(str(filing.get("primaryDocument") or "document")).name
        target = output_dir / f"{accession}_{primary}"
        try:
            raw = request_bytes(url, headers=_headers_for(url, user_agent), retries=1)
            target.write_bytes(raw)
            captured.append({
                "form": filing.get("form"),
                "filing_date": filing.get("filingDate"),
                "acceptance_date_time": filing.get("acceptanceDateTime"),
                "accession_number": filing.get("accessionNumber"),
                "url": url,
                "path": str(target),
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "status": "captured",
            })
        except Exception as exc:
            captured.append({
                "form": filing.get("form"),
                "filing_date": filing.get("filingDate"),
                "acceptance_date_time": filing.get("acceptanceDateTime"),
                "accession_number": filing.get("accessionNumber"),
                "url": url,
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })
    return captured


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch PIT-safe SEC research evidence for one US-listed company.")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--as-of", help="YYYY-MM-DD filing cutoff; defaults to today")
    ap.add_argument("--output", required=True)
    ap.add_argument("--filing-limit", type=int, default=40)
    ap.add_argument("--form4-limit", type=int, default=5)
    ap.add_argument("--skip-companyfacts", action="store_true")
    ap.add_argument("--download-primary-documents-dir", help="directory for frozen SEC primary documents")
    args = ap.parse_args()

    as_of = args.as_of or date.today().isoformat()
    user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if len(user_agent) < 10:
        raise SystemExit('Missing/descriptively short SEC_USER_AGENT; set e.g. "IBKR_STOCKEVALSYS research@example.com"')
    identity = resolve_ticker(args.symbol, user_agent)
    cik = identity["cik"]
    submissions = get_submissions(cik, user_agent)
    filings = recent_filings(submissions, as_of=as_of, limit=args.filing_limit)
    companyfacts = None if args.skip_companyfacts else get_companyfacts(cik, user_agent)
    form4 = fetch_form4_details(cik, filings, user_agent, args.form4_limit)
    captured_documents = download_primary_documents(cik, filings, user_agent, Path(args.download_primary_documents_dir)) if args.download_primary_documents_dir else []

    data: dict[str, Any] = {
        "identity": identity,
        "entity_metadata": {
            "name": submissions.get("name"),
            "sic": submissions.get("sic"),
            "sic_description": submissions.get("sicDescription"),
            "tickers": submissions.get("tickers"),
            "exchanges": submissions.get("exchanges"),
        },
        "recent_filings": [
            {**f, "document_url": filing_document_url(cik, f)} for f in filings
        ],
        "canonical_financials": extract_canonical_financials(companyfacts, as_of) if companyfacts else None,
        "form4": form4,
        "captured_primary_documents": captured_documents,
    }
    packet = source_packet(
        provider="SEC_EDGAR",
        source_type="primary_filings_xbrl_insider",
        source_id=f"sec:{identity['ticker']}:{as_of}",
        as_of=as_of,
        # Each included filing/fact is filtered by filed date <= as_of; packet availability is therefore bounded by the cutoff.
        available_at=as_of,
        reliability="primary",
        source_url=SEC_SUBMISSIONS.format(cik=cik),
        data=data,
        warnings=[
            "Canonical XBRL mapping is best-effort; sector-specific KPIs and non-GAAP measures still require filing/IR review.",
            "Form 4 transactions are context evidence, not automatic bullish/bearish signals.",
        ],
        metadata={"cik": cik, "companyfacts_included": companyfacts is not None},
    )
    write_json(args.output, packet)
    print(f"OK SEC {identity['ticker']} CIK={cik} filings={len(filings)} form4={len(form4)} -> {args.output}")


if __name__ == "__main__":
    main()
