from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./charging_station.db"
    JWT_SECRET: str = "dev-secret-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    #等候区总车位容量 WaitingAreaSize。
    #修改后重新运行 python cli/seed.py 并重启后端即可生效。
    WAITING_AREA_SIZE: int = 10

    #每个充电桩排队队列长度 ChargingQueueLen。
    PILE_QUEUE_LENGTH: int = 3

    #快充电桩数量 FastCharingPileNum。
    FAST_PILE_COUNT: int = 3

    #慢充电桩数量 TrickleChargingPileNum。
    SLOW_PILE_COUNT: int = 2

    #快充/慢充功率，默认对应需求文档 30 度/小时、10 度/小时。
    FAST_POWER_RATE: float = 30.0
    SLOW_POWER_RATE: float = 10.0

    #仿真步长：每次Tick推进的虚拟分钟数。
    SIM_TICK_MINUTES: int = 15

    #如果项目根目录存在 .env，同名配置会覆盖上面的默认值，便于临时改参数。
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
