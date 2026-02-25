from prompts.renderer import render


def test_render_replaces_placeholders():
    template = "Hello {{USER_PROMPT}} -- {{CHAT_HISTORY}}"
    data = {"USER_PROMPT": "World", "CHAT_HISTORY": ""}
    assert render(template, data) == "Hello World -- "


def test_render_missing_placeholder_is_empty():
    template = "A {{MISSING}} B"
    data = {}
    assert render(template, data) == "A  B"
