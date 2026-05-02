from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    anthropic_model: str = "claude-opus-4-6"
    agent_max_iterations: int = 10
    agent_tool_timeout: int = 30
    scenarios_dir: str = "data/scenarios"
    reports_dir: str = "data/reports"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
