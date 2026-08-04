from app.config import Settings


def test_settings_have_expected_defaults():
    settings = Settings(_env_file=None)
    assert settings.openrouter_model_classification == "openai/gpt-4o-mini"
    assert settings.db_path == "storage/app.db"
    assert settings.storage_dir == "storage/files"
