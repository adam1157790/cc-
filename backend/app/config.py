"""全局配置：从 .env 读取，见 .env.example"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 生成引擎
    volcengine_api_key: str = ""
    volcengine_t2v_model: str = "doubao-seedance-1-0-pro-250528"
    volcengine_i2v_model: str = "doubao-seedance-1-0-lite-t2v-250428"
    zhipu_api_key: str = ""
    zhipu_t2v_model: str = "cogvideox-3"
    zhipu_i2v_model: str = "cogvideox-3"

    # 文生图（与视频引擎相互独立，未配置 Key 则前端不显示对应选项）
    volcengine_image_model: str = "doubao-seedream-4-0-250828"
    zhipu_image_model: str = "cogview-4-250304"
    image_daily_quota: int = 20  # 文生图独立配额，不占用视频任务配额

    # 提示词优化 LLM
    llm_api_key: str = ""
    llm_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    llm_model: str = "doubao-seed-1-6-flash-250415"

    # 服务
    secret_key: str = "change-me-to-a-random-string"
    allow_registration: bool = True
    # 配额开关：false 时视频/文生图均不限次（自用场景）
    quota_enabled: bool = True
    max_concurrent_tasks: int = 3
    max_concurrent_image_tasks: int = 2  # 文生图独立并发上限
    default_daily_quota: int = 10


settings = Settings()
