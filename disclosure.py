"""TDnet適時開示の取得と銘柄への紐付け。"""

import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

from settings import Disclosure

_CODE_PATTERN = re.compile(r"^(\d{4,5})")


def _normalize_code(raw: str) -> str | None:
    """TDnetの5桁コード（末尾0）を4桁に正規化する。ETFコード等は除外。"""
    m = _CODE_PATTERN.match(raw.strip())
    if not m:
        return None
    code = m.group(1)
    if len(code) == 5 and code.endswith("0"):
        return code[:4]
    if len(code) == 4:
        return code
    return None


def fetch_tdnet_disclosures(days: int = 3) -> list[dict]:
    """TDnet HTMLから直近N日分の適時開示を取得する。"""
    disclosures = []
    for d in range(days):
        date = datetime.now() - timedelta(days=d)
        if date.weekday() >= 5:
            continue
        date_str = date.strftime("%Y%m%d")
        url = f"https://www.release.tdnet.info/inbs/I_list_001_{date_str}.html"
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "StockScreener/1.0"})
            resp.encoding = "utf-8"
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for row in soup.select("tr"):
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue
                time_text = cells[0].get_text(strip=True)
                code_text = cells[1].get_text(strip=True)
                company = cells[2].get_text(strip=True)
                title = cells[3].get_text(strip=True)
                link_tag = cells[3].find("a")
                link = link_tag["href"] if link_tag and link_tag.has_attr("href") else ""

                code = _normalize_code(code_text)
                if not code:
                    continue

                disclosures.append({
                    "code": code,
                    "company": company,
                    "title": title,
                    "link": link,
                    "date": date_str,
                    "time": time_text,
                })
        except Exception:
            continue
    return disclosures


def classify_disclosure(title: str) -> str | None:
    """開示タイトルから材料キーワードを抽出する。"""
    for kw in Disclosure.keywords:
        if kw in title:
            return kw
    return None


def get_disclosures_for_codes(codes: list[str]) -> dict[str, list[dict]]:
    """銘柄コードごとに適時開示を紐付ける。"""
    code_set = set(codes)
    disclosures = fetch_tdnet_disclosures()

    result: dict[str, list[dict]] = {}
    for d in disclosures:
        code = d.get("code")
        if code and code in code_set:
            d["keyword"] = classify_disclosure(d["title"])
            result.setdefault(code, []).append(d)

    return result


def format_disclosure_summary(disclosures: list[dict]) -> str:
    """銘柄に紐付いた開示の要約文字列を返す。"""
    if not disclosures:
        return ""
    keywords = set()
    for d in disclosures:
        kw = d.get("keyword")
        if kw:
            keywords.add(kw)
    if keywords:
        return "、".join(sorted(keywords))
    return f"開示{len(disclosures)}件"
