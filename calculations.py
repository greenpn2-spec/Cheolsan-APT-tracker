# -*- coding: utf-8 -*-
"""핵심 연산 로직 (순자산, 가용자본, 대출한도, 갭 계산)."""

from config import (
    LTV_PRICE_THRESHOLD,
    LOAN_LIMIT_OVER_15EOK,
    LOAN_LIMIT_UNDER_15EOK,
    PURCHASE_COST_RATE,
    LOW_FLOOR_DISCOUNT,
)


def adjust_dusan_price(price: int, is_low_floor: bool):
    """구로 두산(실보유 저층 3층 매물) 전용 보정.

    두산은 실제로 저층을 보유하고 있어 시세/실거래가를 그대로 반영하면 고평가
    오류가 생긴다. 체크(기본값, 저층가 기준으로 입력함) 시 입력가를 그대로 쓰고,
    체크 해제(중고층 실거래가 등을 참고해 그대로 입력한 경우) 시에만 -10% 보정하여
    저층 등가로 환산한다. 다른 3개 가격(철산13/12단지 호가, 부천보람 매도가)에는
    이 보정을 적용하지 않는다 — 배지 표시용 정보일 뿐이다.

    Returns (adjusted_price, reference_original_price_or_None).
    """
    if is_low_floor:
        return price, None
    adjusted = round(price * (1 - LOW_FLOOR_DISCOUNT))
    return adjusted, price


def loan_limit_for(target_price: int) -> int:
    if target_price > LTV_PRICE_THRESHOLD:
        return LOAN_LIMIT_OVER_15EOK
    return LOAN_LIMIT_UNDER_15EOK


def target_metrics(target_price: int, total_available_capital: int) -> dict:
    loan_limit = loan_limit_for(target_price)
    purchase_cost = round(target_price * PURCHASE_COST_RATE)
    total_required = target_price + purchase_cost
    total_with_loan = total_available_capital + loan_limit
    shortfall = total_required - total_with_loan
    rate = (total_with_loan / total_required * 100) if total_required > 0 else 0.0
    return {
        "target_price": target_price,
        "loan_limit": loan_limit,
        "purchase_cost": purchase_cost,
        "total_required": total_required,
        "total_with_loan": total_with_loan,
        "shortfall": shortfall,
        "rate": rate,
        "over_15eok": target_price > LTV_PRICE_THRESHOLD,
        "achievable": shortfall <= 0,
    }


def compute_metrics(record: dict) -> dict:
    """record: 원 단위 raw 입력값 dict (db.MONTHLY_FIELDS 키 포함).

    저층 보정(-10%)은 실보유 저층 매물인 구로두산에만 적용한다. 철산13/12단지
    호가와 부천보람 매도가는 입력값을 그대로 사용하고, 저층 체크박스는 참고용
    배지로만 표시한다.
    """
    dusan_adj, dusan_ref = adjust_dusan_price(
        record.get("dusan_price", 0), bool(record.get("dusan_low_floor", 1))
    )
    t13_price = record.get("t13_price", 0)
    t12_price = record.get("t12_price", 0)
    boram_price = record.get("boram_price", 0)

    loans = record.get("loan_self", 0) + record.get("loan_spouse", 0)
    net_equity = dusan_adj + boram_price - loans

    cash = record.get("cash_self", 0) + record.get("cash_spouse", 0)
    reserve_fund = record.get("reserve_fund", 0)
    available_cash = cash - reserve_fund

    total_available_capital = net_equity + available_cash

    return {
        "dusan_adjusted": dusan_adj,
        "dusan_reference_original": dusan_ref,
        "net_equity": net_equity,
        "available_cash": available_cash,
        "total_available_capital": total_available_capital,
        "t13": target_metrics(t13_price, total_available_capital),
        "t12": target_metrics(t12_price, total_available_capital),
    }


def format_krw_eok(amount: int) -> str:
    """원 단위 금액을 '15억 3,000만원' 형태 문자열로 변환."""
    sign = "-" if amount < 0 else ""
    amount = abs(int(amount))
    eok = amount // 100_000_000
    man = (amount % 100_000_000) // 10_000
    parts = []
    if eok:
        parts.append(f"{eok}억")
    if man or not parts:
        parts.append(f"{man:,}만")
    return sign + " ".join(parts) + "원"
