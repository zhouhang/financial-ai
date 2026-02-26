## 1. 基础设施搭建

- [x] 1.1 创建 `useTablePreferences` hook，实现 localStorage 读写封装
- [x] 1.2 定义 TypeScript 类型：`TableColumn`, `ViewMode`, `TablePreferences`
- [x] 1.3 配置 React 组件目录结构

## 2. 响应式表格组件

- [x] 2.1 创建 `ResponsiveTable` 基础组件骨架
- [x] 2.2 实现 CSS sticky 固定第一列（文件名列）
- [x] 2.3 实现横向滚动同步（表头与表体 scrollLeft 同步）
- [x] 2.4 添加 `overflow-x: auto` 容器样式

## 3. 列可见性控制

- [x] 3.1 创建列选择下拉菜单组件
- [x] 3.2 实现列显示/隐藏切换逻辑
- [x] 3.3 集成 localStorage 持久化
- [x] 3.4 设置默认显示列

## 4. 视图模式切换

- [x] 4.1 添加视图模式切换器 UI（紧凑/标准/展开）
- [x] 4.2 实现三种模式的 CSS 样式（padding、行高差异）
- [x] 4.3 集成 localStorage 持久化
- [x] 4.4 紧凑模式下仅显示核心列

## 5. 列宽调整

- [x] 5.1 添加列边框拖拽手柄
- [x] 5.2 实现拖拽 resize 逻辑
- [x] 5.3 实现 min-width 限制
- [x] 5.4 集成 localStorage 持久化列宽

## 6. 文件名截断

- [x] 6.1 在文件名单元格添加 CSS `text-overflow: ellipsis`
- [x] 6.2 添加 `title` 属性显示完整文件名
- [x] 6.3 配置默认截断长度为 30 字符
- [x] 6.4 添加可配置的截断长度设置项

## 7. 集成与迁移

- [x] 7.1 改造文件分析页面使用 ResponsiveTable 组件
- [x] 7.2 迁移现有数据到新组件格式
- [x] 7.3 移除旧表格代码
- [x] 7.4 测试所有功能场景

## 8. 验收测试

- [ ] 8.1 横向滚动时第一列固定
- [ ] 8.2 列可见性切换正常，刷新后保持
- [ ] 8.3 三种视图模式切换正常
- [ ] 8.4 列宽拖拽调整正常
- [ ] 8.5 长文件名截断显示，悬停显示完整名称
