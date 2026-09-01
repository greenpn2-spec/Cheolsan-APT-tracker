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

import db
from molit_api import collect_transactions_for_complex


def get_service_key() -> str | None:
    key = os.environ.get("MOLIT_API_KEY")
    if key:
        return key
    stored = db.get_setting("molit_api_key")
    return stored


def run_full_refresh(months_back: int = 3) -> dict:
    """설정된 모든 단지에 대해 최근 실거래가를 수집하여 DB에 저장.

    Returns: {complex_key: inserted_count} 및 오류 시 'error' 포함.
    """
    service_key = get_service_key()
    if not service_key:
        return {"error": "MOLIT_API_KEY 가 설정되지 않았습니다."}

    db.init_db()
    complex_config = db.get_complex_config()
    summary = {}
    for key, cfg in complex_config.items():
        rows = collect_transactions_for_complex(
            complex_key=key,
            lawd_cd=cfg["lawd_cd"],
            keywords=cfg.get("keywords", []),
            service_key=service_key,
            months_back=months_back,
        )
        inserted = db.insert_transactions(rows)
        summary[key] = inserted
    return summary


_scheduler_instance = None


def start_background_scheduler(interval_hours: int = 24):
    """앱 프로세스 내에서 동작하는 BackgroundScheduler 시작 (싱글턴)."""
    global _scheduler_instance
    if _scheduler_instance is not None:
        return _scheduler_instance

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        run_full_refresh,
        "interval",
        hours=interval_hours,
        id="molit_refresh",
        replace_existing=True,
        next_run_time=None,
    )
    scheduler.start()
    _scheduler_instance = scheduler
    return scheduler


if __name__ == "__main__":
    result = run_full_refresh()
    print(result)
