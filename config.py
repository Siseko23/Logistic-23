import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY          = os.getenv("SECRET_KEY", "dev-secret")
    # Always store the SQLite file in the project root directory
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'freightflow.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PLATFORM_FEE_PCT    = float(os.getenv("PLATFORM_FEE_PCT", 26.7))

    # Mail
    MAIL_SERVER         = os.getenv("MAIL_SERVER", "localhost")
    MAIL_PORT           = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS        = os.getenv("MAIL_USE_TLS", "True") == "True"
    MAIL_USERNAME       = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD       = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_USERNAME", "support@movement.com")

    # Celery
    CELERY_BROKER_URL       = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND   = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

    # AI Matching weights
    AI_PRICE_WEIGHT     = 0.50
    AI_PERF_WEIGHT      = 0.35
    AI_PROX_WEIGHT      = 0.15

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    "development": DevelopmentConfig,
    "production":  ProductionConfig,
    "default":     DevelopmentConfig,
}
