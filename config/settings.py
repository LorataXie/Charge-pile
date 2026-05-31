from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "mysql+asyncmy://root:password@localhost:3306/charging_station"
    JWT_SECRET: str = "dev-secret-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    WAITING_AREA_SIZE: int = 10
    PILE_QUEUE_LENGTH: int = 3
    FAST_PILE_COUNT: int = 3
    SLOW_PILE_COUNT: int = 2
    FAST_POWER_RATE: float = 30.0
    SLOW_POWER_RATE: float = 10.0
    SIM_TICK_MINUTES: int = 15

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
