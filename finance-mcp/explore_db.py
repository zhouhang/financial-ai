#!/usr/bin/env python3
"""
数据库表结构探索脚本
"""
import subprocess
import sys

# 首先尝试安装 psycopg2-binary
print("📦 检查并安装 psycopg2-binary...")
try:
    import psycopg2
    print("✅ psycopg2 已安装")
except ImportError:
    print("⏳ 正在安装 psycopg2-binary...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary", "-q", "--break-system-packages"])
    print("✅ psycopg2-binary 安装完成")
    import psycopg2

from psycopg2 import sql
import json

# 连接数据库
try:
    # 首先尝试使用 finflux_user
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="finflux",
            user="finflux_user",
            password="123456"
        )
    except psycopg2.OperationalError:
        # 如果失败，尝试使用当前系统用户
        import os
        current_user = os.getenv('USER')
        print(f"⚠️  尝试使用系统用户: {current_user}")
        conn = psycopg2.connect(
            host="localhost",
            database="finflux",
            user=current_user
        )
    
    cur = conn.cursor()
    
    print("\n" + "=" * 80)
    print("✅ 成功连接到数据库 finflux")
    print("=" * 80)
    print()
    
    # 获取所有表
    cur.execute("""
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name;
    """)
    
    tables = cur.fetchall()
    
    print(f"📊 数据库中的表（共 {len(tables)} 个）：")
    print("-" * 80)
    
    table_info = {}
    
    for schema, table_name, table_type in tables:
        full_name = f"{schema}.{table_name}"
        print(f"\n📋 {full_name} ({table_type})")
        
        # 获取表的列信息
        cur.execute("""
            SELECT 
                column_name, 
                data_type, 
                character_maximum_length,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position;
        """, (schema, table_name))
        
        columns = cur.fetchall()
        
        # 获取主键信息
        cur.execute("""
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = %s::regclass AND i.indisprimary;
        """, (full_name,))
        
        primary_keys = [row[0] for row in cur.fetchall()]
        
        # 获取外键信息
        cur.execute("""
            SELECT
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
              AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = %s
              AND tc.table_name = %s;
        """, (schema, table_name))
        
        foreign_keys = cur.fetchall()
        
        # 获取表的行数
        try:
            cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(
                sql.Identifier(schema, table_name)
            ))
            row_count = cur.fetchone()[0]
        except:
            row_count = 0
        
        print(f"  记录数: {row_count}")
        
        if primary_keys:
            print(f"  🔑 主键: {', '.join(primary_keys)}")
        
        if foreign_keys:
            print(f"  🔗 外键:")
            for fk_col, fk_table, fk_ref in foreign_keys:
                print(f"    - {fk_col} -> {fk_table}.{fk_ref}")
        
        print(f"\n  列信息:")
        table_info[full_name] = {
            "columns": [],
            "primary_keys": primary_keys,
            "foreign_keys": foreign_keys,
            "row_count": row_count
        }
        
        for col_name, data_type, max_length, nullable, default in columns:
            pk_mark = " 🔑" if col_name in primary_keys else ""
            nullable_mark = "NULL" if nullable == "YES" else "NOT NULL"
            
            type_str = data_type
            if max_length:
                type_str += f"({max_length})"
            
            default_str = f" DEFAULT {default}" if default else ""
            
            print(f"    - {col_name:<30} {type_str:<20} {nullable_mark:<10}{default_str}{pk_mark}")
            
            table_info[full_name]["columns"].append({
                "name": col_name,
                "type": data_type,
                "max_length": max_length,
                "nullable": nullable,
                "default": default,
                "is_primary_key": col_name in primary_keys
            })
    
    print("\n" + "=" * 80)
    print("📈 数据库统计")
    print("=" * 80)
    print(f"总表数: {len(tables)}")
    
    # 获取数据库大小
    cur.execute("SELECT pg_size_pretty(pg_database_size('finflux'));")
    db_size = cur.fetchone()[0]
    print(f"数据库大小: {db_size}")
    
    # 保存表结构信息到文件
    output_file = '/Users/kevin/workspace/financial-ai/finance-mcp/db_schema_info.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(table_info, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n✅ 表结构信息已保存到: {output_file}")
    
    # 查询一些示例数据
    print("\n" + "=" * 80)
    print("📊 查询示例数据（每个表取前3条）")
    print("=" * 80)
    
    for schema, table_name, table_type in tables[:5]:  # 只查前5个表
        full_name = f"{schema}.{table_name}"
        try:
            cur.execute(sql.SQL("SELECT * FROM {} LIMIT 3").format(
                sql.Identifier(schema, table_name)
            ))
            rows = cur.fetchall()
            if rows:
                print(f"\n📋 {full_name} (前3条):")
                col_names = [desc[0] for desc in cur.description]
                print(f"  列名: {', '.join(col_names)}")
                for i, row in enumerate(rows, 1):
                    print(f"  行{i}: {row}")
        except Exception as e:
            print(f"\n⚠️  {full_name}: 无法查询 - {str(e)}")
    
    cur.close()
    conn.close()
    
    print("\n" + "=" * 80)
    print("✅ 数据库探索完成")
    print("=" * 80)
    
except Exception as e:
    print(f"❌ 连接失败: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
