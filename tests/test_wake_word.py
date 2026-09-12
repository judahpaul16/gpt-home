from src.wake_word import command_after_wake_word


def test_command_follows_the_wake_word():
    assert command_after_wake_word("computer whats the weather", "computer") == "whats the weather"


def test_wake_word_alone_yields_an_empty_command():
    assert command_after_wake_word("computer", "computer") == ""


def test_transcript_without_the_wake_word_is_ignored():
    assert command_after_wake_word("whats the weather", "computer") is None


def test_wake_word_inside_another_word_does_not_count():
    assert command_after_wake_word("my computers are slow", "computer") is None


def test_repeated_wake_word_hallucination_is_ignored():
    assert command_after_wake_word("computer computer computer computer", "computer") is None
    assert command_after_wake_word("computer thank you computer thank you", "computer") is None


def test_multi_word_keyword_and_case():
    assert command_after_wake_word("hey home turn on the lights", "Hey Home") == "turn on the lights"
