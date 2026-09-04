# -*- coding: utf-8 -*-
"""실거래가 주기적 수집 스케줄러.

두 가지 방식으로 사용 가능:
1) 독립 실행/cron: `python scheduler.py` 를 crontab 이나 시스템 스케줄러에 등록.
   (Streamlit 프로세스와 무관하게 항상 안정적으로 동작하는 방식을 권장)
2) 앱 내장 스케줄러: app.py 사이드바에서 토글 시 APScheduler
   BackgroundScheduler 가 앱 프로세스 안에서 주기 실행됨. (앱이 켜져있는 동안만 동작)
"""

import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import db
from molit_api import collect_transactions_for_complex

# 매월 1일 오전 1시(KST)에 자동 갱신
MONTHLY_CRON_DAY = 1
MONTHLY_CRON_HOUR = 1
MONTHLY_CRON_MINUTE = 0
MONTHLY_CRON_TZ = "Asia/Seoul"


def get_service_key() -> str | None:
    key = os.environ.get("MOLIT_API_KEY")
    if key:
        return key
    stored = db.get_setting("molit_api_key")
    return stored


def run_full_refresh(months_back: int = 3) -> dict:
    """설정된 모든 단지에 대해 최근 실거래가를 수집하여 DB에 저장.

    Returns: {complex_key: {"inserted": int, "errors": [str, ...]}} 형태.
    MOLIT_API_KEY 자체가 없으면 최상위 'error' 키만 담아 반환한다.
    조회 중 발생한 오류(인증키 오류 등)는 조용히 무시하지 않고 각 단지별
    "errors" 목록에 그대로 남겨서 화면에서 원인을 확인할 수 있게 한다.
    """
    db.init_db()
    service_key = get_service_key()
    if not service_key:
        return {"error": "MOLIT_API_KEY 가 설정되지 않았습니다."}

    complex_config = db.get_complex_config()
    summary = {}
    for key, cfg in complex_config.items():
        rows, errors = collect_transactions_for_complex(
            complex_key=key,
            lawd_cd=cfg["lawd_cd"],
            keywords=cfg.get("keywords", []),
            service_key=service_key,
            months_back=months_back,
            dong_filter=cfg.get("dong_filter"),
            area_m2_targets=cfg.get("area_m2_targets"),
            area_m2_tolerance=cfg.get("area_m2_tolerance", 1.0),
        )
        inserted = db.insert_transactions(rows)
        summary[key] = {"inserted": inserted, "errors": errors}
    return summary


_scheduler_instance = None


def start_background_scheduler():
    """앱 프로세스 내에서 동작하는 BackgroundScheduler 시작 (싱글턴).

    매월 1일 오전 1시(KST)에 run_full_refresh를 자동 실행한다.
    Streamlit 앱이 켜져 있는 동안에만 유효하며, 앱을 항상 켜두지 않는다면
    scheduler.py를 시스템 cron에 등록하는 방식(README 참고)을 권장한다.
    """
    global _scheduler_instance
    if _scheduler_instance is not None:
        return _scheduler_instance

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        run_full_refresh,
        CronTrigger(
            day=MONTHLY_CRON_DAY,
            hour=MONTHLY_CRON_HOUR,
            minute=MONTHLY_CRON_MINUTE,
            timezone=MONTHLY_CRON_TZ,
        ),
        id="molit_refresh",
        replace_existing=True,
    )
    scheduler.start()
    _scheduler_instance = scheduler
    return scheduler


def is_background_scheduler_running() -> bool:
    return _scheduler_instance is not None and _scheduler_instance.running


if __name__ == "__main__":
    result = run_full_refresh()
    print(result)
