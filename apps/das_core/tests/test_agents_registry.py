from agents import registry


def test_registry_lists_agents():
    agents = registry.list_agents()
    assert any(a['name'] == 'file_manager' for a in agents)


def test_registry_prompt_paths_exist():
    router_path = registry.ROUTER_PROMPT_PATH
    assert router_path.exists()
    agent = registry.get_agent('file_manager')
    assert agent['prompt_path'].exists()


def test_employee_manager_description_mentions_self_profile_requests():
    description = registry.BUILTIN_AGENTS['employee_manager']['description'].lower()
    assert 'my profile' in description
    assert 'my personal details' in description
    assert 'my email' in description


def test_default_role_policy_exposes_employee_manager():
    assert 'employee_manager' in registry.ROLE_AGENT_POLICY['User']
    assert 'employee_manager' in registry.ROLE_AGENT_POLICY['Manager']
    assert 'employee_manager' in registry.ROLE_AGENT_POLICY['Employee']


def test_attendance_prompt_allows_today_checkin_when_previous_day_is_open():
    agent = registry.get_agent('attendance_manager')
    prompt_path = agent['prompt_path']
    prompt_text = prompt_path.read_text(encoding='utf-8').lower()

    assert 'older open sessions from previous days do not block' in prompt_text
    assert 'already checked in for today' in prompt_text
