"""Regression checks for the read-only release schema gate."""
from sqlalchemy import create_engine, text

from scripts import check_release_schema as gate


def _schema(with_constraint):
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    connection.execute(text(
        "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
    ))
    connection.execute(text(
        "INSERT INTO alembic_version (version_num) VALUES (:revision)"
    ), {"revision": gate.EXPECTED_REVISION})
    constraint = (
        ", CONSTRAINT uq_platoon_microgame_member_day "
        "UNIQUE (period_start, game_key, user_id, score_day)"
        if with_constraint else ""
    )
    connection.execute(text(
        "CREATE TABLE platoon_game_activities ("
        "id INTEGER PRIMARY KEY, period_start DATE NOT NULL, "
        "game_key VARCHAR(40) NOT NULL, platoon_id INTEGER NOT NULL, "
        "user_id INTEGER NOT NULL, score_day DATE NOT NULL"
        + constraint + ")"
    ))
    return connection


def test_release_gate_fails_when_games_uniqueness_missing(monkeypatch):
    monkeypatch.setattr(gate, "REQUIRED_COLUMNS", {
        "platoon_game_activities": {
            "id", "period_start", "game_key", "platoon_id",
            "user_id", "score_day"
        }
    })
    monkeypatch.setattr(gate, "REQUIRED_INDEXES", {})
    connection = _schema(with_constraint=False)
    try:
        problems = gate.validate_schema(connection)
        assert any("Missing unique constraint: platoon_game_activities."
                   "uq_platoon_microgame_member_day" in p for p in problems)
    finally:
        connection.close()
        connection.engine.dispose()


def test_release_gate_accepts_games_uniqueness(monkeypatch):
    monkeypatch.setattr(gate, "REQUIRED_COLUMNS", {
        "platoon_game_activities": {
            "id", "period_start", "game_key", "platoon_id",
            "user_id", "score_day"
        }
    })
    monkeypatch.setattr(gate, "REQUIRED_INDEXES", {})
    connection = _schema(with_constraint=True)
    try:
        assert gate.validate_schema(connection) == []
    finally:
        connection.close()
        connection.engine.dispose()
