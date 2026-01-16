from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Neo4j connection
    NEO4J_URI: str = Field(default="bolt://yamabiko.proxy.rlwy.net:33306")
    NEO4J_USER: str = Field(default="neo4j")
    NEO4J_PASSWORD: str = Field(default="password")
    NEO4J_DATABASE: str = Field(default="neo4j")

    OPENAI_API_KEY: str = Field(default="neo4j")
    OPENAI_BASE_URL: str = Field(default="neo4j")
    OPENAI_MODEL: str = Field(default="neo4j")
    OPENAI_FIX_MODEL: str = Field(default="neo4j")

    # Driver tuning (reasonable defaults)
    NEO4J_MAX_POOL_SIZE: int = Field(default=3)
    NEO4J_CONNECTION_TIMEOUT_SEC: int = Field(default=15)

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()


