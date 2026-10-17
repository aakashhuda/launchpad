from __future__ import annotations

from src.tasks.retry import RetryPolicy


def test_should_retry_until_max_attempts():
    policy = RetryPolicy(max_attempts=3)
    assert policy.should_retry(1) is True
    assert policy.should_retry(2) is True
    assert policy.should_retry(3) is False
    assert policy.should_retry(4) is False


def test_delay_grows_exponentially_and_is_capped():
    policy = RetryPolicy(max_attempts=6, base_delay_seconds=5.0, max_delay_seconds=60.0)
    assert policy.delay_for(1) == 5.0
    assert policy.delay_for(2) == 10.0
    assert policy.delay_for(3) == 20.0
    assert policy.delay_for(4) == 40.0
    # 5 * 2**4 = 80 -> capped at 60.
    assert policy.delay_for(5) == 60.0
    assert policy.delay_for(99) == 60.0
