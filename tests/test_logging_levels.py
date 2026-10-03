import logging
from unittest.mock import patch

from lyo_app.core.logging import setup_logging


def test_production_logging_keeps_app_info_but_quiets_sqlalchemy():
    with patch("lyo_app.core.logging.settings.debug", False):
        setup_logging()

    assert logging.getLogger("lyo_app").level == logging.INFO
    assert logging.getLogger("uvicorn.error").level == logging.INFO
    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING
    assert logging.getLogger("sqlalchemy.pool").level == logging.WARNING


def test_debug_logging_restores_sqlalchemy_detail():
    with patch("lyo_app.core.logging.settings.debug", True):
        setup_logging()

    assert logging.getLogger("lyo_app").level == logging.DEBUG
    assert logging.getLogger("sqlalchemy.engine").level == logging.DEBUG
    assert logging.getLogger("sqlalchemy.pool").level == logging.DEBUG
