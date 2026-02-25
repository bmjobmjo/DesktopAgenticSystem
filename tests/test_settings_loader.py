import json

from core.common_data_area import CommonDataArea
from settings import config_loader as cl


def test_settings_load_merge_save(tmp_path, monkeypatch):
    defaults_path = tmp_path / 'defaults.json'
    user_path = tmp_path / 'user_config.json'

    defaults = {
        'llm_provider': 'mock',
        'gemini_api_key': '',
        'accessible_directories': [],
        'default_directory': ''
    }
    user = {
        'default_directory': 'C:/data',
        'accessible_directories': ['C:/data']
    }

    defaults_path.write_text(json.dumps(defaults), encoding='utf-8')
    user_path.write_text(json.dumps(user), encoding='utf-8')

    monkeypatch.setattr(cl, 'DEFAULTS_PATH', defaults_path)
    monkeypatch.setattr(cl, 'USER_CONFIG_PATH', user_path)

    merged = cl.load_settings()
    assert merged['llm_provider'] == 'mock'
    assert merged['default_directory'] == 'C:/data'
    assert merged['accessible_directories'] == ['C:/data']

    merged['llm_provider'] = 'gemini'
    cl.save_settings(merged)
    reloaded = json.loads(user_path.read_text(encoding='utf-8'))
    assert reloaded['llm_provider'] == 'gemini'


def test_load_settings_into_cda(tmp_path, monkeypatch):
    defaults_path = tmp_path / 'defaults.json'
    user_path = tmp_path / 'user_config.json'

    defaults = {
        'llm_provider': 'mock',
        'gemini_api_key': '',
        'accessible_directories': [],
        'default_directory': ''
    }
    defaults_path.write_text(json.dumps(defaults), encoding='utf-8')
    user_path.write_text(json.dumps({'default_directory': 'C:/x'}), encoding='utf-8')

    monkeypatch.setattr(cl, 'DEFAULTS_PATH', defaults_path)
    monkeypatch.setattr(cl, 'USER_CONFIG_PATH', user_path)

    cda = CommonDataArea()
    cda.reset()

    cl.load_settings_into_cda(cda)
    assert cda.get_setting('default_directory') == 'C:/x'
    assert cda.get_setting('llm_provider') == 'mock'
