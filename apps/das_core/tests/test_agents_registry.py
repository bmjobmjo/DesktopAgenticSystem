from agents import registry


def test_registry_lists_agents():
    agents = registry.list_agents()
    assert any(a['name'] == 'file_manager' for a in agents)


def test_registry_prompt_paths_exist():
    router_path = registry.ROUTER_PROMPT_PATH
    assert router_path.exists()
    agent = registry.get_agent('file_manager')
    assert agent['prompt_path'].exists()
