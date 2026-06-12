from core.channel_commands import is_new_session_command


def test_is_new_session_command_accepts_exact_command_with_whitespace() -> None:
    assert is_new_session_command("/new")
    assert is_new_session_command("/new\r\n")
    assert is_new_session_command("  /new  \n")


def test_is_new_session_command_rejects_substrings_and_extra_text() -> None:
    assert not is_new_session_command("please /new")
    assert not is_new_session_command("/new please")
    assert not is_new_session_command("/new\nhello")
