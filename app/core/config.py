# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information.
import os
from dataclasses import dataclass
from dotenv import load_dotenv

"""
Central de configurações (Settings) do BuildFlow.


- Carrega variáveis do .env (app/env/db/log/cors/open‑meteo).
- Fornece defaults seguros e tipados via dataclass.
- Expõe `settings` como singleton para uso em toda a app.
"""

load_dotenv()

@dataclass
class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "BuildFlow")
    APP_ENV: str = os.getenv("APP_ENV", "local")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))


    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "5"))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))

    CORS_ORIGINS: list[str] = tuple(
        origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()
    )

    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "10"))
    ALLOWED_IMAGE_TYPES: tuple[str, ...] = tuple(
        t.strip() for t in os.getenv("ALLOWED_IMAGE_TYPES", "image/jpeg,image/png,image/webp").split(",") if t.strip()
    )

    OPEN_METEO_ENABLED: bool = True
    OPEN_METEO_TIMEOUT_S: int = int(os.getenv("OPEN_METEO_TIMEOUT_S", "8"))
    OPEN_METEO_DAILY_PARAMS: str = os.getenv(
    "OPEN_METEO_DAILY_PARAMS",
    "weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
)
    OPEN_METEO_TIMEZONE: str = os.getenv("OPEN_METEO_TIMEZONE", "UTC")
    OPEN_METEO_RETRIES: int = int(os.getenv("OPEN_METEO_RETRIES", "2"))
    OPEN_METEO_RETRY_BACKOFF_MS: int = int(os.getenv("OPEN_METEO_RETRY_BACKOFF_MS", "250"))

    DEFAULT_LATITUDE: float = float(os.getenv("DEFAULT_LATITUDE", "41.15"))
    DEFAULT_LONGITUDE: float = float(os.getenv("DEFAULT_LONGITUDE", "-8.61"))

settings = Settings()
