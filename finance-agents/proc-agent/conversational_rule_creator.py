"""对话式规则创建 LangGraph 子图

实现基于对话的规则创建、编辑、验证流程。
"""

from __future__ import annotations

from typing import Dict, List, Any, Optional, TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage


# ──────────────────────────────────────────────────────────────────────────────
# 状态定义
# ──────────────────────────────────────────────────────────────────────────────

class RuleCreationState(TypedDict, total=False):
    """规则创建状态"""
    
    # 对话上下文
    messages: List[Dict[str, str]]  # 对话历史
    user_id: Optional[str]  # 用户 ID
    
    # 规则信息（逐步填充）
    rule_name: Optional[str]  # 规则名称
    rule_description: Optional[str]  # 规则描述
    data_sources: List[str]  # 数据源列表
    processing_logic: Optional[str]  # 处理逻辑
    
    # 对话状态
    current_step: str  # collecting_info, generating_rule, confirming, testing, completed
    missing_info: List[str]  # 还缺少的信息
    
    # 生成的规则
    generated_rule_content: Optional[str]  # 生成的规则内容
    generated_script_path: Optional[str]  # 生成的脚本路径
    
    # 验证结果
    test_result: Optional[Dict[str, Any]]  # 测试结果
    validation_report: Optional[str]  # 验证报告
    
    # 系统消息
    system_message: Optional[str]  # 要返回给用户的消息


# ──────────────────────────────────────────────────────────────────────────────
# 节点函数
# ──────────────────────────────────────────────────────────────────────────────

def intent_recognition_node(state: RuleCreationState) -> Dict[str, Any]:
    """意图识别节点

    识别用户意图：创建规则、编辑规则、测试规则、提供信息等
    """
    from .llm_rule_understanding import get_llm_rule_understanding
    
    messages = state.get('messages', [])
    if not messages:
        return {"system_message": "您好！我是规则创建助手，请问有什么可以帮您？"}
    
    # 获取最后一条用户消息
    last_message = messages[-1]
    if last_message.get('role') != 'user':
        return {}
    
    user_message = last_message.get('content', '')
    
    # 使用 LLM 识别意图
    llm_understanding = get_llm_rule_understanding()
    intent_result = llm_understanding.extract_intent(
        user_message=user_message,
        context={
            'rule_name': state.get('rule_name'),
            'current_step': state.get('current_step')
        }
    )
    
    intent = intent_result.get('intent', 'chat')
    
    # 提取信息
    extracted_info = intent_result.get('extracted_info', {})
    updates = {}
    
    if extracted_info.get('rule_name'):
        updates['rule_name'] = extracted_info['rule_name']
    if extracted_info.get('description'):
        updates['rule_description'] = extracted_info['description']
    if extracted_info.get('data_sources'):
        updates['data_sources'] = extracted_info['data_sources']
    
    # 根据意图设置下一步
    if intent == 'create_rule':
        updates['current_step'] = 'collecting_info'
        updates['system_message'] = "好的，请描述一下这个规则是用来做什么的？"
    elif intent == 'provide_info':
        # 用户正在提供信息
        updates['current_step'] = state.get('current_step', 'collecting_info')
    elif intent == 'confirm':
        # 用户确认
        if state.get('current_step') == 'generating_rule':
            updates['current_step'] = 'saving_rule'
    elif intent == 'modify':
        # 用户要求修改
        updates['current_step'] = 'modifying_rule'
    
    return updates


def collect_info_node(state: RuleCreationState) -> Dict[str, Any]:
    """信息收集节点

    收集创建规则所需的信息
    """
    from .llm_rule_understanding import get_llm_rule_understanding
    
    messages = state.get('messages', [])
    rule_name = state.get('rule_name')
    description = state.get('rule_description')
    data_sources = state.get('data_sources', [])
    
    # 检查还缺少什么信息
    missing = []
    if not rule_name:
        missing.append('规则名称')
    if not description:
        missing.append('规则描述')
    if not data_sources:
        missing.append('数据源')
    
    if not missing:
        # 信息完整，进入生成阶段
        return {
            'current_step': 'generating_rule',
            'missing_info': []
        }
    
    # 生成提示语
    llm_understanding = get_llm_rule_understanding()
    last_message = messages[-1].get('content', '') if messages else ''
    
    # 从对话中提取更多信息
    intent_result = llm_understanding.extract_intent(last_message, state)
    extracted = intent_result.get('extracted_info', {})
    
    updates = {}
    if extracted.get('rule_name') and not rule_name:
        updates['rule_name'] = extracted['rule_name']
    if extracted.get('description') and not description:
        updates['rule_description'] = extracted['description']
    if extracted.get('data_sources') and not data_sources:
        updates['data_sources'] = extracted['data_sources']
    
    # 生成回复
    if missing[0] == '规则名称' and not updates.get('rule_name'):
        updates['system_message'] = "好的，请给这个规则起个名字，比如'应收账款分析'、'流水整理'等"
    elif (missing[0] == '规则描述' or '规则描述' in missing) and not updates.get('rule_description'):
        updates['system_message'] = "好的，请描述一下这个规则要做什么处理？比如'分析账龄和回收率'"
    elif (missing[0] == '数据源' or '数据源' in missing) and not updates.get('data_sources'):
        updates['system_message'] = "明白了，需要从哪些文件读取数据？比如'应收账款明细表'、'银行流水'"
    
    updates['missing_info'] = [m for m in missing if not updates.get(m.lower().replace('名称', '_name').replace('描述', '_description').replace('数据源', '_data_sources'))]
    
    return updates


def generate_rule_node(state: RuleCreationState) -> Dict[str, Any]:
    """生成规则节点

    根据收集到的信息生成规则文件和脚本
    """
    from .llm_rule_understanding import get_llm_rule_understanding
    from .rule_manager import get_rule_manager
    from .script_generator import get_script_generator
    
    rule_name = state.get('rule_name')
    description = state.get('rule_description')
    data_sources = state.get('data_sources', [])
    processing_logic = state.get('processing_logic')
    user_id = state.get('user_id')
    
    if not rule_name:
        return {"system_message": "错误：规则名称为空"}
    
    # 使用 LLM 生成规则内容
    llm_understanding = get_llm_rule_understanding()
    messages = state.get('messages', [])
    
    collected_info = {
        'rule_name': rule_name,
        'description': description or f'{rule_name}业务规则',
        'data_sources': data_sources,
        'processing_logic': processing_logic or '根据业务规则进行处理'
    }
    
    rule_content = llm_understanding.generate_rule_from_conversation(
        conversation=messages,
        collected_info=collected_info
    )
    
    # 保存规则
    try:
        rule_manager = get_rule_manager()
        
        # 解析规则内容中的元数据
        import json
        import re
        
        metadata = {}
        json_match = re.search(r'```json\s*(.+?)\s*```', rule_content, re.DOTALL)
        if json_match:
            try:
                metadata = json.loads(json_match.group(1))
            except:
                pass
        
        # 创建规则
        rule_info = rule_manager.create_rule(
            rule_name=rule_name,
            description=metadata.get('description', description),
            intent_keywords=[rule_name],  # 简化处理
            data_sources=data_sources,
            processing_rules=rule_content,
            output_format={'format': 'excel'},
            user_id=user_id
        )
        
        # 生成脚本
        script_generator = get_script_generator()
        script_result = script_generator.generate_script(
            rule_name=rule_name,
            rule_info=rule_info
        )
        
        return {
            'generated_rule_content': rule_content,
            'generated_script_path': script_result.get('script_path'),
            'current_step': 'confirming',
            'system_message': f"✅ 规则已生成！\n\n规则名：{rule_name}\n数据源：{', '.join(data_sources)}\n\n请确认是否正确？需要修改请告诉我。"
        }
        
    except Exception as e:
        return {
            'current_step': 'collecting_info',
            'system_message': f"生成规则失败：{str(e)}"
        }


def confirm_node(state: RuleCreationState) -> Dict[str, Any]:
    """确认节点

    等待用户确认规则
    """
    # 这个节点主要由用户消息触发，在 intent_recognition_node 中处理
    return {}


def test_rule_node(state: RuleCreationState) -> Dict[str, Any]:
    """测试规则节点

    执行脚本测试规则
    """
    from .rule_creation_processor import get_rule_creation_processor
    
    rule_name = state.get('rule_name')
    user_id = state.get('user_id')
    
    if not rule_name:
        return {"system_message": "错误：规则名称为空"}
    
    # TODO: 需要用户上传测试数据
    # 这里先返回提示信息
    return {
        'current_step': 'testing',
        'system_message': f"好的，请上传测试数据文件来测试规则 '{rule_name}'"
    }


def save_rule_node(state: RuleCreationState) -> Dict[str, Any]:
    """保存规则节点

    将规则状态更新为 active
    """
    from .rule_manager import get_rule_manager
    
    rule_name = state.get('rule_name')
    user_id = state.get('user_id')
    
    if not rule_name:
        return {"system_message": "错误：规则名称为空"}
    
    try:
        rule_manager = get_rule_manager()
        rule_manager.update_rule(rule_name, status='active', user_id=user_id)
        
        return {
            'current_step': 'completed',
            'system_message': f"✅ 规则 '{rule_name}' 已激活并保存！\n\n现在可以使用这个规则处理数据了。"
        }
    except Exception as e:
        return {
            'system_message': f"保存规则失败：{str(e)}"
        }


# ──────────────────────────────────────────────────────────────────────────────
# 路由函数
# ──────────────────────────────────────────────────────────────────────────────

def route_after_intent(state: RuleCreationState) -> str:
    """意图识别后的路由"""
    current_step = state.get('current_step', 'collecting_info')
    
    if current_step == 'collecting_info':
        return 'collect_info'
    elif current_step == 'generating_rule':
        return 'generate_rule'
    elif current_step == 'confirming':
        return 'confirm'
    elif current_step == 'testing':
        return 'test_rule'
    elif current_step == 'saving_rule':
        return 'save_rule'
    elif current_step == 'completed':
        return END
    else:
        return 'collect_info'


def route_after_collect(state: RuleCreationState) -> str:
    """信息收集后的路由"""
    missing_info = state.get('missing_info', [])
    
    if not missing_info:
        return 'generate_rule'
    else:
        return END  # 继续等待用户输入


def route_after_generate(state: RuleCreationState) -> str:
    """生成规则后的路由"""
    return 'confirm'


def route_after_confirm(state: RuleCreationState) -> str:
    """确认后的路由"""
    # 由用户消息决定下一步
    messages = state.get('messages', [])
    if messages:
        last_msg = messages[-1].get('content', '').lower()
        if '确认' in last_msg or '好的' in last_msg or '对的' in last_msg:
            return 'save_rule'
        elif '测试' in last_msg or '试一下' in last_msg:
            return 'test_rule'
        elif '修改' in last_msg or '调整' in last_msg:
            return 'collect_info'
    
    return END


# ──────────────────────────────────────────────────────────────────────────────
# 图构建器
# ──────────────────────────────────────────────────────────────────────────────

def build_rule_creation_graph() -> StateGraph:
    """构建规则创建子图"""
    builder = StateGraph(RuleCreationState)
    
    # 添加节点
    builder.add_node('intent_recognition', intent_recognition_node)
    builder.add_node('collect_info', collect_info_node)
    builder.add_node('generate_rule', generate_rule_node)
    builder.add_node('confirm', confirm_node)
    builder.add_node('test_rule', test_rule_node)
    builder.add_node('save_rule', save_rule_node)
    
    # 设置入口点
    builder.set_entry_point('intent_recognition')
    
    # 添加边
    builder.add_conditional_edges(
        'intent_recognition',
        route_after_intent,
        {
            'collect_info': 'collect_info',
            'generate_rule': 'generate_rule',
            'confirm': 'confirm',
            'test_rule': 'test_rule',
            'save_rule': 'save_rule',
            END: END
        }
    )
    
    builder.add_conditional_edges(
        'collect_info',
        route_after_collect,
        {
            'generate_rule': 'generate_rule',
            END: END
        }
    )
    
    builder.add_conditional_edges(
        'generate_rule',
        route_after_generate,
        {
            'confirm': 'confirm'
        }
    )
    
    builder.add_conditional_edges(
        'confirm',
        route_after_confirm,
        {
            'save_rule': 'save_rule',
            'test_rule': 'test_rule',
            'collect_info': 'collect_info',
            END: END
        }
    )
    
    builder.add_edge('save_rule', END)
    builder.add_edge('test_rule', END)
    
    return builder


# ──────────────────────────────────────────────────────────────────────────────
# 处理器
# ──────────────────────────────────────────────────────────────────────────────

class ConversationalRuleCreator:
    """对话式规则创建器"""
    
    def __init__(self, user_id: Optional[str] = None):
        """初始化对话式规则创建器

        参数:
            user_id: 用户 ID
        """
        self.user_id = user_id
        self.graph = build_rule_creation_graph()
        self.compiled = self.graph.compile()
        
        # 初始化状态
        self.state: RuleCreationState = {
            'messages': [],
            'user_id': user_id,
            'current_step': 'collecting_info',
            'missing_info': [],
            'data_sources': []
        }
    
    def process_message(self, user_message: str) -> Dict[str, Any]:
        """处理用户消息

        参数:
            user_message: 用户消息

        返回:
            响应
        """
        # 添加用户消息到状态
        self.state['messages'].append({
            'role': 'user',
            'content': user_message
        })
        
        # 执行图
        try:
            result = self.compiled.invoke(self.state)
            
            # 添加 AI 响应到状态
            if result.get('system_message'):
                self.state['messages'].append({
                    'role': 'assistant',
                    'content': result['system_message']
                })
            
            return {
                'success': True,
                'message': result.get('system_message', ''),
                'step': result.get('current_step', 'unknown'),
                'rule_name': result.get('rule_name'),
                'data': result
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f"处理失败：{str(e)}"
            }
    
    def get_current_state(self) -> RuleCreationState:
        """获取当前状态"""
        return self.state
    
    def reset(self):
        """重置状态"""
        self.state = {
            'messages': [],
            'user_id': self.user_id,
            'current_step': 'collecting_info',
            'missing_info': [],
            'data_sources': []
        }


# ──────────────────────────────────────────────────────────────────────────────
# 全局工厂函数
# ──────────────────────────────────────────────────────────────────────────────

_rule_creators: Dict[str, ConversationalRuleCreator] = {}

def get_rule_creator(user_id: Optional[str] = None) -> ConversationalRuleCreator:
    """获取规则创建器实例

    参数:
        user_id: 用户 ID

    返回:
        规则创建器实例
    """
    key = user_id or 'default'
    if key not in _rule_creators:
        _rule_creators[key] = ConversationalRuleCreator(user_id)
    return _rule_creators[key]
