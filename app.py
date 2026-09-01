# -*- coding: utf-8 -*-
"""철산 갈아타기 자금 및 시세 트래킹 대시보드."""

import os
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import db
from calculations import compute_metrics, format_krw_eok
from config import (
    RESERVE_FUND_DEFAULT,
    MANWON,
    TARGET_COMPLEXES,
    HELD_COMPLEXES,
)
from molit_api import MolitApiError

st.set_page_config(page_title="철산 갈아타기 트래커", page_icon="🏘️", layout="wide")
db.init_db()

# ---------------------------------------------------------------------------
# 세션 상태 초기화
# ---------------------------------------------------------------------------
DEFAULTS = {
    "in_t13_price_man": 0,
    "in_t13_low": False,
    "in_t12_price_man": 0,
    "in_t12_low": False,
    "in_dusan_price_man": 0,
    "in_dusan_low": True,
    "in_boram_price_man": 0,
    "in_boram_low": False,
    "in_loan_self_man": 0,
    "in_loan_spouse_man": 0,
    "in_cash_self_man": 0,
    "in_cash_spouse_man": 0,
    "in_reserve_man": RESERVE_FUND_DEFAULT // MANWON,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

if "selected_ym" not in st.session_state:
    st.session_state["selected_ym"] = date.today().strftime("%Y-%m")


def load_record_into_state(record: dict):
    st.session_state["in_t13_price_man"] = record["t13_price"] // MANWON
    st.session_state["in_t13_low"] = bool(record["t13_low_floor"])
    st.session_state["in_t12_price_man"] = record["t12_price"] // MANWON
    st.session_state["in_t12_low"] = bool(record["t12_low_floor"])
    st.session_state["in_dusan_price_man"] = record["dusan_price"] // MANWON
    st.session_state["in_dusan_low"] = bool(record["dusan_low_floor"])
    st.session_state["in_boram_price_man"] = record["boram_price"] // MANWON
    st.session_state["in_boram_low"] = bool(record["boram_low_floor"])
    st.session_state["in_loan_self_man"] = record["loan_self"] // MANWON
    st.session_state["in_loan_spouse_man"] = record["loan_spouse"] // MANWON
    st.session_state["in_cash_self_man"] = record["cash_self"] // MANWON
    st.session_state["in_cash_spouse_man"] = record["cash_spouse"] // MANWON
    st.session_state["in_reserve_man"] = record["reserve_fund"] // MANWON


def current_record_from_state() -> dict:
    return {
        "t13_price": st.session_state["in_t13_price_man"] * MANWON,
        "t13_low_floor": int(st.session_state["in_t13_low"]),
        "t12_price": st.session_state["in_t12_price_man"] * MANWON,
        "t12_low_floor": int(st.session_state["in_t12_low"]),
        "dusan_price": st.session_state["in_dusan_price_man"] * MANWON,
        "dusan_low_floor": int(st.session_state["in_dusan_low"]),
        "boram_price": st.session_state["in_boram_price_man"] * MANWON,
        "boram_low_floor": int(st.session_state["in_boram_low"]),
        "loan_self": st.session_state["in_loan_self_man"] * MANWON,
        "loan_spouse": st.session_state["in_loan_spouse_man"] * MANWON,
        "cash_self": st.session_state["in_cash_self_man"] * MANWON,
        "cash_spouse": st.session_state["in_cash_spouse_man"] * MANWON,
        "reserve_fund": st.session_state["in_reserve_man"] * MANWON,
    }


# ---------------------------------------------------------------------------
# 사이드바: API 설정 & 실거래가 갱신
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 설정")

    st.subheader("국토부 Open API")
    default_key = os.environ.get("MOLIT_API_KEY") or db.get_setting("molit_api_key", "")
    api_key_input = st.text_input(
        "MOLIT_API_KEY (data.go.kr 인증키)", value=default_key or "", type="password",
        help="공공데이터포털에서 '아파트매매 실거래 상세자료' 활용신청 후 발급받은 서비스키",
    )
    if st.button("API 키 저장", use_container_width=True):
        db.set_setting("molit_api_key", api_key_input)
        st.success("저장되었습니다.")

    last_fetch = db.get_last_fetch_time()
    st.caption(f"마지막 실거래가 수집: {last_fetch or '아직 없음'}")

    if st.button("🔄 지금 실거래가 갱신", use_container_width=True):
        import scheduler as _sched
        with st.spinner("국토부 Open API에서 최근 3개월 실거래가를 조회하는 중..."):
            try:
                result = _sched.run_full_refresh(months_back=3)
            except Exception as e:  # noqa: BLE001
                result = {"error": str(e)}
        if "error" in result:
            st.error(result["error"])
        else:
            total = sum(result.values())
            st.success(f"신규 {total}건 저장 완료")
            st.json(result)

    with st.expander("🛰️ 앱 내장 자동 갱신 (선택)"):
        st.caption(
            "Streamlit 앱이 켜져 있는 동안만 동작합니다. "
            "항상 안정적으로 돌리려면 scheduler.py를 cron에 등록하는 것을 권장합니다."
        )
        interval = st.number_input("갱신 주기(시간)", min_value=1, max_value=168, value=24)
        if st.button("자동 갱신 시작", use_container_width=True):
            import scheduler as _sched
            _sched.start_background_scheduler(interval_hours=int(interval))
            st.success(f"{interval}시간마다 자동 갱신이 시작되었습니다. (앱 실행 중에만 유효)")

    with st.expander("🧭 단지 코드 설정 (LAWD_CD / 키워드)"):
        st.caption("실거래가 조회에 사용하는 법정동코드와 아파트명 매칭 키워드입니다. 데이터가 안 잡히면 확인/수정하세요.")
        stored_cfg = db.get_complex_config()
        new_cfg = {}
        for key, cfg in stored_cfg.items():
            st.markdown(f"**{cfg['label']}**")
            c1, c2 = st.columns(2)
            lawd = c1.text_input("LAWD_CD", value=cfg["lawd_cd"], key=f"lawd_{key}")
            kw = c2.text_input(
                "매칭 키워드(콤마구분)", value=",".join(cfg.get("keywords", [])), key=f"kw_{key}"
            )
            new_cfg[key] = {
                "lawd_cd": lawd.strip(),
                "keywords": [k.strip() for k in kw.split(",") if k.strip()],
            }
        if st.button("단지 코드 설정 저장", use_container_width=True):
            db.set_setting("complex_config", new_cfg)
            st.success("저장되었습니다.")


# ---------------------------------------------------------------------------
# 메인: 타이틀 & 월 선택 / 기록 불러오기
# ---------------------------------------------------------------------------
st.title("🏘️ 철산 갈아타기 자금 트래킹 대시보드")
st.caption("철산주공 13/12단지 진입을 위한 자금 갭(Gap) 실시간 모니터링")

col_ym, col_load, col_save = st.columns([2, 1, 1])
with col_ym:
    picked_date = st.date_input(
        "기록할 연/월 선택",
        value=date.fromisoformat(st.session_state["selected_ym"] + "-01"),
    )
    new_ym = picked_date.strftime("%Y-%m")
    if new_ym != st.session_state["selected_ym"]:
        st.session_state["selected_ym"] = new_ym

with col_load:
    st.write("")
    st.write("")
    if st.button("📂 이 달 기록 불러오기", use_container_width=True):
        rec = db.get_monthly_record(st.session_state["selected_ym"])
        if rec:
            load_record_into_state(rec)
            st.success("불러왔습니다.")
            st.rerun()
        else:
            latest = db.get_latest_record()
            if latest:
                load_record_into_state(latest)
                st.info("이 달 기록이 없어 가장 최근 기록 값을 불러왔습니다. (저장 전까지는 임시값)")
                st.rerun()
            else:
                st.warning("저장된 기록이 없습니다.")

with col_save:
    st.write("")
    st.write("")
    save_clicked = st.button("💾 이 달 기록 저장", type="primary", use_container_width=True)

if save_clicked:
    db.upsert_monthly_record(st.session_state["selected_ym"], current_record_from_state())
    st.success(f"{st.session_state['selected_ym']} 기록이 저장되었습니다.")

st.divider()

# ---------------------------------------------------------------------------
# 입력 섹션
# ---------------------------------------------------------------------------
LOW_FLOOR_HELP = "체크: 입력가가 이미 저층 기준가임 (보정 없음). 해제: 입력가가 저층이 아닌 기준가로 보고 -10% 자동 보정하여 저층가로 환산."

st.subheader("📋 매물 호가 입력 (Target, 만원 단위)")
c1, c2 = st.columns(2)
with c1:
    st.markdown(f"**{TARGET_COMPLEXES['cheolsan13']['label']} {TARGET_COMPLEXES['cheolsan13']['pyeong']}평**")
    st.number_input("최저 호가(만원)", min_value=0, step=500, key="in_t13_price_man")
    st.checkbox("저층 매물 (해제 시 -10% 보정)", key="in_t13_low", help=LOW_FLOOR_HELP)
with c2:
    st.markdown(f"**{TARGET_COMPLEXES['cheolsan12']['label']} {TARGET_COMPLEXES['cheolsan12']['pyeong']}평**")
    st.number_input("최저 호가(만원)", min_value=0, step=500, key="in_t12_price_man")
    st.checkbox("저층 매물 (해제 시 -10% 보정)", key="in_t12_low", help=LOW_FLOOR_HELP)

st.subheader("🏠 보유 부동산 매도 예상가 입력 (만원 단위)")
c3, c4 = st.columns(2)
with c3:
    st.markdown(f"**{HELD_COMPLEXES['guro_dusan']['label']} {HELD_COMPLEXES['guro_dusan']['pyeong']}평** (3층)")
    st.number_input("매도 예상가(만원)", min_value=0, step=500, key="in_dusan_price_man")
    st.checkbox("저층가 기준으로 입력함 (기본 체크, 해제 시 -10% 자동 보정)", key="in_dusan_low", help=LOW_FLOOR_HELP)
with c4:
    st.markdown(f"**{HELD_COMPLEXES['bucheon_boram']['label']} {HELD_COMPLEXES['bucheon_boram']['pyeong']}평**")
    st.number_input("매도 예상가(만원)", min_value=0, step=500, key="in_boram_price_man")
    st.checkbox("저층 매물 (해제 시 -10% 보정)", key="in_boram_low", help=LOW_FLOOR_HELP)

st.subheader("💳 기존 대출 잔액 (만원 단위)")
c5, c6 = st.columns(2)
with c5:
    st.number_input("본인 대출 잔액(만원)", min_value=0, step=100, key="in_loan_self_man")
with c6:
    st.number_input("배우자 대출 잔액(만원)", min_value=0, step=100, key="in_loan_spouse_man")

st.subheader("💰 현금 자산 입력 (만원 단위)")
c7, c8, c9 = st.columns(3)
with c7:
    st.number_input("본인 유동성 현금/투자금(만원)", min_value=0, step=100, key="in_cash_self_man")
with c8:
    st.number_input("배우자 유동성 현금/투자금(만원)", min_value=0, step=100, key="in_cash_spouse_man")
with c9:
    st.number_input("보존할 예비 투자금(만원)", min_value=0, step=100, key="in_reserve_man")

st.divider()

# ---------------------------------------------------------------------------
# 실시간 계산
# ---------------------------------------------------------------------------
record = current_record_from_state()
metrics = compute_metrics(record)

st.subheader("📊 핵심 지표 (KPI)")
kA, kB, kC = st.columns(3)
with kA:
    st.metric(
        "🎯 철산주공 13단지 28평 달성률",
        f"{metrics['t13']['rate']:.1f}%",
        delta=f"부족 {format_krw_eok(metrics['t13']['shortfall'])}" if metrics['t13']['shortfall'] > 0
        else f"여유 {format_krw_eok(-metrics['t13']['shortfall'])}",
        delta_color="inverse",
    )
with kB:
    st.metric(
        "🅱️ 철산주공 12단지 27평 달성률(플랜B)",
        f"{metrics['t12']['rate']:.1f}%",
        delta=f"부족 {format_krw_eok(metrics['t12']['shortfall'])}" if metrics['t12']['shortfall'] > 0
        else f"여유 {format_krw_eok(-metrics['t12']['shortfall'])}",
        delta_color="inverse",
    )
with kC:
    st.metric("보유 순자산 총액", format_krw_eok(metrics["net_equity"]))
    st.metric("현재 가용 현금", format_krw_eok(metrics["available_cash"]))

# 조건부 경고 배지
for label, key in [("철산 13단지", "t13"), ("철산 12단지", "t12")]:
    m = metrics[key]
    if m["over_15eok"]:
        st.warning(f"⚠️ [{label}] 15억 초과 규제 적용: 대출 한도 4억 원 제한 구역 (호가 {format_krw_eok(m['target_price'])})")
    if m["achievable"]:
        st.success(f"🎉 [{label}] 매수 실행 가능 상태! (갭 메우기 완료, 여유 {format_krw_eok(-m['shortfall'])})")

st.divider()

# ---------------------------------------------------------------------------
# 매물/보유자산 카드 (저층 표시)
# ---------------------------------------------------------------------------
st.subheader("🏷️ 단지별 현황 카드")
cards = st.columns(4)

def render_price_card(price_label: str, low_floor_checked: bool, adjusted_price: int,
                       reference_original) -> None:
    if low_floor_checked:
        st.write(f"{price_label}: **{format_krw_eok(adjusted_price)}**")
        st.write("🔻 저층(입력가 그대로 사용)")
    else:
        st.write(f"{price_label}(저층 보정): **{format_krw_eok(adjusted_price)}**")
        st.caption(f"원본 입력가(일반층 기준): {format_krw_eok(reference_original)} → -10% 보정 적용")
        st.write("⬜ 일반층 입력 → 저층가로 환산")


with cards[0]:
    st.markdown("##### 🎯 철산주공 13단지 28평")
    render_price_card("호가", bool(record["t13_low_floor"]), metrics["t13"]["target_price"],
                       metrics["t13"]["reference_original"])

with cards[1]:
    st.markdown("##### 🅱️ 철산주공 12단지 27평")
    render_price_card("호가", bool(record["t12_low_floor"]), metrics["t12"]["target_price"],
                       metrics["t12"]["reference_original"])

with cards[2]:
    st.markdown("##### 🏠 구로 두산 20평 (3층)")
    render_price_card("매도 예상가", bool(record["dusan_low_floor"]), metrics["dusan_adjusted"],
                       metrics["dusan_reference_original"])

with cards[3]:
    st.markdown("##### 🏠 부천 보람마을 아주 23평")
    render_price_card("매도 예상가", bool(record["boram_low_floor"]), metrics["boram_adjusted"],
                       metrics["boram_reference_original"])

st.divider()

# ---------------------------------------------------------------------------
# 상세 계산 내역
# ---------------------------------------------------------------------------
with st.expander("🧮 상세 계산 내역 보기"):
    for label, key in [("철산 13단지 28평", "t13"), ("철산 12단지 27평", "t12")]:
        m = metrics[key]
        st.markdown(f"**[{label}]**")
        detail_df = pd.DataFrame(
            {
                "항목": [
                    "Target 호가", "구매 제반 비용(3.5%)", "총 필요 자금",
                    "부동산 순자산", "가용 현금", "총 가용 자본",
                    "대출 한도(LTV)", "총 가용자본+대출", "최종 부족/여유 자금", "달성률(%)",
                ],
                "금액/값": [
                    format_krw_eok(m["target_price"]),
                    format_krw_eok(m["purchase_cost"]),
                    format_krw_eok(m["total_required"]),
                    format_krw_eok(metrics["net_equity"]),
                    format_krw_eok(metrics["available_cash"]),
                    format_krw_eok(metrics["total_available_capital"]),
                    format_krw_eok(m["loan_limit"]),
                    format_krw_eok(m["total_with_loan"]),
                    format_krw_eok(m["shortfall"]) if m["shortfall"] >= 0 else f"-{format_krw_eok(-m['shortfall'])} (여유)",
                    f"{m['rate']:.1f}%",
                ],
            }
        )
        st.dataframe(detail_df, hide_index=True, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# 월별 기록 테이블 & 그래프
# ---------------------------------------------------------------------------
st.subheader("📈 월별 기록 & 추이")

hist_df = db.get_all_monthly_records_df()
if hist_df.empty:
    st.info("아직 저장된 월별 기록이 없습니다. 상단에서 값을 입력하고 '이 달 기록 저장'을 눌러주세요.")
else:
    rows = []
    for _, r in hist_df.iterrows():
        rec_dict = r.to_dict()
        m = compute_metrics(rec_dict)
        rows.append(
            {
                "연월": rec_dict["year_month"],
                "13단지 호가": rec_dict["t13_price"],
                "13단지 부족갭": m["t13"]["shortfall"],
                "13단지 달성률(%)": round(m["t13"]["rate"], 1),
                "12단지 호가": rec_dict["t12_price"],
                "12단지 부족갭": m["t12"]["shortfall"],
                "12단지 달성률(%)": round(m["t12"]["rate"], 1),
                "순자산": m["net_equity"],
                "가용현금": m["available_cash"],
            }
        )
    table_df = pd.DataFrame(rows)
    st.dataframe(table_df, hide_index=True, use_container_width=True)

    fig_gap = go.Figure()
    fig_gap.add_trace(go.Scatter(x=table_df["연월"], y=table_df["13단지 부족갭"], mode="lines+markers", name="13단지 부족갭"))
    fig_gap.add_trace(go.Scatter(x=table_df["연월"], y=table_df["12단지 부족갭"], mode="lines+markers", name="12단지 부족갭"))
    fig_gap.add_hline(y=0, line_dash="dash", line_color="green")
    fig_gap.update_layout(title="월별 필요 갭 금액 추이 (원)", xaxis_title="연월", yaxis_title="부족 금액(원)")
    st.plotly_chart(fig_gap, use_container_width=True)

    fig_rate = go.Figure()
    fig_rate.add_trace(go.Scatter(x=table_df["연월"], y=table_df["13단지 달성률(%)"], mode="lines+markers", name="13단지 달성률"))
    fig_rate.add_trace(go.Scatter(x=table_df["연월"], y=table_df["12단지 달성률(%)"], mode="lines+markers", name="12단지 달성률"))
    fig_rate.add_hline(y=100, line_dash="dash", line_color="green")
    fig_rate.update_layout(title="월별 달성률(%) 추이", xaxis_title="연월", yaxis_title="달성률(%)")
    st.plotly_chart(fig_rate, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# 실거래가 참고 정보
# ---------------------------------------------------------------------------
st.subheader("🏢 실거래가 참고 (국토부 Open API 자동수집)")
all_complexes = {**TARGET_COMPLEXES, **HELD_COMPLEXES}
tx_cols = st.columns(2)
for i, (key, cfg) in enumerate(all_complexes.items()):
    with tx_cols[i % 2]:
        st.markdown(f"**{cfg['badge']} {cfg['label']} {cfg['pyeong']}평**")
        tx_df = db.get_recent_transactions(key, limit=10)
        if tx_df.empty:
            st.caption("수집된 실거래가가 없습니다. 사이드바에서 '지금 실거래가 갱신'을 눌러보세요.")
        else:
            tx_df = tx_df.copy()
            tx_df["price"] = tx_df["price"].apply(format_krw_eok)
            tx_df.columns = ["거래일", "아파트명", "거래가", "전용면적(㎡)", "층", "법정동"]
            st.dataframe(tx_df, hide_index=True, use_container_width=True)
