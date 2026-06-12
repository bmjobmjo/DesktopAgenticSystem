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


def test_apply_bundled_embedding_defaults(tmp_path, monkeypatch):
    model_dir = tmp_path / 'models' / 'all-MiniLM-L6-v2'
    model_dir.mkdir(parents=True)
    (model_dir / 'modules.json').write_text('[]', encoding='utf-8')

    monkeypatch.setattr(cl, '_embedding_search_roots', lambda: [tmp_path])

    settings = {
        'embedding_model_name': 'all-MiniLM-L6-v2',
        'embedding_model_path': '',
        'embedding_local_files_only': False,
    }
    resolved, changed = cl.apply_bundled_embedding_defaults(settings)
    assert changed is True
    assert resolved['embedding_model_path'] == str(model_dir.resolve())
    assert resolved['embedding_local_files_only'] is True


def test_load_settings_into_cda_persists_bundled_embedding_path(tmp_path, monkeypatch):
    defaults_path = tmp_path / 'defaults.json'
    user_path = tmp_path / 'user_config.json'
    model_dir = tmp_path / 'models' / 'all-MiniLM-L6-v2'
    model_dir.mkdir(parents=True)
    (model_dir / 'modules.json').write_text('[]', encoding='utf-8')

    defaults = {
        'llm_provider': 'mock',
        'embedding_model_name': 'all-MiniLM-L6-v2',
        'embedding_model_path': '',
        'embedding_local_files_only': False,
    }
    defaults_path.write_text(json.dumps(defaults), encoding='utf-8')
    user_path.write_text(json.dumps({}), encoding='utf-8')

    monkeypatch.setattr(cl, 'DEFAULTS_PATH', defaults_path)
    monkeypatch.setattr(cl, 'USER_CONFIG_PATH', user_path)
    monkeypatch.setattr(cl, '_embedding_search_roots', lambda: [tmp_path])

    cda = CommonDataArea()
    cda.reset()
    cl.load_settings_into_cda(cda)

    assert cda.get_setting('embedding_model_path') == str(model_dir.resolve())
    assert cda.get_setting('embedding_local_files_only') is True
    persisted = json.loads(user_path.read_text(encoding='utf-8'))
    assert persisted['embedding_model_path'] == str(model_dir.resolve())
