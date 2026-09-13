from src.config import get_settings
from src.db.interfaces.base import BaseDatabase
from src.db.interfaces.postgresql import PostgreSQLDatabase
from src.schemas.database.config import PostgreSQLSettings


def make_database() -> BaseDatabase:
    settings = get_settings()

    config = PostgreSQLSettings(
        database_url=settings.postgres_database_url,
        echo_sql=settings.postgres_echo_sql,
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow,
    )

    database = PostgreSQLDatabase(config=config)
    database.startup()
    return database
#这段函数相当于去PostgreSQLSettings把参数拿过来，
# 然后把他里面构建好的engine给start up起来，然后给database，
# 所以这个database就是启动起来的postgreSQL