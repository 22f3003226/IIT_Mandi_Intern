from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    openrouter_api_key: str = ""
    openrouter_model_classification: str = "openai/gpt-4o-mini"
    openrouter_model_extraction: str = "openai/gpt-4o-mini"
    db_path: str = "storage/app.db"
    storage_dir: str = "storage/files"


settings = Settings()
