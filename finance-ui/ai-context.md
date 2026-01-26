# 项目上下文（AI必读）

## 项目简介
财务AI助手 - 数据整理和对账工具

## 核心功能
1. 用户通过AI对话创建配置
2. 打开可视化画布操作Excel
3. 操作步骤自动生成JSON配置
4. 配置可保存、复用

## 技术栈
- React 18 + TypeScript
- Zustand（状态管理）
- dnd-kit（拖拽）
- SheetJS（Excel处理）

## 代码约定
见 .cursorrules 文件

## 关键文件
- src/components/Canvas/Canvas.tsx - 主画布组件
- src/stores/canvasStore.ts - 画布状态
- src/types/index.ts - 全局类型定义

## 当前进度
- [x] 项目初始化
- [x] AI对话集成
- [ ] 画布拖拽功能
- [ ] Excel预览
- [ ] JSON配置生成

## 下一步
实现Canvas组件的拖拽映射功能