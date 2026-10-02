"""阶段 5：学习报表接口测试（GET /me/stats，TDD 先行）。

覆盖：
- 范围过滤（week / month / all）与按天趋势
- 整体正确率、各领域掌握度（按闯关聚合，累计不受范围影响）
- 空数据空态、参数校验、未登录
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tests.conftest import login_user, make_answer_record, make_quiz_record

pytestmark = pytest.mark.usefixtures("auth_settings")


class TestStatsEndpoint:
    def test_requires_login(self, client_db):
        resp = client_db.get("/api/v1/me/stats")
        assert resp.status_code == 401
        assert resp.json()["code"] == 4003

    def test_invalid_range_rejected(self, client_db):
        headers, _ = login_user(client_db, "dev_stats_bad")
        resp = client_db.get("/api/v1/me/stats?range=year", headers=headers)
        assert resp.status_code == 422
        assert resp.json()["code"] == 4000

    def test_empty_data_state(self, client_db):
        headers, _ = login_user(client_db, "dev_stats_empty")

        resp = client_db.get("/api/v1/me/stats?range=week", headers=headers)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["range"] == "week"
        assert data["overall_accuracy"] is None
        assert len(data["trend"]) == 7  # 本周一~周日
        assert all(point["accuracy"] is None for point in data["trend"])
        assert data["domains"] == []

    def test_week_trend_and_overall(self, client_db, db_session, sample_questions):
        """今天答 2 题对 1 题：week 视图应包含今天的数据点。"""
        headers, user_id = login_user(client_db, "dev_stats_week")
        quiz = make_quiz_record(db_session, user_id, sample_questions)
        now = datetime.now()
        make_answer_record(db_session, quiz, user_id, sample_questions[0], True, created_at=now)
        make_answer_record(db_session, quiz, user_id, sample_questions[1], False, created_at=now)

        resp = client_db.get("/api/v1/me/stats?range=week", headers=headers)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["overall_accuracy"] == 50
        today = now.date().isoformat()
        today_point = next(point for point in data["trend"] if point["date"] == today)
        assert today_point["total"] == 2
        assert today_point["correct"] == 1
        assert today_point["accuracy"] == 50

    def test_ranges_filter_by_date(self, client_db, db_session, sample_questions):
        """今天 1 对 + 35 天前 1 错：week/month 只看今天，all 看两条。"""
        headers, user_id = login_user(client_db, "dev_stats_ranges")
        quiz = make_quiz_record(db_session, user_id, sample_questions)
        now = datetime.now()
        old = now - timedelta(days=35)
        make_answer_record(db_session, quiz, user_id, sample_questions[0], True, created_at=now)
        make_answer_record(db_session, quiz, user_id, sample_questions[1], False, created_at=old)

        week = client_db.get("/api/v1/me/stats?range=week", headers=headers).json()["data"]
        month = client_db.get("/api/v1/me/stats?range=month", headers=headers).json()["data"]
        all_ = client_db.get("/api/v1/me/stats?range=all", headers=headers).json()["data"]

        assert week["overall_accuracy"] == 100
        assert month["overall_accuracy"] == 100
        assert all_["overall_accuracy"] == 50

        # all 的时间跨度覆盖 35 天前；week 只有 7 个点
        assert len(week["trend"]) == 7
        assert len(all_["trend"]) >= 36
        assert all_["trend"][0]["date"] == old.date().isoformat()

    def test_domains_aggregate_by_quiz(self, client_db, db_session, sample_questions):
        """各领域（按闯关）掌握度：累计统计，取最近更新的闯关。"""
        headers, user_id = login_user(client_db, "dev_stats_domains")
        quiz_a = make_quiz_record(db_session, user_id, sample_questions, title="RAG 入门")
        quiz_b = make_quiz_record(db_session, user_id, sample_questions, title="Python 基础")
        now = datetime.now()
        make_answer_record(db_session, quiz_a, user_id, sample_questions[0], True, created_at=now)
        make_answer_record(db_session, quiz_b, user_id, sample_questions[1], False, created_at=now)

        resp = client_db.get("/api/v1/me/stats?range=all", headers=headers)

        data = resp.json()["data"]
        names = {item["name"] for item in data["domains"]}
        assert names == {"RAG 入门", "Python 基础"}
        domain_a = next(item for item in data["domains"] if item["name"] == "RAG 入门")
        assert domain_a["accuracy"] == 100
        assert domain_a["quiz_id"] == quiz_a.quiz_id
