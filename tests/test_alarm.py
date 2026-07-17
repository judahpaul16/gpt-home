from datetime import datetime

import pytest


def _alarm(load_source):
    return load_source("alarm_iso", "tools/alarm.py")


def test_parse_in_minutes(load_source):
    alarm = _alarm(load_source)
    before = datetime.now()
    delta = (alarm._parse_time_expression("in 5 minutes") - before).total_seconds()
    assert 295 <= delta <= 305


def test_parse_hours(load_source):
    alarm = _alarm(load_source)
    before = datetime.now()
    delta = (alarm._parse_time_expression("2 hours") - before).total_seconds()
    assert 7195 <= delta <= 7205


def test_parse_absolute_am(load_source):
    target = _alarm(load_source)._parse_time_expression("7:30 am")
    assert (target.hour, target.minute) == (7, 30)


def test_parse_absolute_pm(load_source):
    target = _alarm(load_source)._parse_time_expression("3:15 pm")
    assert (target.hour, target.minute) == (15, 15)


def test_parse_invalid_raises(load_source):
    with pytest.raises(ValueError):
        _alarm(load_source)._parse_time_expression("gibberish")
