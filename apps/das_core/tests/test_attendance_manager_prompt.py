from agents import registry


def test_attendance_manager_allows_authorized_organization_reports():
    prompt = registry.get_agent("attendance_manager")["prompt_path"].read_text(encoding="utf-8").lower()

    assert "manager` and `admin` may list" in prompt
    assert "do not silently reduce it to the acting user's rows" in prompt
    assert "export_file" in prompt
    assert "send_whatsapp_file" in prompt
    assert "send_telegram_file" in prompt


def test_daily_task_and_work_diary_prompts_allow_authorized_team_reports():
    for agent_name in ("dailytask_manager", "work_diary_manager"):
        prompt = registry.get_agent(agent_name)["prompt_path"].read_text(encoding="utf-8").lower()
        assert "manager` or `admin`" in prompt
        assert "export_file" in prompt
        assert "send_whatsapp_file" in prompt
        assert "send_telegram_file" in prompt
