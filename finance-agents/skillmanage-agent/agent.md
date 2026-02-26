# agent描述
- name: skill管理 agent
- desc: 本agent可以查看、编辑已有的skill，并且可以创建新的业务处理skill

## 功能描述
在当前项目中基于langgraph增加skill的管理agent功能

## 功能处理详细描述
### 后台功能描述

### 前端功能描述
1. 前端的代码逻辑在finance-web中进行增加和完善
2. 前端界面可以通过项目url:http://ip:port/skillmanager路径打开skill manager的功能界面
2. 功能界面左侧为当前系统已有的skill列表(显示skill的名称信息)
3. 功能界面右侧为skill的内容的显示区域，包括的内容有:skill名称、skill描述、skill规则内容、原始验证数据文件(文件需支持上传)、结果文件、备注等
4. 功能按钮有测试验证，保存等，用户点击测试验证，将调用后台的接口进行验证；点击保存按钮