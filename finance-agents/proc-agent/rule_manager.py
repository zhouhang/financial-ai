"""规则管理器模块

支持规则的创建、编辑、删除、验证等功能。
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict


@dataclass
class RuleInfo:
    """规则信息"""
    name: str                    # 规则名称
    description: str             # 规则描述
    intent_keywords: List[str]   # 意图关键词
    data_sources: List[str]      # 数据源
    processing_rules: str        # 处理规则（Markdown）
    output_format: Dict          # 输出格式
    created_at: str              # 创建时间
    updated_at: str              # 更新时间
    user_id: Optional[str]       # 用户 ID（None 为公共规则）
    status: str = "draft"        # 状态：draft/testing/active


class RuleManager:
    """规则管理器"""

    def __init__(self, base_dir: Optional[Path] = None):
        """初始化规则管理器

        参数:
            base_dir: proc-agent 根目录，默认为当前文件所在目录
        """
        if base_dir is None:
            base_dir = Path(__file__).parent

        self.base_dir = base_dir
        self.references_dir = base_dir / "references"
        self.scripts_dir = base_dir / "scripts"
        self.users_dir = base_dir / "users"

        # 确保目录存在
        self.references_dir.mkdir(parents=True, exist_ok=True)
        self.scripts_dir.mkdir(parents=True, exist_ok=True)

    def _get_user_dir(self, user_id: str) -> Path:
        """获取用户目录

        参数:
            user_id: 用户 ID

        返回:
            用户目录路径
        """
        user_dir = self.users_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def _get_rule_path(self, rule_name: str, user_id: Optional[str] = None) -> Path:
        """获取规则文件路径

        参数:
            rule_name: 规则名称
            user_id: 用户 ID（None 为公共规则）

        返回:
            规则文件路径
        """
        if user_id:
            user_dir = self._get_user_dir(user_id)
            references_dir = user_dir / "references"
            references_dir.mkdir(parents=True, exist_ok=True)
            return references_dir / f"{rule_name}_rule.md"
        else:
            return self.references_dir / f"{rule_name}_rule.md"

    def _get_script_path(self, rule_name: str, user_id: Optional[str] = None) -> Path:
        """获取脚本文件路径

        参数:
            rule_name: 规则名称
            user_id: 用户 ID（None 为公共规则）

        返回:
            脚本文件路径
        """
        if user_id:
            user_dir = self._get_user_dir(user_id)
            scripts_dir = user_dir / "scripts"
            scripts_dir.mkdir(parents=True, exist_ok=True)
            return scripts_dir / f"{rule_name}_rule.py"
        else:
            return self.scripts_dir / f"{rule_name}_rule.py"

    def create_rule(
        self,
        rule_name: str,
        description: str,
        intent_keywords: List[str],
        data_sources: List[str],
        processing_rules: str,
        output_format: Dict,
        user_id: Optional[str] = None
    ) -> RuleInfo:
        """创建规则

        参数:
            rule_name: 规则名称
            description: 规则描述
            intent_keywords: 意图关键词列表
            data_sources: 数据源列表
            processing_rules: 处理规则（Markdown 格式）
            output_format: 输出格式定义
            user_id: 用户 ID（None 为公共规则）

        返回:
            规则信息
        """
        now = datetime.now().isoformat()

        rule_info = RuleInfo(
            name=rule_name,
            description=description,
            intent_keywords=intent_keywords,
            data_sources=data_sources,
            processing_rules=processing_rules,
            output_format=output_format,
            created_at=now,
            updated_at=now,
            user_id=user_id,
            status="draft"
        )

        # 保存规则文件
        rule_path = self._get_rule_path(rule_name, user_id)
        self._save_rule_file(rule_path, rule_info)

        return rule_info

    def _save_rule_file(self, rule_path: Path, rule_info: RuleInfo) -> None:
        """保存规则文件

        参数:
            rule_path: 规则文件路径
            rule_info: 规则信息
        """
        content = f"""# 规则：{rule_info.name}

## 基本信息

- **规则名称**: {rule_info.name}
- **描述**: {rule_info.description}
- **创建时间**: {rule_info.created_at}
- **更新时间**: {rule_info.updated_at}
- **状态**: {rule_info.status}
- **用户 ID**: {rule_info.user_id or '公共规则'}

## 意图识别

**关键词**: {', '.join(rule_info.intent_keywords)}

当用户请求中包含以上关键词时，将使用本规则进行处理。

## 数据源

本规则需要从以下数据源读取数据：

{chr(10).join(f'- {source}' for source in rule_info.data_sources)}

## 处理规则

{rule_info.processing_rules}

## 输出格式

```json
{json.dumps(rule_info.output_format, indent=2, ensure_ascii=False)}
```

## 元数据

```json
{json.dumps({{
    'name': rule_info.name,
    'description': rule_info.description,
    'intent_keywords': rule_info.intent_keywords,
    'data_sources': rule_info.data_sources,
    'created_at': rule_info.created_at,
    'updated_at': rule_info.updated_at,
    'user_id': rule_info.user_id,
    'status': rule_info.status
}}, indent=2, ensure_ascii=False)}
```
"""

        with open(rule_path, 'w', encoding='utf-8') as f:
            f.write(content)

    def list_rules(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取规则列表

        参数:
            user_id: 用户 ID（None 为公共规则 + 用户规则）

        返回:
            规则信息列表
        """
        rules = []

        # 公共规则
        if self.references_dir.exists():
            for rule_file in self.references_dir.glob("*_rule.md"):
                rule_info = self._load_rule_info(rule_file)
                if rule_info:
                    rules.append(rule_info)

        # 用户规则
        if user_id:
            user_dir = self._get_user_dir(user_id)
            user_references = user_dir / "references"
            if user_references.exists():
                for rule_file in user_references.glob("*_rule.md"):
                    rule_info = self._load_rule_info(rule_file)
                    if rule_info:
                        rules.append(rule_info)

        return rules

    def _load_rule_info(self, rule_path: Path) -> Optional[Dict[str, Any]]:
        """加载规则信息

        参数:
            rule_path: 规则文件路径

        返回:
            规则信息字典
        """
        try:
            content = rule_path.read_text(encoding='utf-8')

            # 从 Markdown 中提取元数据
            if '```json' in content:
                # 查找最后一个 JSON 块（元数据）
                json_blocks = content.split('```json')
                if len(json_blocks) > 1:
                    json_str = json_blocks[-1].split('```')[0].strip()
                    metadata = json.loads(json_str)

                    return {
                        'name': metadata.get('name', rule_path.stem),
                        'description': metadata.get('description', ''),
                        'intent_keywords': metadata.get('intent_keywords', []),
                        'data_sources': metadata.get('data_sources', []),
                        'created_at': metadata.get('created_at', ''),
                        'updated_at': metadata.get('updated_at', ''),
                        'user_id': metadata.get('user_id'),
                        'status': metadata.get('status', 'draft'),
                        'file_path': str(rule_path)
                    }
        except Exception as e:
            print(f"加载规则文件失败 {rule_path}: {e}")

        return None

    def get_rule(self, rule_name: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取规则详情

        参数:
            rule_name: 规则名称
            user_id: 用户 ID（None 优先查找公共规则）

        返回:
            规则信息字典，不存在则返回 None
        """
        # 先查找用户规则
        if user_id:
            user_dir = self._get_user_dir(user_id)
            user_rule_path = user_dir / "references" / f"{rule_name}_rule.md"
            if user_rule_path.exists():
                return self._load_rule_info(user_rule_path)

        # 查找公共规则
        public_rule_path = self.references_dir / f"{rule_name}_rule.md"
        if public_rule_path.exists():
            return self._load_rule_info(public_rule_path)

        return None

    def update_rule(
        self,
        rule_name: str,
        **kwargs
    ) -> Optional[RuleInfo]:
        """更新规则

        参数:
            rule_name: 规则名称
            **kwargs: 要更新的字段

        返回:
            更新后的规则信息，规则不存在则返回 None
        """
        # 查找规则
        rule_info = self.get_rule(rule_name)
        if not rule_info:
            return None

        user_id = rule_info.get('user_id')

        # 更新字段
        for key, value in kwargs.items():
            if key in rule_info:
                rule_info[key] = value

        # 更新时间
        rule_info['updated_at'] = datetime.now().isoformat()

        # 重新保存
        rule_path = self._get_rule_path(rule_name, user_id)
        rule_obj = RuleInfo(**rule_info)
        self._save_rule_file(rule_path, rule_obj)

        return rule_obj

    def delete_rule(self, rule_name: str, user_id: Optional[str] = None) -> bool:
        """删除规则

        参数:
            rule_name: 规则名称
            user_id: 用户 ID（None 只删除公共规则）

        返回:
            是否删除成功
        """
        rule_path = self._get_rule_path(rule_name, user_id)

        if rule_path.exists():
            rule_path.unlink()

            # 同时删除脚本文件
            script_path = self._get_script_path(rule_name, user_id)
            if script_path.exists():
                script_path.unlink()

            return True

        return False

    def get_rule_script(self, rule_name: str, user_id: Optional[str] = None) -> Optional[Path]:
        """获取规则对应的脚本路径

        参数:
            rule_name: 规则名称
            user_id: 用户 ID

        返回:
            脚本路径，不存在则返回 None
        """
        script_path = self._get_script_path(rule_name, user_id)
        if script_path.exists():
            return script_path
        return None


# 全局规则管理器实例
_rule_manager: Optional[RuleManager] = None


def get_rule_manager(base_dir: Optional[Path] = None) -> RuleManager:
    """获取规则管理器实例

    参数:
        base_dir: proc-agent 根目录

    返回:
        规则管理器实例
    """
    global _rule_manager
    if _rule_manager is None:
        _rule_manager = RuleManager(base_dir)
    return _rule_manager
