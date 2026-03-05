"""将 data 目录下所有 xlsx 文件转换为 Markdown 格式，方便 AI 读取。"""

import os
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

base = os.path.dirname(os.path.abspath(__file__))

xlsx_files = [f for f in os.listdir(base) if f.endswith('.xlsx')]
print(f"找到 {len(xlsx_files)} 个 xlsx 文件: {xlsx_files}\n")

for fname in xlsx_files:
    fpath = os.path.join(base, fname)
    md_path = os.path.join(base, fname.replace('.xlsx', '.md'))

    lines = [f"# {fname}\n"]
    try:
        xl = pd.ExcelFile(fpath)
        for sheet in xl.sheet_names:
            df = xl.parse(sheet, dtype=str).fillna('')
            lines.append(f"\n## Sheet: {sheet}\n")
            try:
                lines.append(df.to_markdown(index=False))
            except Exception:
                lines.append(df.to_string(index=False))
            lines.append("\n")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        print(f"✅ {fname} → {os.path.basename(md_path)}")
    except Exception as e:
        print(f"❌ {fname} 转换失败: {e}")

print("\n转换完成！")
