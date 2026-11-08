"""Exercise real child processes without SEC or AI requests."""
import time

import pytest

import main
from sec_core import DataUnavailable


def echo(ticker):
    return {"ticker": ticker}


def unavailable(ticker):
    raise DataUnavailable("fixture unavailable")


def broken(ticker):
    raise ValueError("fixture error")


def slow(ticker):
    time.sleep(10)


def test_child_result():
    assert main.isolated(echo, "TEST") == {"ticker": "TEST"}


def test_child_unavailable():
    with pytest.raises(DataUnavailable, match="fixture unavailable"):
        main.isolated(unavailable, "TEST")


def test_child_error():
    with pytest.raises(RuntimeError, match="fixture error"):
        main.isolated(broken, "TEST")


def test_child_timeout_releases_slot(monkeypatch):
    monkeypatch.setattr(main, "CHILD_LIMIT", 0.1)
    with pytest.raises(RuntimeError, match="stopped after"):
        main.isolated(slow, "TEST")
    monkeypatch.setattr(main, "CHILD_LIMIT", 30)
    assert main.isolated(echo, "TEST") == {"ticker": "TEST"}
