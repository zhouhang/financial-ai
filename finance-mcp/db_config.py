"""
数据库配置模块
从环境变量读取数据库配置
"""
import os
from pathlib import Path
from typing import Dict, Any

# 尝试加载 python-dotenv
try:
    from dotenv import load_dotenv
    # 加载 .env 文件
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # 如果没有安装 python-dotenv，使用系统环境变量
    pass


class DatabaseConfig:
    """数据库配置类"""
    
    def __init__(self):
        self.host = os.getenv('DB_HOST', 'localhost')
        self.port = int(os.getenv('DB_PORT', '5432'))
        self.database = os.getenv('DB_NAME', 'tally')
        self.user = os.getenv('DB_USER', 'tally_user')
        self.password = os.getenv('DB_PASSWORD', '123456')
    
    def get_connection_params(self) -> Dict[str, Any]:
        """获取连接参数字典"""
        return {
            'host': self.host,
            'port': self.port,
            'database': self.database,
            'user': self.user,
            'password': self.password
        }
    
    def get_connection_string(self) -> str:
        """获取连接字符串（用于 SQLAlchemy 等）"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    def __repr__(self):
        # 隐藏密码
        return f"DatabaseConfig(host={self.host}, port={self.port}, database={self.database}, user={self.user})"


# 全局配置实例
db_config = DatabaseConfig()


def get_db_connection():
    """
    获取数据库连接
    
    Returns:
        psycopg2 connection 对象
    """
    try:
        import psycopg2
        return psycopg2.connect(**db_config.get_connection_params())
    except ImportError:
        raise ImportError("请先安装 psycopg2-binary: pip install psycopg2-binary")
    except Exception as e:
        raise Exception(f"数据库连接失败: {str(e)}")


async def get_async_db_connection():
    """
    获取异步数据库连接（使用 asyncpg）
    
    Returns:
        asyncpg connection 对象
    """
    try:
        import asyncpg
        return await asyncpg.connect(
            host=db_config.host,
            port=db_config.port,
            database=db_config.database,
            user=db_config.user,
            password=db_config.password
        )
    except ImportError:
        raise ImportError("请先安装 asyncpg: pip install asyncpg")
    except Exception as e:
        raise Exception(f"异步数据库连接失败: {str(e)}")


if __name__ == "__main__":
    # 测试配置
    print("=" * 60)
    print("数据库配置信息:")
    print("=" * 60)
    print(db_config)
    print()
    print("连接字符串:")
    print(db_config.get_connection_string())
    print()
    
    # 测试连接
    try:
        conn = get_db_connection()
        print("✅ 数据库连接成功!")
        
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        print(f"PostgreSQL 版本: {version}")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ 数据库连接失败: {str(e)}")
