#!/usr/bin/env python3
"""
查询 PostgreSQL 数据库表结构
"""
import psycopg2
from psycopg2.extras import RealDictCursor

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'tally',
    'user': 'tally_user',
    'password': '123456'
}


def get_connection():
    """获取数据库连接"""
    return psycopg2.connect(**DB_CONFIG)


def list_all_tables(conn):
    """列出所有表"""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT 
                table_schema,
                table_name
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            AND table_type = 'BASE TABLE'
            ORDER BY table_schema, table_name;
        """)
        return cur.fetchall()


def get_table_schema(conn, table_name, schema='public'):
    """获取表结构详情"""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT 
                c.column_name,
                c.data_type,
                c.character_maximum_length,
                c.numeric_precision,
                c.numeric_scale,
                c.is_nullable,
                c.column_default,
                tc.constraint_type,
                kcu.constraint_name AS pk_constraint_name,
                pgd.description AS column_comment
            FROM information_schema.columns c
            LEFT JOIN information_schema.key_column_usage kcu 
                ON c.column_name = kcu.column_name 
                AND c.table_schema = kcu.table_schema
                AND c.table_name = kcu.table_name
            LEFT JOIN information_schema.table_constraints tc 
                ON kcu.constraint_name = tc.constraint_name
                AND kcu.table_schema = tc.table_schema
                AND kcu.table_name = tc.table_name
            LEFT JOIN pg_catalog.pg_statio_all_tables AS st 
                ON c.table_schema = st.schemaname 
                AND c.table_name = st.relname
            LEFT JOIN pg_catalog.pg_description pgd 
                ON pgd.objoid = st.relid 
                AND pgd.objsubid = c.ordinal_position
            WHERE c.table_name = %s AND c.table_schema = %s
            ORDER BY c.ordinal_position;
        """, (table_name, schema))
        return cur.fetchall()


def get_table_row_count(conn, table_name, schema='public'):
    """获取表行数"""
    with conn.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) FROM {schema}."{table_name}";')
        return cur.fetchone()[0]


def get_table_indexes(conn, table_name, schema='public'):
    """获取表索引信息"""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT
                indexname,
                indexdef
            FROM pg_indexes
            WHERE tablename = %s AND schemaname = %s;
        """, (table_name, schema))
        return cur.fetchall()


def print_table_schema(conn, table_name, schema='public'):
    """打印表结构"""
    print(f"\n{'='*80}")
    print(f"表名：{schema}.{table_name}")
    print(f"{'='*80}")
    
    # 行数
    try:
        row_count = get_table_row_count(conn, table_name, schema)
        print(f"行数：{row_count}")
    except:
        pass
    
    # 列信息
    columns = get_table_schema(conn, table_name, schema)
    
    if columns:
        print(f"\n{'列名':<30} {'类型':<20} {'可空':<6} {'默认值':<20} {'约束':<10}")
        print(f"{'-'*80}")
        for col in columns:
            column_name = col['column_name']
            data_type = col['data_type']
            if data_type == 'character varying':
                data_type = f"varchar({col['character_maximum_length']})"
            elif data_type == 'numeric' and col['numeric_precision']:
                data_type = f"numeric({col['numeric_precision']},{col['numeric_scale']})"
            
            is_nullable = 'YES' if col['is_nullable'] == 'YES' else 'NO'
            default = col['column_default'] or '-'
            constraint = 'PK' if col['constraint_type'] == 'PRIMARY KEY' else ''
            
            print(f"{column_name:<30} {data_type:<20} {is_nullable:<6} {str(default):<20} {constraint:<10}")
    
    # 索引信息
    indexes = get_table_indexes(conn, table_name, schema)
    if indexes:
        print(f"\n索引:")
        for idx in indexes:
            print(f"  - {idx['indexname']}")


def main():
    """主函数"""
    print("="*80)
    print("PostgreSQL 数据库表结构查询")
    print(f"数据库：{DB_CONFIG['database']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}")
    print("="*80)
    
    conn = get_connection()
    
    try:
        # 获取所有表
        tables = list_all_tables(conn)
        
        print(f"\n共找到 {len(tables)} 个表:\n")
        
        # 按 schema 分组
        from collections import defaultdict
        schema_tables = defaultdict(list)
        for table in tables:
            schema_tables[table['table_schema']].append(table['table_name'])
        
        # 打印每个表
        for schema, table_names in sorted(schema_tables.items()):
            print(f"\n{'='*80}")
            print(f"Schema: {schema}")
            print(f"{'='*80}")
            for table_name in sorted(table_names):
                print(f"  - {table_name}")
        
        # 打印每个表的详细结构
        print("\n\n" + "="*80)
        print("详细表结构")
        print("="*80)
        
        for table in tables:
            print_table_schema(conn, table['table_name'], table['table_schema'])
            
    finally:
        conn.close()


if __name__ == "__main__":
    main()
