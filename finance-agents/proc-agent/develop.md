# 数据整理数字员工 - 开发需求文档

## 一、项目概述

### 1.1 项目名称
- **中文名**: 数据整理数字员工
- **英文名**: Data-Process Agent (proc-agent)

### 1.2 项目定位
一个通用的数据整理平台，能够根据配置的业务 Skill 和规则描述，对各类数据进行智能化整理、汇聚和分析。

### 1.3 核心架构
```
数据整理数字员工 (Agent)
├── 核心框架层
│   ├── Skill Manager (技能管理器)
│   ├── Script Generator (脚本生成器)
│   └── Execution Engine (执行引擎)
├── Skill 层
│   ├── Audit Skill (审计数据整理) ← 首个业务 Skill
│   └── [其他业务 Skill] ← 待扩展
└── 数据层
    ├── data/ (原始数据)
    ├── references/ (规则文件)
    ├── scripts/ (处理脚本)
    └── result/ (处理结果)
```

---

## 二、功能需求

### 2.1 核心功能

#### 2.1.1 Agent 激活
1. 在前端选择"数据整理 agent"，该 proc-agent 将被激活
2. 激活后，前端所有的请求操作均由该 agent 进行处理
3. Agent 负责路由到对应的 Skill 进行处理

#### 2.1.2 业务功能类型
该 agent 支持两种类型的业务功能：
1. **数据整理**: 根据用户上传的文件和意图，调用对应 Skill 进行数据处理
2. **规则配置管理**: 创建、编辑、验证业务规则

### 2.2 详细功能描述

#### 2.2.1 数据整理业务
1. 分析用户录入的意图和上传的文档
2. 根据意图识别调用对应的 Skill 进行整理业务处理
3. 支持多种业务类型（当前仅审计，后续可扩展）

#### 2.2.2 规则配置管理
1. **创建新规则**: 用户通过录入指令和意图与 agent 交互，创建新的整理规则
2. **编辑已有规则**: 修改已有的业务规则
3. **查看规则列表**: 查看当前已有的整理规则列表
4. **规则验证**: 对新的和已有的业务规则进行验证

#### 2.2.3 脚本生成与执行
1. 根据用户的意图生成符合大模型理解的业务规则文件
2. 根据业务规则文件生成对应的处理 Python 脚本
3. 调用 Python 脚本进行数据整理业务
4. 用户可以查看整理后的结果文件

#### 2.2.4 结果验证
1. 用户可以上传正确的结果文件作为参考
2. 比较整理结果文件与上传的结果文件
3. 如果有差异，提示用户验证结果有差异
4. 用户可以继续完善和修改对应的规则

### 2.3 用户隔离
1. 不同用户创建的规则文件需要隔离
2. 公共规则文件存放在 `references/` 根目录
3. 用户私有规则文件存放在 `users/{user_id}/references/` 目录
4. 不同用户创建的规则文件不能相互调用

---

## 三、技术架构要求

### 3.1 技术栈
- **Agent 框架**: 基于 LangGraph 进行开发
- **前端**: 基于 finance-web 进行功能增加、完善
- **后端**: Python 3.10+
- **数据处理**: pandas, openpyxl 等

### 3.2 目录结构
```
proc-agent/
├── __init__.py                  # 模块初始化
├── agent.md                     # Agent 描述
├── develop.md                   # 开发需求文档
├── skills/                      # Skill 目录
│   ├── audit/                   # 审计数据整理 Skill
│   │   ├── SKILL.md             # Skill 定义
│   │   ├── references/          # 规则文件
│   │   └── scripts/             # 处理脚本
│   └── [other]/                 # 其他 Skill (待扩展)
├── references/                  # 公共规则文件
├── scripts/                     # 公共脚本
├── data/                        # 原始数据
└── result/                      # 处理结果
```

### 3.3 Skill 架构
每个 Skill 包含：
1. **SKILL.md**: Skill 的定义文件，包含功能描述、输入输出、处理规则等
2. **references/**: 该 Skill 专用的规则文件
3. **scripts/**: 该 Skill 专用的处理脚本

### 3.4 LangGraph 集成
1. Agent 主图负责意图识别和 Skill 路由
2. 每个 Skill 可以是独立的子图
3. Skill 之间相互隔离，通过 Agent 统一调度

---

## 四、当前开发范围

### 4.1 已完成的 Skill
- **Audit Skill (审计数据整理)**: 
  - Skill ID: `AUDIT-DATA-ORGANIZER-001`
  - 路径：`skills/audit/`
  - 状态：✅ 已完成

### 4.2 支持的业务类型（审计 Skill）
| 业务类型 | 意图编码 | 规则文件 | 脚本文件 | 状态 |
|---------|---------|---------|---------|------|
| 货币资金整理 | `cash_funds` | ✅ 已完成 | ✅ 已完成 | 可用 |
| 流水分析 | `transaction_analysis` | ⚠️ 待创建 | ⚠️ 待创建 | 待开发 |
| 应收账款分析 | `accounts_receivable` | ⚠️ 待创建 | ⚠️ 待创建 | 待开发 |
| 库存商品分析 | `inventory_analysis` | ⚠️ 待创建 | ⚠️ 待创建 | 待开发 |
| 开户清单核对 | `bank_account_check` | ⚠️ 待创建 | ⚠️ 待创建 | 待开发 |

---

## 五、开发阶段

### 阶段一：基础架构（已完成）
- ✅ 创建 proc-agent 目录结构
- ✅ 实现核心模块（intent_recognizer, skill_handler, script_executor）
- ✅ 创建审计 Skill 框架
- ✅ 完成货币资金业务规则和脚本

### 阶段二：LangGraph 集成（进行中）
- ⚠️ 构建 Agent 主图
- ⚠️ 实现 Skill 路由逻辑
- ⚠️ 集成到 data-agent

### 阶段三：规则管理功能（待开发）
- ❌ 规则创建界面
- ❌ 规则编辑功能
- ❌ 规则验证机制

### 阶段四：用户隔离（待开发）
- ❌ 用户目录管理
- ❌ 规则权限控制
- ❌ 用户间隔离机制

### 阶段五：扩展其他 Skill（待开发）
- ❌ 其他业务领域的 Skill
- ❌ Skill 注册机制
- ❌ Skill 热加载

---

## 六、接口定义

### 6.1 Agent 接口

```python
class DataProcessAgent:
    """数据整理数字员工接口"""
    
    async def process_request(
        self,
        user_request: str,
        files: List[str],
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """处理用户请求"""
        pass
    
    async def list_skills(self) -> List[Dict[str, str]]:
        """列出所有可用的 Skill"""
        pass
    
    async def get_skill_detail(self, skill_id: str) -> Dict[str, Any]:
        """获取 Skill 详情"""
        pass
```

### 6.2 Skill 接口

```python
class Skill:
    """Skill 基础接口"""
    
    def __init__(self, skill_id: str, name: str, description: str):
        self.skill_id = skill_id
        self.name = name
        self.description = description
    
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理数据"""
        pass
    
    def get_rules(self) -> List[Dict[str, Any]]:
        """获取规则列表"""
        pass
```

---

## 七、配置管理

### 7.1 环境变量
```bash
# Agent 配置
PROC_AGENT_NAME="Data-Process Agent"
PROC_AGENT_VERSION="1.0.0"

# 数据目录
DATA_DIR="/path/to/data"
RESULT_DIR="/path/to/result"

# LLM 配置
LLM_PROVIDER="openai"
LLM_MODEL="gpt-4"
```

### 7.2 配置文件
```yaml
# config.yaml
agent:
  name: "Data-Process Agent"
  version: "1.0.0"
  
skills:
  enabled:
    - "AUDIT-DATA-ORGANIZER-001"
  
data:
  input_dir: "data/"
  output_dir: "result/"
  user_isolation: true
```

---

## 八、测试要求

### 8.1 单元测试
- 意图识别准确率 > 90%
- 脚本执行成功率 > 95%
- 错误处理覆盖率 100%

### 8.2 集成测试
- Agent 与前端集成测试
- Skill 路由测试
- 用户隔离测试

### 8.3 性能测试
- 单个请求响应时间 < 30 秒
- 并发处理能力 > 10 请求/秒
- 大数据处理（>10MB）不出现内存溢出

---

## 九、验收标准

### 9.1 功能验收
- [ ] 能够正确识别用户意图
- [ ] 能够调用对应 Skill 进行处理
- [ ] 能够生成正确的结果文件
- [ ] 支持规则创建、编辑、验证
- [ ] 用户隔离机制正常工作

### 9.2 质量验收
- [ ] 代码符合 Python 规范
- [ ] 单元测试覆盖率 > 80%
- [ ] 文档完整准确

---

## 十、后续规划

### 10.1 短期（1-2 个月）
1. 完善审计 Skill 的其他业务类型
2. 实现规则管理功能
3. 实现用户隔离机制

### 10.2 中期（3-6 个月）
1. 扩展其他业务领域的 Skill（如税务、财务等）
2. 实现 Skill 市场机制
3. 支持 Skill 热加载和动态注册

### 10.3 长期（6-12 个月）
1. 实现 Agent 自主学习能力
2. 支持分布式部署
3. 构建完整的数据整理生态系统

---

**文档版本**: 3.0  
**创建日期**: 2026-02-26  
**最后更新**: 2026-02-27  
**维护者**: 数据整理数字员工团队
