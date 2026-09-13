from contextlib import contextmanager

from src.db.factory import make_database

#定义一个全局私有变量，存储唯一的数据库实例
_database = None


def get_database():
    global _database
    #声明使用全局变量
    if _database is None:
        _database = make_database()
    return _database


@contextmanager
def get_db_session():
    database = get_database()
    with database.get_session() as session:
        yield session
        #把创建好的会话session抛出去，外部with块里的代码会拿到这个session来用
        #with块结束后，会自动回到这里，执行后续清理
