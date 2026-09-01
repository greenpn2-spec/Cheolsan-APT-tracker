# -*- coding: utf-8 -*-
"""국토교통부 아파트매매 실거래가 Open API(data.go.kr) 연동 모듈."""

import xml.etree.ElementTree as ET
from datetime import date

import requests

ENDPOINT = (
    "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
)
TIMEOUT = 15


class MolitApiError(Exception):
    pass


def _parse_amount(text: str) -> int:
    if not text:
        return 0
    return int(text.replace(",", "").strip()) * 10_000  # 만원 -> 원


def _text(item: ET.Element, tag: str) -> str:
    el = item.find(tag)
    return el.text.strip() if el is not None and el.text else ""


def _text_any(item: ET.Element, *tags: str) -> str:
    """여러 후보 태그명 중 값이 있는 첫 번째를 반환.

    RTMSDataSvcAptTradeDev(상세자료) 응답은 aptNm/dealAmount/dealYear 같은
    영문 camelCase 태그를 쓰고, 기본(RTMSDataSvcAptTrade) 응답은 아파트/거래금액/년
    같은 한글 태그를 쓴다. 둘 다 대응하기 위해 후보를 순서대로 시도한다.
    """
    for tag in tags:
        value = _text(item, tag)
        if value:
            return value
    return ""


def fetch_trades_for_month(lawd_cd: str, deal_ymd: str, service_key: str,
                            num_of_rows: int = 1000) -> list:
    """단일 시군구코드/거래년월에 대한 아파트 매매 실거래 목록을 반환.

    반환 항목 dict: apt_name, deal_date, price(원), area_m2, floor, dong
    """
    params = {
        "serviceKey": service_key,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "pageNo": 1,
        "numOfRows": num_of_rows,
    }
    resp = requests.get(ENDPOINT, params=params, timeout=TIMEOUT)
    resp.raise_for_status()

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        raise MolitApiError(f"API 응답 파싱 실패: {e}") from e

    header = root.find("header")
    if header is not None:
        result_code = _text(header, "resultCode")
        result_msg = _text(header, "resultMsg")
        if result_code and result_code != "00":
            raise MolitApiError(f"API 오류({result_code}): {result_msg}")

    items = root.findall(".//item")
    results = []
    for item in items:
        apt_name = _text_any(item, "aptNm", "아파트")
        raw_amount = _text_any(item, "dealAmount", "거래금액")
        year = _text_any(item, "dealYear", "년")
        month = _text_any(item, "dealMonth", "월")
        day = _text_any(item, "dealDay", "일")
        area = _text_any(item, "excluUseAr", "전용면적")
        floor = _text_any(item, "floor", "층")
        dong = _text_any(item, "umdNm", "법정동")

        if not (apt_name and raw_amount and year and month and day):
            continue

        try:
            deal_date = date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            continue

        results.append(
            {
                "apt_name": apt_name,
                "deal_date": deal_date,
                "price": _parse_amount(raw_amount),
                "area_m2": float(area) if area else None,
                "floor": int(floor) if floor.lstrip("-").isdigit() else None,
                "dong": dong,
            }
        )
    return results


def filter_by_keywords(items: list, keywords: list) -> list:
    if not keywords:
        return items
    normalized_keywords = [k.replace(" ", "") for k in keywords]
    filtered = []
    for it in items:
        name = (it.get("apt_name") or "").replace(" ", "")
        if any(k in name for k in normalized_keywords):
            filtered.append(it)
    return filtered


def recent_year_months(months_back: int = 3) -> list:
    today = date.today()
    year, month = today.year, today.month
    out = []
    for _ in range(months_back):
        out.append(f"{year:04d}{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return out


def collect_transactions_for_complex(complex_key: str, lawd_cd: str, keywords: list,
                                      service_key: str, months_back: int = 3) -> tuple:
    """최근 N개월치 실거래가를 조회하여 keywords로 필터링 후
    db.insert_transactions에 바로 넣을 수 있는 dict 리스트로 반환.

    Returns (collected_rows, error_messages). 조회 중 오류가 나도 나머지 개월은
    계속 시도하되, 어떤 오류가 있었는지는 error_messages에 남겨서 화면에 보여줄 수
    있게 한다 (오류를 조용히 삼키지 않는다).
    """
    collected = []
    errors = []
    for ymd in recent_year_months(months_back):
        try:
            items = fetch_trades_for_month(lawd_cd, ymd, service_key)
        except requests.RequestException as e:
            errors.append(f"{ymd}: 네트워크 오류 ({e})")
            continue
        except MolitApiError as e:
            errors.append(f"{ymd}: {e}")
            continue
        matched = filter_by_keywords(items, keywords)
        for m in matched:
            m["complex_key"] = complex_key
        collected.extend(matched)
    return collected, errors
