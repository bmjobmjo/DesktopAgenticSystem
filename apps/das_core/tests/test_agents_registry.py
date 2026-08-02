from agents import registry


def test_registry_lists_agents():
    agents = registry.list_agents()
    assert any(a['name'] == 'file_manager' for a in agents)


def test_registry_prompt_paths_exist():
    router_path = registry.ROUTER_PROMPT_PATH
    assert router_path.exists()
    agent = registry.get_agent('file_manager')
    assert agent['prompt_path'].exists()


def test_incoming_file_processor_is_a_registered_builtin_agent():
    agent = registry.BUILTIN_AGENTS['incoming_file_processor']
    loaded = registry.get_agent('incoming_file_processor')

    assert agent['prompt_file'].exists()
    assert loaded['name'] == 'incoming_file_processor'
    assert loaded['prompt_path'].exists()
    assert 'reusable file summary' in agent['description'].lower()
    assert 'does not create expenses' in agent['description'].lower()


def test_business_roles_can_route_attached_files_to_incoming_processor():
    assert 'incoming_file_processor' in registry.ROLE_AGENT_POLICY['Admin']
    assert 'incoming_file_processor' in registry.ROLE_AGENT_POLICY['User']
    assert 'incoming_file_processor' in registry.ROLE_AGENT_POLICY['Manager']
    assert 'incoming_file_processor' in registry.ROLE_AGENT_POLICY['Employee']


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


def test_task_manager_prompt_resolves_unambiguous_follow_up_context():
    agent = registry.get_agent('task_manager')
    prompt_path = agent['prompt_path']
    prompt_text = prompt_path.read_text(encoding='utf-8').lower()

    assert 'conversation continuity is required' in prompt_text
    assert 'do not treat a short follow-up confirmation as a new, context-free request' in prompt_text
