"""Unit tests for ``src/memory/short_term.py``."""

import pytest

from memory.short_term import SessionContext, ShortTermMemory


def test_get_session_creates_empty_context_on_first_access():
    mem = ShortTermMemory()
    ctx = mem.get_session("s1")

    assert isinstance(ctx, SessionContext)
    assert ctx.messages == []
    assert ctx.last_sql is None
    assert ctx.assumptions == []
    assert ctx.recent_tables == set()


def test_get_session_returns_same_instance_on_repeated_access():
    mem = ShortTermMemory()
    ctx1 = mem.get_session("s1")
    ctx2 = mem.get_session("s1")

    assert ctx1 is ctx2


def test_add_message_appends_in_order():
    mem = ShortTermMemory()
    mem.add_message("s1", "user", "hello")
    mem.add_message("s1", "assistant", "hi")

    assert mem.get_messages("s1") == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_add_message_truncates_when_exceeding_max_messages():
    mem = ShortTermMemory(max_messages=3)
    for i in range(5):
        mem.add_message("s1", "user", f"m{i}")

    messages = mem.get_messages("s1")
    assert len(messages) == 3
    assert [m["content"] for m in messages] == ["m2", "m3", "m4"]


def test_messages_are_isolated_between_sessions():
    mem = ShortTermMemory()
    mem.add_message("s1", "user", "only s1")
    mem.add_message("s2", "user", "only s2")

    assert mem.get_messages("s1") == [{"role": "user", "content": "only s1"}]
    assert mem.get_messages("s2") == [{"role": "user", "content": "only s2"}]


def test_get_messages_returns_independent_copy():
    mem = ShortTermMemory()
    mem.add_message("s1", "user", "hello")

    copy = mem.get_messages("s1")
    copy.append({"role": "fake", "content": "mutation"})

    # Internal state unaffected
    assert mem.get_messages("s1") == [{"role": "user", "content": "hello"}]


@pytest.mark.parametrize(
    "key,value",
    [
        ("last_sql", "SELECT 1"),
        ("last_query_plan", "plan text"),
        ("last_result_summary", "5 rows returned"),
    ],
)
def test_set_and_get_known_context_fields(key, value):
    mem = ShortTermMemory()
    mem.set_context("s1", key, value)

    assert mem.get_context("s1", key) == value


def test_set_context_for_unknown_key_goes_to_extra():
    mem = ShortTermMemory()
    mem.set_context("s1", "custom_flag", True)

    assert mem.get_context("s1", "custom_flag") is True


def test_get_context_for_missing_unknown_key_returns_none():
    mem = ShortTermMemory()
    assert mem.get_context("s1", "never_set") is None


def test_reset_drops_session():
    mem = ShortTermMemory()
    mem.add_message("s1", "user", "hello")
    mem.reset("s1")

    # Re-accessing creates fresh, empty context
    assert mem.get_messages("s1") == []


def test_reset_is_noop_for_unknown_session():
    mem = ShortTermMemory()
    mem.reset("never-existed")  # must not raise
