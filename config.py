# -*- coding: utf-8 -*-
"""프로젝트 전역 설정 및 상수."""

import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "tracker.db")

RESERVE_FUND_DEFAULT = 300_000_000  # 예비 투자금 기본값 (원)
PURCHASE_COST_RATE = 0.035          # 구매 제반 비용률 (취득세+중개보수+등기비용 등 근사치)
LTV_PRICE_THRESHOLD = 1_500_000_000  # 15억 규제 기준
LOAN_LIMIT_OVER_15EOK = 400_000_000
LOAN_LIMIT_UNDER_15EOK = 600_000_000
LOW_FLOOR_DISCOUNT = 0.10            # 저층 보정률 (-10%, 저층이 아닌 입력가에 적용)

MANWON = 10_000  # 만원 단위 <-> 원 변환

# 매수 목표 단지 (미보유, 실거래가 자동수집 + Target 호가 수동입력)
TARGET_COMPLEXES = {
    "cheolsan13": {
        "label": "철산주공 13단지",
        "pyeong": 28,
        "badge": "🎯 목표",
        "lawd_cd": "41210",   # 경기 광명시
        "keywords": ["철산주공13", "주공13", "철산주공 13"],
    },
    "cheolsan12": {
        "label": "철산주공 12단지",
        "pyeong": 27,
        "badge": "🅱️ 플랜B",
        "lawd_cd": "41210",   # 경기 광명시
        "keywords": ["철산주공12", "주공12", "철산주공 12"],
    },
}

# 보유 자산 (실거래가 자동수집 + 매도 예상가 수동입력)
HELD_COMPLEXES = {
    "guro_dusan": {
        "label": "구로 두산",
        "pyeong": 20,
        "badge": "🏠 보유",
        "lawd_cd": "11530",   # 서울 구로구
        "keywords": ["두산"],
        "default_low_floor": True,   # 3층 실거주 -> 기본 저층
        "has_correction": True,      # 체크 해제 시 -10% 저층 보정 적용
    },
    "bucheon_boram": {
        "label": "부천 보람마을 아주",
        "pyeong": 23,
        "badge": "🏠 보유",
        "lawd_cd": "41190",   # 경기 부천시
        "keywords": ["아주"],
        "default_low_floor": False,
        "has_correction": False,     # 보정 없이 참고용 뱃지만 표시
    },
}

ALL_COMPLEXES = {**TARGET_COMPLEXES, **HELD_COMPLEXES}
