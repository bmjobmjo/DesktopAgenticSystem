from agents import registry


def _expense_prompt() -> str:
    return registry.AGENTS["expense_manager"]["prompt_path"].read_text(encoding="utf-8").lower()


def test_receipt_backed_mark_expense_defaults_to_creation():
    prompt = _expense_prompt()

    assert "creation-first interpretation" in prompt
    assert "a no-match result means proceed with creation" in prompt
    assert "at most one duplicate check is allowed" in prompt
    assert "do not broaden the search, scan all expenses, request an expense id" in prompt
    assert "never ask the user to confirm creation" in prompt


def test_expense_creation_uses_defaults_and_only_requires_amount():
    prompt = _expense_prompt()

    assert "require only `amount`" in prompt
    assert "default it to the current local date" in prompt
    assert "`entered_by_user_id = user_id`" in prompt
    assert "`project_id = null` unless" in prompt
    assert "ask one concise question for the amount only" in prompt
    assert "general`, `gneral`, and `genral`" in prompt


def test_expense_agent_description_advertises_creation_first_behavior():
    description = registry._BUILTIN_DESCRIPTIONS["expense_manager"].lower()

    assert "mark/log/record this expense" in description
    assert "creation unless" in description


def test_incoming_file_processor_does_not_claim_expense_creation():
    prompt_path = registry.AGENTS["incoming_file_processor"]["prompt_path"]
    prompt = prompt_path.read_text(encoding="utf-8").lower()

    assert "ingestion is not domain completion" in prompt
    assert "it does not create an expense" in prompt
    assert "`agent_call` to `expense_manager`" in prompt
    assert "`expenses.category_id`" in prompt
    assert "let `expense_manager` confirm expense creation or categorization" in prompt
