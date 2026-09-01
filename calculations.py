# -*- coding: utf-8 -*-
"""핵심 연산 로직 (순자산, 가용자본, 대출한도, 갭 계산)."""

from config import (
    LTV_PRICE_THRESHOLD,
    LOAN_LIMIT_OVER_15EOK,
    LOAN_LIMIT_UNDER_15EOK,
    PURCHASE_COST_RATE,
    LOW_FLOOR_DISCOUNT,
)


def adjust_low_floor_price(price: int, is_low_floor: bool):
    """저층 여부 체크 시 입력가 그대로 사용, 저층이 아닐 경우에만 -10% 보정하여
    저층가로 환산한다.

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

    4개 가격(13단지 호가/12단지 호가/두산 매도가/보람 매도가) 모두 동일한 규칙으로
    저층 보정을 적용한다: 저층 체크 시 입력가 그대로, 저층이 아닐 경우에만 -10% 보정.
    """
    t13_adj, t13_ref = adjust_low_floor_price(
        record.get("t13_price", 0), bool(record.get("t13_low_floor", 0))
    )
    t12_adj, t12_ref = adjust_low_floor_price(
        record.get("t12_price", 0), bool(record.get("t12_low_floor", 0))
    )
    dusan_adj, dusan_ref = adjust_low_floor_price(
        record.get("dusan_price", 0), bool(record.get("dusan_low_floor", 1))
    )
    boram_adj, boram_ref = adjust_low_floor_price(
        record.get("boram_price", 0), bool(record.get("boram_low_floor", 0))
    )

    loans = record.get("loan_self", 0) + record.get("loan_spouse", 0)
    net_equity = dusan_adj + boram_adj - loans

    cash = record.get("cash_self", 0) + record.get("cash_spouse", 0)
    reserve_fund = record.get("reserve_fund", 0)
    available_cash = cash - reserve_fund

    total_available_capital = net_equity + available_cash

    return {
        "dusan_adjusted": dusan_adj,
        "dusan_reference_original": dusan_ref,
        "boram_adjusted": boram_adj,
        "boram_reference_original": boram_ref,
        "net_equity": net_equity,
        "available_cash": available_cash,
        "total_available_capital": total_available_capital,
        "t13": {
            **target_metrics(t13_adj, total_available_capital),
            "reference_original": t13_ref,
        },
        "t12": {
            **target_metrics(t12_adj, total_available_capital),
            "reference_original": t12_ref,
        },
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
