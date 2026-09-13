'''
这份代码，是项目数据库层的统一接口规范
BaseDatabase数据库连接基类：规定任何数据库（postgreSQL、MySQL）只要想接入，都应该实现
1.启动连接startup、2，关闭连接teardown、3.获取会话get_session

BaseRepository数据仓库基类：所有数据表的操作，都应该实现五个基础功能
1.创建create 2.查ID 3.更新 4.删除 5.列表查询
'''

from abc import ABC, abstractmethod
from typing import Any, ContextManager, Dict, List, Optional

from sqlalchemy.orm import Session


class BaseDatabase(ABC):
    """数据库操作基类"""

    @abstractmethod
    def startup(self) -> None:
        """初始化数据库连接"""

    @abstractmethod
    def teardown(self) -> None:
        """关闭数据库连接"""

    @abstractmethod
    def get_session(self) -> ContextManager[Session]:
        """获取数据库会话"""


class BaseRepository(ABC):
    """数据访问的基础仓库模式"""

    def __init__(self, session: Session):
        self.session = session

    @abstractmethod
    def create(self, data: Dict[str, Any]) -> Any:
        """创建新记录"""

    @abstractmethod
    def get_by_id(self, record_id: Any) -> Optional[Any]:
        """根据ID获取记录"""

    @abstractmethod
    def update(self, record_id: Any, data: Dict[str, Any]) -> Optional[Any]:
        """根据ID更新记录"""

    @abstractmethod
    def delete(self, record_id: Any) -> bool:
        """根据ID删除记录"""

    @abstractmethod
    def list(self, limit: int = 100, offset: int = 0) -> List[Any]:
        """分页列出记录"""