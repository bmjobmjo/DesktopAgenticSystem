from agents import registry


def _prompt(agent_name: str) -> str:
    agent = registry.get_agent(agent_name)
    return agent["prompt_path"].read_text(encoding="utf-8").lower()


def test_task_manager_resolves_missing_membership_as_prerequisite():
    prompt = _prompt("task_manager")

    assert "implied prerequisite of the requested assignment" in prompt
    assert "do not ask the user to choose between backlog and an exception" in prompt
    assert "do not mark the overall request complete after only the membership step" in prompt


def test_organization_manager_returns_compound_assignment_to_task_manager():
    prompt = _prompt("organization_management_agent")

    assert "never stop after only the prerequisite" in prompt
    assert 'selected_agent = "task_manager"' in prompt
    assert "do not return `complete` after membership alone" in prompt


def test_project_manager_lists_named_users_tasks_across_projects():
    prompt = _prompt("project_manager")

    assert "list their assigned tasks across all projects" in prompt
    assert "do not ask which project" in prompt
    assert "without a `projectid` filter" in prompt


def test_non_router_descriptions_expose_membership_prerequisite_ownership():
    task_description = registry.BUILTIN_AGENTS["task_manager"]["description"].lower()
    organization_description = registry.BUILTIN_AGENTS[
        "organization_management_agent"
    ]["description"].lower()

    assert "membership-prerequisite coordination" in task_description
    assert "membership prerequisites handed off from task assignment workflows" in (
        organization_description
    )
