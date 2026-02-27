"""文件/Sheet 配对分析工具 - 基于已有智能匹配算法简化版"""

from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


def calculate_column_overlap(headers1: list[str], headers2: list[str]) -> tuple[float, list[str]]:
    """计算列名重叠度
    
    Returns: (重叠百分比, 共享列名列表)
    """
    if not headers1 or not headers2:
        return 0.0, []
    
    set1 = set(h.lower().strip() for h in headers1)
    set2 = set(h.lower().strip() for h in headers2)
    intersection = set1 & set2
    
    smaller_size = min(len(set1), len(set2))
    if smaller_size == 0:
        return 0.0, []
    
    overlap_pct = (len(intersection) / smaller_size) * 100
    shared_columns = [h for h in headers1 if h.lower().strip() in intersection]
    
    return overlap_pct, shared_columns


def suggest_best_pair(all_sheets: list[tuple[str, str, dict]]) -> dict[str, Any] | None:
    """从所有sheet中找出最佳配对
    
    Args:
        all_sheets: [(filename, sheet_name, sheet_data), ...]
        
    Returns:
        最佳配对结果字典
    """
    if len(all_sheets) < 2:
        return None
    
    best_score = 0
    best_pair = None
    
    for i in range(len(all_sheets)):
        for j in range(i + 1, len(all_sheets)):
            filename1, sheet1_name, sheet1 = all_sheets[i]
            filename2, sheet2_name, sheet2 = all_sheets[j]
            
            headers1 = sheet1.get('headers', [])
            headers2 = sheet2.get('headers', [])
            
            overlap_pct, shared_columns = calculate_column_overlap(headers1, headers2)
            
            # 简单评分：主要看列重叠度
            score = overlap_pct
            
            if score > best_score:
                best_score = score
                best_pair = {
                    'file1': {'filename': filename1, 'sheet': sheet1_name},
                    'file2': {'filename': filename2, 'sheet': sheet2_name},
                    'score': score,
                    'overlap_pct': overlap_pct,
                    'shared_columns': shared_columns[:5],  # 只显示前5个
                    'rationale': f"列名重叠 {overlap_pct:.0f}%，共享字段：{', '.join(shared_columns[:3])}"
                }
    
    return best_pair
