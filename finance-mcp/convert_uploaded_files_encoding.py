#!/usr/bin/env python3
"""
手动转换已上传文件的编码为 UTF-8
"""
import chardet
from pathlib import Path
import sys

def convert_file_encoding(file_path: Path) -> bool:
    """
    转换文件编码为 UTF-8
    
    Args:
        file_path: 文件路径
        
    Returns:
        是否成功转换
    """
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}")
        return False
    
    print(f"\n处理文件: {file_path.name}")
    print(f"  路径: {file_path}")
    
    # 读取原始文件
    with open(file_path, 'rb') as f:
        content = f.read()
    
    print(f"  原始大小: {len(content)} 字节")
    
    # 检测编码
    detected = chardet.detect(content)
    encoding = detected.get('encoding', 'utf-8')
    confidence = detected.get('confidence', 0)
    
    print(f"  检测编码: {encoding} (置信度: {confidence:.2%})")
    
    # 如果已经是 UTF-8，跳过
    if encoding and encoding.lower().startswith('utf-8'):
        print(f"  ✅ 已经是 UTF-8 编码，跳过")
        return True
    
    # 如果检测不出编码或置信度低，尝试常见编码
    if not encoding or confidence < 0.7:
        print(f"  置信度低，尝试常见编码...")
        for try_encoding in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin1']:
            try:
                content.decode(try_encoding)
                encoding = try_encoding
                print(f"    ✅ 使用编码: {encoding}")
                break
            except (UnicodeDecodeError, LookupError):
                continue
    
    if not encoding:
        print(f"  ❌ 无法检测编码")
        return False
    
    # 转换编码
    try:
        text_content = content.decode(encoding)
        utf8_content = text_content.encode('utf-8-sig')  # UTF-8 with BOM
        
        # 备份原文件
        backup_path = file_path.with_suffix(file_path.suffix + '.bak')
        file_path.rename(backup_path)
        print(f"  备份原文件: {backup_path.name}")
        
        # 保存转换后的文件
        with open(file_path, 'wb') as f:
            f.write(utf8_content)
        
        print(f"  ✅ 编码转换成功: {encoding} → UTF-8-sig")
        print(f"  转换后大小: {len(utf8_content)} 字节")
        
        # 验证
        if utf8_content.startswith(b'\xef\xbb\xbf'):
            print(f"  ✅ 包含 UTF-8 BOM")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 转换失败: {str(e)}")
        # 恢复原文件
        if backup_path.exists():
            backup_path.rename(file_path)
        return False

def main():
    """主函数"""
    print("=" * 80)
    print("批量转换上传文件编码为 UTF-8")
    print("=" * 80)
    
    # 要转换的文件
    files_to_convert = [
        "uploads/2026/1/8/1767597466118_080439.csv",
        "uploads/2026/1/8/ads_finance_d_inc_channel_details_20260105152012277_0_080439.csv"
    ]
    
    script_dir = Path(__file__).parent
    success_count = 0
    failed_count = 0
    
    for file_path_str in files_to_convert:
        file_path = script_dir / file_path_str
        if convert_file_encoding(file_path):
            success_count += 1
        else:
            failed_count += 1
    
    print("\n" + "=" * 80)
    print("转换完成")
    print("=" * 80)
    print(f"成功: {success_count} 个文件")
    print(f"失败: {failed_count} 个文件")
    
    if failed_count == 0:
        print("\n✅ 所有文件转换成功！")
    else:
        print(f"\n⚠️ {failed_count} 个文件转换失败")

if __name__ == "__main__":
    main()

