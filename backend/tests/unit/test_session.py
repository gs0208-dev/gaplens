from app.db.session import engine


def test_engine_hides_statement_parameters_from_error_messages() -> None:
    assert engine.sync_engine.hide_parameters is True
