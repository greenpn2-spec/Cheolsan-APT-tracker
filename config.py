# -*- coding: utf-8 -*-
"""프로젝트 전역 설정 및 상수."""

import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "tracker.db")

RESERVE_FUND_DEFAULT = 300_000_000  # 예비 투자금 기본값 (원)

# 구매 제반 비용 항목별 근사치 (취득세/중개수수료는 호가 대비 %, 이사비용은 정액)
ACQUISITION_TAX_RATE = 0.030   # 취득세 등(지방교육세 포함 근사치)
BROKERAGE_RATE = 0.005         # 부동산 중개수수료 근사치 (법정 상한 부근)
MOVING_COST_DEFAULT = 3_000_000  # 이사비용 예상액(원) — 정액, 목표가와 무관

LTV_PRICE_THRESHOLD = 1_500_000_000  # 15억 규제 기준
LOAN_LIMIT_OVER_15EOK = 400_000_000
LOAN_LIMIT_UNDER_15EOK = 600_000_000
LOW_FLOOR_DISCOUNT = 0.10            # 저층 보정률 (-10%, 저층이 아닌 입력가에 적용)

MANWON = 10_000  # 만원 단위 <-> 원 변환

# keywords: API 응답 아파트명(aptNm)과 "정확히 일치"하는 이름 후보 목록 (부분일치 아님).
#           실제 국토부 데이터의 아파트명은 "철산주공13단지" 같은 정식 명칭이 아니라
#           "주공13"처럼 축약된 형태로 내려오는 경우가 많아, 실제 수집 결과를 보고 값을
#           확정했다. 잘못 잡히면 사이드바 "🧭 단지 코드 설정"에서 직접 수정 가능.
# dong_filter: 법정동(umdNm) 부분일치 필터 (동명이 다른 지역의 동일 단지명과 섞이는 것 방지)
# area_m2_target / area_m2_tolerance: 전용면적(㎡) 필터 - 원하는 평형만 남기기 위함

# 매수 목표 단지 (미보유, 실거래가 자동수집 + Target 호가 수동입력)
TARGET_COMPLEXES = {
    "cheolsan13": {
        "label": "철산주공 13단지",
        "pyeong": 28,
        "badge": "🎯 목표",
        "lawd_cd": "41210",   # 경기 광명시
        "keywords": ["주공13"],
        "dong_filter": "철산동",
        "area_m2_target": 73.08,   # A/B타입 73.08~73.09 모두 포함되도록 허용오차로 커버
        "area_m2_tolerance": 0.3,
    },
    "cheolsan12": {
        "label": "철산주공 12단지",
        "pyeong": 27,
        "badge": "🅱️ 플랜B",
        "lawd_cd": "41210",   # 경기 광명시
        "keywords": ["주공12"],
        "dong_filter": "철산동",
        "area_m2_target": 73.08,
        "area_m2_tolerance": 0.3,
    },
}

# 보유 자산 (실거래가 자동수집 + 매도 예상가 수동입력)
HELD_COMPLEXES = {
    "guro_dusan": {
        "label": "구로 두산",
        "pyeong": 20,
        "badge": "🏠 보유",
        "lawd_cd": "11530",   # 서울 구로구
        "keywords": ["구로두산"],
        "dong_filter": "구로동",
        "area_m2_target": 44.64,
        "area_m2_tolerance": 0.3,
        "default_low_floor": True,   # 3층 실거주 -> 기본 저층
        "has_correction": True,      # 체크 해제 시 -10% 저층 보정 적용
    },
    "bucheon_boram": {
        "label": "부천 보람마을 아주",
        "pyeong": 23,
        "badge": "🏠 보유",
        "lawd_cd": "41192",   # 경기 부천시 원미구 (2024 구 재설치로 41190 전체코드는 더 이상 안 맞을 수 있음). 실측으로 확인 완료.
        "keywords": ["보람마을(아주)"],  # 실제 국토부 데이터의 아파트명이 이 괄호 포함 형식으로 내려옴 (실측 확인)
        "dong_filter": "중동",
        "area_m2_target": 59.94,
        "area_m2_tolerance": 0.3,
        "default_low_floor": False,
        "has_correction": False,     # 보정 없이 참고용 뱃지만 표시
    },
}

ALL_COMPLEXES = {**TARGET_COMPLEXES, **HELD_COMPLEXES}
