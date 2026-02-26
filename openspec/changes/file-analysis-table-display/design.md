## Context

当前文件分析结果使用简单 HTML table 展示，无响应式处理。当文件名过长或列数较多时，导致：
1. 表格溢出容器，布局崩坏
2. 用户无法在有限屏幕空间内完整浏览数据

需要改造为支持横向滚动、列控制、视图模式的响应式表格组件。

## Goals / Non-Goals

**Goals:**
- 实现响应式表格，支持横向滚动
- 第一列（文件名）固定不随横向滚动移动
- 提供列可见性控制，用户可切换列显示/隐藏
- 支持紧凑/标准/展开三种视图模式
- 支持拖拽调整列宽
- 文件名过长时截断显示，悬停显示完整名称

**Non-Goals:**
- 后端数据处理逻辑变更
- 移动端 touch 交互优化（暂不考虑）
- 表格数据排序/筛选功能

## Decisions

### 1. 使用 CSS sticky 固定第一列

**Decision:** 使用 CSS `position: sticky; left: 0` 固定第一列，而非 JavaScript 手动计算偏移。

**Rationale:** 
- CSS sticky 性能更好，滚动时由浏览器合成层处理
- 实现简单，无需维护滚动同步状态
- 兼容主流浏览器

**Alternative:** JavaScript 监听 scroll 事件手动设置 `transform: translateX()` — 性能较差，已排除。

### 2. 使用 localStorage 持久化用户偏好

**Decision:** 列可见性、视图模式、列宽偏好存储在 localStorage。

**Rationale:**
- 纯前端方案，无需后端 API
- 简单快速，满足用户偏好保持需求
- 用户清除浏览器数据后重置为默认值，可接受

**Alternative:** 后端存储用户偏好 — 需要额外 API 开发，暂不必要。

### 3. 使用 React 组件封装表格逻辑

**Decision:** 创建 `ResponsiveTable` 通用组件，封装滚动、列控制、视图模式逻辑。

**Rationale:**
- 组件可复用于其他模块（文件列表、数据导出等）
- 状态集中管理，避免 props drilling
- 便于单元测试

### 4. 文件名截断使用 CSS text-overflow

**Decision:** 使用 CSS `text-overflow: ellipsis` + `white-space: nowrap` 实现截断，title 属性显示完整名称。

**Rationale:**
- CSS 原生支持，无需 JavaScript 计算
- 性能好，浏览器优化
- title 属性自动触发浏览器 tooltip

**Alternative:** 自定义 Tooltip 组件 — 增加复杂度，浏览器原生 tooltip 已足够。

## Risks / Trade-offs

- **固定列与横向滚动冲突** → 确保表头和表体滚动同步，使用相同 scrollLeft
- **列宽调整与响应式冲突** → 设置 min-width 防止列被压缩过窄
- **localStorage 满** → 捕获异常，降级为内存存储

## Migration Plan

1. 新增 `ResponsiveTable` 组件
2. 新增 `useTablePreferences` hook 管理 localStorage
3. 改造现有文件分析页面使用新组件
4. 移除旧表格代码

## Open Questions

- 是否需要支持列顺序拖拽调整？（当前仅支持可见性控制）
- 移动端是否需要单独优化？（当前仅针对桌面端）
