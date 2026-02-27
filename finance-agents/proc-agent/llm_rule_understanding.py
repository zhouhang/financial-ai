"""LLM 规则理解器

使用大模型理解用户意图，从对话中提取规则信息。
"""

import json
import re
from typing import Dict, List, Any, Optional
from pathlib import Path


class LLMRuleUnderstanding:
    """LLM 规则理解器"""

    def __init__(self, llm=None):
        """初始化 LLM 规则理解器

        参数:
            llm: LLM 实例，如果为 None 则使用默认配置
        """
        self.llm = llm
        if self.llm is None:
            # 使用默认的 LLM 配置
            try:
                from langchain.chat_models import ChatOpenAI
                from langchain.schema import HumanMessage, SystemMessage
                
                self.llm = ChatOpenAI(
                    model="gpt-4",
                    temperature=0.3,
                    max_tokens=2000
                )
            except ImportError:
                print("警告：langchain 未安装，LLM 功能将受限")
                self.llm = None

    def extract_intent(self, user_message: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """从用户消息中提取意图

        参数:
            user_message: 用户消息
            context: 对话上下文

        返回:
            意图信息字典
        """
        if self.llm is None:
            # 简单的规则匹配
            return self._simple_intent_extraction(user_message, context)

        system_prompt = """你是一个规则创建助手。请分析用户的意图。

可能的意图类型：
- create_rule: 创建新规则（"我想创建一个规则"、"帮我创建一个..."）
- edit_rule: 编辑已有规则（"修改 XX 规则"、"更新 XX"）
- test_rule: 测试规则（"测试一下"、"运行这个规则"）
- confirm: 确认操作（"对的"、"好的"、"确认"）
- modify: 修改规则内容（"改成..."、"调整为..."）
- provide_info: 提供信息（"从 XX 文件读取"、"数据源是..."）
- chat: 普通聊天

用户消息：{user_message}

当前上下文：{context}

请返回 JSON 格式：
{{
    "intent": "create_rule",
    "rule_name": "规则名（如果提到了）",
    "confidence": 0.95,
    "extracted_info": {{
        "description": "规则描述（如果提到了）",
        "data_sources": ["数据源 1", "数据源 2"],
        "processing_logic": "处理逻辑描述"
    }},
    "needs_more_info": true/false  # 是否需要更多信息
}}
"""

        try:
            from langchain.schema import HumanMessage, SystemMessage
            
            prompt = system_prompt.format(
                user_message=user_message,
                context=json.dumps(context or {}, ensure_ascii=False)
            )
            
            messages = [
                SystemMessage(content="你是一个专业的规则创建助手，擅长理解用户意图。"),
                HumanMessage(content=prompt)
            ]
            
            response = self.llm.invoke(messages)
            content = response.content.strip()
            
            # 解析 JSON
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            
            result = json.loads(content)
            return result
            
        except Exception as e:
            print(f"LLM 意图识别失败：{e}")
            return self._simple_intent_extraction(user_message, context)

    def _simple_intent_extraction(self, user_message: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """简单的意图提取（不使用 LLM）

        参数:
            user_message: 用户消息
            context: 对话上下文

        返回:
            意图信息字典
        """
        message_lower = user_message.lower()
        
        # 意图关键词匹配
        intent_patterns = {
            'create_rule': ['创建.*规则', '新建.*规则', '帮我创建', '我想创建', '添加.*规则'],
            'edit_rule': ['修改.*规则', '编辑.*规则', '更新.*规则', '调整.*规则'],
            'test_rule': ['测试.*规则', '运行.*规则', '验证.*规则', '试一下'],
            'confirm': ['对的', '好的', '确认', '没问题', '可以', '是的'],
            'modify': ['改成', '改为', '调整为', '修改成', '变成'],
        }
        
        for intent, patterns in intent_patterns.items():
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    return {
                        "intent": intent,
                        "rule_name": self._extract_rule_name(user_message),
                        "confidence": 0.8,
                        "extracted_info": self._extract_info_simple(user_message),
                        "needs_more_info": intent == 'create_rule'
                    }
        
        # 默认返回聊天
        return {
            "intent": "chat",
            "rule_name": None,
            "confidence": 0.5,
            "extracted_info": {},
            "needs_more_info": False
        }

    def _extract_rule_name(self, user_message: str) -> Optional[str]:
        """提取规则名称

        参数:
            user_message: 用户消息

        返回:
            规则名称
        """
        # 匹配 "XX 规则"、"XX 分析"、"XX 整理"
        patterns = [
            r'["\']([^"\']+)["\'].*规则',  # "规则名"规则
            r'规则 ["\']([^"\']+)["\']',  # 规则"规则名"
            r'([^\s,，]+).*规则',  # XX 规则
            r'([^\s,，]+).*分析',  # XX 分析
            r'([^\s,，]+).*整理',  # XX 整理
        ]
        
        for pattern in patterns:
            match = re.search(pattern, user_message)
            if match:
                return match.group(1).strip()
        
        return None

    def _extract_info_simple(self, user_message: str) -> Dict[str, Any]:
        """简单提取信息

        参数:
            user_message: 用户消息

        返回:
            提取的信息
        """
        info = {}
        
        # 提取数据源
        if '从' in user_message and ('读取' in user_message or '文件' in user_message):
            # "从 XX 文件读取"
            match = re.search(r'从 (.+?) (?:读取 | 文件)', user_message)
            if match:
                info['data_sources'] = [match.group(1).strip()]
        
        # 提取描述
        if '分析' in user_message or '处理' in user_message:
            info['description'] = user_message
        
        return info

    def generate_rule_from_conversation(
        self,
        conversation: List[Dict[str, str]],
        collected_info: Dict[str, Any]
    ) -> str:
        """从对话生成规则

        参数:
            conversation: 对话历史
            collected_info: 收集到的信息

        返回:
            规则内容（Markdown 格式）
        """
        if self.llm is None:
            return self._generate_rule_template(collected_info)

        system_prompt = """根据以下对话和收集到的信息，生成一个完整的业务规则文件。

收集到的信息:
- 规则名：{rule_name}
- 描述：{description}
- 数据源：{data_sources}
- 处理逻辑：{processing_logic}

对话历史:
{conversation}

请生成 Markdown 格式的规则文件，包含:
1. 规则名称
2. 功能描述
3. 数据源
4. 处理规则（详细步骤）
5. 输出格式
6. 异常处理
"""

        try:
            conversation_text = "\n".join([
                f"{msg['role']}: {msg['content']}"
                for msg in conversation[-10:]  # 最近 10 轮对话
            ])
            
            prompt = system_prompt.format(
                rule_name=collected_info.get('rule_name', '未命名规则'),
                description=collected_info.get('description', ''),
                data_sources=', '.join(collected_info.get('data_sources', [])),
                processing_logic=collected_info.get('processing_logic', ''),
                conversation=conversation_text
            )
            
            from langchain.schema import HumanMessage, SystemMessage
            messages = [
                SystemMessage(content="你是一个专业的规则编写助手。"),
                HumanMessage(content=prompt)
            ]
            
            response = self.llm.invoke(messages)
            return response.content.strip()
            
        except Exception as e:
            print(f"LLM 规则生成失败：{e}")
            return self._generate_rule_template(collected_info)

    def _generate_rule_template(self, collected_info: Dict[str, Any]) -> str:
        """生成规则模板（不使用 LLM）

        参数:
            collected_info: 收集到的信息

        返回:
            规则内容（Markdown 格式）
        """
        rule_name = collected_info.get('rule_name', '未命名规则')
        description = collected_info.get('description', '业务规则')
        data_sources = collected_info.get('data_sources', [])
        processing_logic = collected_info.get('processing_logic', '按业务规则处理')
        
        return f"""# 规则：{rule_name}

## 基本信息

- **规则名称**: {rule_name}
- **描述**: {description}
- **创建时间**: {__import__('datetime').datetime.now().isoformat()}
- **状态**: draft

## 数据源

本规则需要从以下数据源读取数据：

{chr(10).join(f'- {source}' for source in data_sources)}

## 处理规则

{processing_logic}

## 输出格式

- 格式：Excel
- Sheet 名称：{rule_name}
- 字段：根据处理结果自动生成

## 异常处理

1. 数据缺失时跳过该记录
2. 格式错误时记录日志
3. 处理失败时返回错误信息

## 元数据

```json
{{
    "name": "{rule_name}",
    "description": "{description}",
    "data_sources": {json.dumps(data_sources, ensure_ascii=False)},
    "status": "draft"
}}
```
"""


# 全局 LLM 规则理解器实例
_llm_rule_understanding: Optional[LLMRuleUnderstanding] = None


def get_llm_rule_understanding() -> LLMRuleUnderstanding:
    """获取 LLM 规则理解器实例

    返回:
        LLM 规则理解器实例
    """
    global _llm_rule_understanding
    if _llm_rule_understanding is None:
        _llm_rule_understanding = LLMRuleUnderstanding()
    return _llm_rule_understanding
