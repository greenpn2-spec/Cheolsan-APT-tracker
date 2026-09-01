# -*- coding: utf-8 -*-
"""철산 갈아타기 자금 및 시세 트래킹 대시보드."""

import os
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

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


def format_kst(iso_str: str | None) -> str:
    """UTC ISO 문자열을 'YYYY-MM-DD HH:MM (KST)' 형태로 변환."""
    if not iso_str:
        return "아직 없음"
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        return iso_str
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    kst = dt.astimezone(ZoneInfo("Asia/Seoul"))
    return kst.strftime("%Y-%m-%d %H:%M") + " (KST)"

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


# 세션이 새로 시작될 때(첫 로드, 리부트, 새 탭 등) DB에 저장된 값을 자동으로
# 불러온다. 이걸 안 하면 입력해둔 값이 "리부트/새로고침할 때마다 사라진 것처럼"
# 보이게 된다 (실제로는 DB에 저장은 됐지만 화면에 다시 채워주질 않았을 뿐).
if "_state_loaded" not in st.session_state:
    today_ym = date.today().strftime("%Y-%m")
    record = db.get_monthly_record(today_ym) or db.get_latest_record()
    if record:
        load_record_into_state(record)
    else:
        for k, v in DEFAULTS.items():
            st.session_state[k] = v
    # 저장 대상 월은 항상 이번 달을 기본으로 한다 (과거 달의 값을 불러왔더라도
    # '저장'을 누르면 그 과거 기록을 덮어쓰는 게 아니라 이번 달로 새로 기록되게).
    st.session_state["selected_ym"] = today_ym
    st.session_state["_state_loaded"] = True


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
    st.caption(f"마지막 실거래가 수집: {format_kst(last_fetch)}")

    if st.button("🔄 지금 실거래가 갱신", use_container_width=True):
        import scheduler as _sched
        with st.spinner("국토부 Open API에서 최근 3개월 실거래가를 조회하는 중..."):
            try:
                result = _sched.run_full_refresh(months_back=3)
            except Exception as e:  # noqa: BLE001
                result = {"error": str(e)}
        st.session_state["last_refresh_result"] = result
        st.rerun()

    last_result = st.session_state.get("last_refresh_result")
    if last_result is not None:
        if "error" in last_result:
            st.error(last_result["error"])
        else:
            all_complexes_cfg = {**TARGET_COMPLEXES, **HELD_COMPLEXES}
            total_inserted = sum(v["inserted"] for v in last_result.values())
            has_errors = any(v["errors"] for v in last_result.values())
            if total_inserted > 0:
                st.success(f"신규 {total_inserted}건 저장 완료")
            elif not has_errors:
                st.info("신규 실거래가가 없습니다 (이미 최신 상태이거나, 최근 3개월간 해당 단지 거래가 없을 수 있습니다).")
            for key, v in last_result.items():
                label = all_complexes_cfg.get(key, {}).get("label", key)
                total_in_db = db.count_transactions(key)
                st.caption(f"{label}: 이번에 신규 {v['inserted']}건 (DB 누적 총 {total_in_db}건)")
            if has_errors:
                with st.expander("⚠️ 조회 중 오류 발생 (자세히 보기)"):
                    for key, v in last_result.items():
                        if v["errors"]:
                            label = all_complexes_cfg.get(key, {}).get("label", key)
                            st.markdown(f"**{label}**")
                            for err in v["errors"]:
                                st.caption(err)

    with st.expander("🛰️ 자동 갱신 (매월 1일 오전 1시)"):
        import scheduler as _sched
        st.caption(
            "실거래가는 매월 1일 오전 1시(KST)에 자동 갱신되도록 설계되어 있습니다. "
            "위의 '지금 실거래가 갱신' 버튼은 그대로 원할 때 언제든 눌러 즉시 갱신할 수 있습니다."
        )
        st.markdown(
            "**앱 내장 스케줄러**: 아래 버튼을 누르면 이 Streamlit 프로세스가 켜져 있는 동안 "
            "매월 1일 01:00에 자동 실행됩니다. (앱을 껐다 켜면 다시 눌러야 합니다.)"
        )
        if st.button("매월 1일 01:00 자동 갱신 시작", use_container_width=True):
            _sched.start_background_scheduler()
            st.success("등록되었습니다. 다음 실행: 매월 1일 오전 1시(KST)")
        status = "🟢 실행 중" if _sched.is_background_scheduler_running() else "⚪ 미실행"
        st.caption(f"앱 내장 스케줄러 상태: {status}")

        st.markdown("**cron (권장, 앱을 계속 켜두지 않아도 동작)**")
        st.code("0 1 1 * * cd /path/to/Cheolsan-APT-tracker && python scheduler.py", language="bash")
        st.caption("서버의 crontab에 위 줄을 등록하면 앱 실행 여부와 무관하게 매월 1일 01:00에 갱신됩니다. 자세한 방법은 README 참고.")

    with st.expander("🧭 단지 코드 설정 (LAWD_CD / 아파트명 / 평형)"):
        st.caption(
            "실거래가 조회에 사용하는 법정동코드, 아파트명, 법정동, 전용면적 필터입니다. "
            "'정확한 아파트명'은 부분일치가 아니라 완전히 같은 이름만 매칭됩니다 "
            "(예: '두산'으로 두면 '구로두산위브' 같은 다른 단지까지 섞여 들어옵니다). "
            "엉뚱한 단지/평형이 잡히거나 아예 안 잡히면 여기서 직접 조정하세요."
        )
        stored_cfg = db.get_complex_config()
        new_cfg = {}
        for key, cfg in stored_cfg.items():
            st.markdown(f"**{cfg['label']}**")
            c1, c2 = st.columns(2)
            lawd = c1.text_input("LAWD_CD", value=cfg["lawd_cd"], key=f"lawd_{key}")
            kw = c2.text_input(
                "정확한 아파트명(콤마구분)", value=",".join(cfg.get("keywords", [])), key=f"kw_{key}"
            )
            c3, c4, c5 = st.columns(3)
            dong = c3.text_input(
                "법정동(선택)", value=cfg.get("dong_filter") or "", key=f"dong_{key}",
                help="비워두면 법정동 필터 없이 시/군/구 전체에서 검색합니다.",
            )
            area_target = c4.number_input(
                "전용면적 기준(㎡, 선택)", min_value=0.0, step=0.1,
                value=float(cfg.get("area_m2_target") or 0.0), key=f"area_{key}",
                help="0이면 면적 필터를 적용하지 않습니다.",
            )
            area_tol = c5.number_input(
                "허용오차(㎡)", min_value=0.0, step=0.1,
                value=float(cfg.get("area_m2_tolerance", 1.0)), key=f"tol_{key}",
            )
            new_cfg[key] = {
                "lawd_cd": lawd.strip(),
                "keywords": [k.strip() for k in kw.split(",") if k.strip()],
                "dong_filter": dong.strip() or None,
                "area_m2_target": area_target if area_target > 0 else None,
                "area_m2_tolerance": area_tol,
            }

            if st.button(f"🔍 이 LAWD_CD로 원본 목록 미리보기", key=f"debug_btn_{key}"):
                debug_service_key = api_key_input or default_key
                if not debug_service_key:
                    st.session_state[f"debug_result_{key}"] = {"error": "API 키를 먼저 입력/저장하세요."}
                else:
                    import molit_api as _mapi
                    try:
                        found = None
                        tried = []
                        for ymd in _mapi.recent_year_months(3):
                            items = _mapi.fetch_trades_for_month(lawd.strip(), ymd, debug_service_key)
                            tried.append((ymd, len(items)))
                            if items:
                                found = (ymd, items)
                                break
                        st.session_state[f"debug_result_{key}"] = {"found": found, "tried": tried}
                    except Exception as e:  # noqa: BLE001
                        st.session_state[f"debug_result_{key}"] = {"error": str(e)}

            debug_result = st.session_state.get(f"debug_result_{key}")
            if debug_result:
                if "error" in debug_result:
                    st.error(debug_result["error"])
                elif not debug_result["found"]:
                    tried_str = ", ".join(f"{y}({c}건)" for y, c in debug_result["tried"])
                    st.warning(
                        f"이 LAWD_CD로 최근 3개월({tried_str}) 모두 거래가 0건입니다. "
                        "LAWD_CD 자체가 틀렸을 가능성이 높습니다."
                    )
                else:
                    ymd, items = debug_result["found"]
                    st.caption(f"{ymd} 기준, 이 LAWD_CD 전체 거래 {len(items)}건 중 서로 다른 아파트명 목록:")
                    seen = {}
                    for it in items:
                        k2 = (it["apt_name"], it["dong"] or "")
                        seen.setdefault(k2, set()).add(it["area_m2"])
                    debug_rows = [
                        {
                            "아파트명": name,
                            "법정동": dong_val,
                            "전용면적(㎡) 예시": ", ".join(
                                f"{a:g}" for a in sorted(a for a in areas if a is not None)
                            ),
                        }
                        for (name, dong_val), areas in sorted(seen.items())
                    ]
                    st.dataframe(pd.DataFrame(debug_rows), hide_index=True, use_container_width=True)
            st.divider()
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
BADGE_ONLY_HELP = "참고용 배지 표시 전용입니다. 가격 계산에는 영향을 주지 않습니다."
DUSAN_LOW_FLOOR_HELP = "체크(기본값): 입력가가 이미 저층(3층) 기준가임 → 보정 없음. 해제: 중고층 실거래가 등을 참고해 그대로 입력한 경우 → -10% 자동 보정하여 저층 등가로 환산."

st.subheader("📋 매물 호가 입력 (Target, 만원 단위)")
c1, c2 = st.columns(2)
with c1:
    st.markdown(f"**{TARGET_COMPLEXES['cheolsan13']['label']} {TARGET_COMPLEXES['cheolsan13']['pyeong']}평**")
    st.number_input("최저 호가(만원)", min_value=0, step=500, key="in_t13_price_man")
    st.checkbox("저층 매물", key="in_t13_low", help=BADGE_ONLY_HELP)
with c2:
    st.markdown(f"**{TARGET_COMPLEXES['cheolsan12']['label']} {TARGET_COMPLEXES['cheolsan12']['pyeong']}평**")
    st.number_input("최저 호가(만원)", min_value=0, step=500, key="in_t12_price_man")
    st.checkbox("저층 매물", key="in_t12_low", help=BADGE_ONLY_HELP)

st.subheader("🏠 보유 부동산 매도 예상가 입력 (만원 단위)")
c3, c4 = st.columns(2)
with c3:
    st.markdown(f"**{HELD_COMPLEXES['guro_dusan']['label']} {HELD_COMPLEXES['guro_dusan']['pyeong']}평** (3층 · 실보유 저층)")
    st.number_input("매도 예상가(만원)", min_value=0, step=500, key="in_dusan_price_man")
    st.checkbox("저층가 기준으로 입력함 (기본 체크, 해제 시 -10% 자동 보정)", key="in_dusan_low", help=DUSAN_LOW_FLOOR_HELP)
with c4:
    st.markdown(f"**{HELD_COMPLEXES['bucheon_boram']['label']} {HELD_COMPLEXES['bucheon_boram']['pyeong']}평**")
    st.number_input("매도 예상가(만원)", min_value=0, step=500, key="in_boram_price_man")
    st.checkbox("저층 매물", key="in_boram_low", help=BADGE_ONLY_HELP)

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

def render_badge_card(price_label: str, price: int, low_floor_checked: bool) -> None:
    st.write(f"{price_label}: **{format_krw_eok(price)}**")
    st.write("🔻 저층" if low_floor_checked else "⬜ 일반층/미표시")


with cards[0]:
    st.markdown("##### 🎯 철산주공 13단지 28평")
    render_badge_card("호가", record["t13_price"], bool(record["t13_low_floor"]))

with cards[1]:
    st.markdown("##### 🅱️ 철산주공 12단지 27평")
    render_badge_card("호가", record["t12_price"], bool(record["t12_low_floor"]))

with cards[2]:
    st.markdown("##### 🏠 구로 두산 20평 (3층 · 실보유 저층)")
    if metrics["dusan_reference_original"] is not None:
        st.write(f"매도 예상가(저층 보정): **{format_krw_eok(metrics['dusan_adjusted'])}**")
        st.caption(f"원본 입력가(중고층 기준): {format_krw_eok(metrics['dusan_reference_original'])} → -10% 보정 적용")
        st.write("⬜ 중고층 기준 입력 → 저층가로 환산")
    else:
        st.write(f"매도 예상가: **{format_krw_eok(metrics['dusan_adjusted'])}**")
        st.write("🔻 저층(입력가 그대로 사용)")

with cards[3]:
    st.markdown("##### 🏠 부천 보람마을 아주 23평")
    render_badge_card("매도 예상가", record["boram_price"], bool(record["boram_low_floor"]))

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
        st.caption(f"마지막 갱신: {format_kst(db.get_last_fetch_time(key))}")
        tx_df = db.get_recent_transactions(key, limit=10)
        if tx_df.empty:
            st.caption("수집된 실거래가가 없습니다. 사이드바에서 '지금 실거래가 갱신'을 눌러보세요.")
        else:
            tx_df = tx_df.copy()
            tx_df["price"] = tx_df["price"].apply(format_krw_eok)
            tx_df.columns = ["거래일", "아파트명", "거래가", "전용면적(㎡)", "층", "법정동"]
            st.dataframe(tx_df, hide_index=True, use_container_width=True)
