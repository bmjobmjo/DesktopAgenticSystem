from core.common_data_area import CommonDataArea


def test_singleton_identity():
    a = CommonDataArea()
    b = CommonDataArea()
    assert a is b


def test_settings_and_memory_crud():
    cda = CommonDataArea()
    cda.reset()

    cda.set_setting('llm_provider', 'mock')
    assert cda.get_setting('llm_provider') == 'mock'
    assert cda.get_setting('missing', 'default') == 'default'

    cda.set_memory('last_tool', {'name': 'list_directory'})
    assert cda.get_memory('last_tool')['name'] == 'list_directory'
    assert cda.get_memory('missing', 42) == 42


def test_runtime_storage():
    cda = CommonDataArea()
    cda.reset()

    obj = {'k': 'v'}
    cda.set_runtime('router', obj)
    assert cda.get_runtime('router') is obj
    assert cda.get_runtime('missing') is None
