import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from src.db.interfaces.base import BaseDatabase
from src.schemas.database.config import PostgreSQLSettings

logger = logging.getLogger(__name__)

Base = declarative_base()
#会创建一个ORM 模型的基类，定义了所有数据库表模型的通用行为，
# 比如如何映射到数据库表、如何处理字段类型、如何生成SQL语句。
#后面的数据库表模型都要继承它，所有继承Base的模型，都会被自动注册到它的metadata属性里。
#后续创建/更新数据库表时，只需要调用Base.metadata.create_all(engine)，就能一次性创建所有表。
#SQLAlchemy ORM的入口：没有它，你就没法用“类”和“对象”的方式来操作数据库，只能写原生SQL。

class PostgreSQLDatabase(BaseDatabase):
#继承了BaseDatabase类
    def __init__(self, config: PostgreSQLSettings):
        self.config = config
        self.engine: Optional[Engine] = None
        #self.engine是SQLAlchemy的核心对象，代表数据库连接池
        #先初始化为None，构造实例时不连接数据库，真正用的时候再创造
        self.session_factory: Optional[sessionmaker] = None
        #self.session_factory是用来创建数据库会话的工厂

    def startup(self) -> None: #none表示没有返回值
        '''
        做了五件事情:1.连接PostgreSQL，2.配置连接池，3.测试连接是否有效
        4.自动创建所有数据表，5.记录日志，方便排查问题
        '''
        try:
            logger.info(
                f"Attempting to connect to PostgreSQL at: {self.config.database_url.split('@')[1] if '@' in self.config.database_url else 'localhost'}"
            )

            self.engine = create_engine(
                self.config.database_url,
                echo=self.config.echo_sql,
                pool_size=self.config.pool_size,
                max_overflow=self.config.max_overflow,
                pool_pre_ping=True,
            )
            #根据配置里的URL链接PostgreSQL，设置连接池，echo控制是否打印SQL日志
            #pool_pre_ping=True开启链接有效性检查

            self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
            #创建一个数据路绘画工厂，后面的增删改查，都由它来生成会话执行
            assert self.engine is not None
            #确保engine已经成功创建，没创建成功直接报错
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                logger.info("Database connection test successful")
            #从连接池里面拿一个链接，向数据库发送一条简单的查询，成功执行就返回日志

            inspector = inspect(self.engine)
            existing_tables = inspector.get_table_names()
            #调用get_table_names()获取数据库里已经存在的所有表明

            Base.metadata.create_all(bind=self.engine)
            #根据base里面的模型创建对应的表，要是没有就创建，有就不管他，然后绑定到engine

            updated_tables = inspector.get_table_names()
            new_tables = set(updated_tables) - set(existing_tables)

            if new_tables:
                logger.info(f"Created new tables: {', '.join(new_tables)}")
            else:
                logger.info("All tables already exist - no new tables created")

            logger.info("PostgreSQL database initialized successfully")
            assert self.engine is not None
            logger.info(f"Database: {self.engine.url.database}")
            logger.info(f"Total tables: {', '.join(updated_tables) if updated_tables else 'None'}")
            logger.info("Database connection established")

        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL database: {e}")
            raise

    def teardown(self) -> None:
        if self.engine:
            self.engine.dispose()
            logger.info("PostgreSQL database connections closed")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        if not self.session_factory:
            raise RuntimeError("Database not initialized. Call startup() first.")

        session = self.session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
