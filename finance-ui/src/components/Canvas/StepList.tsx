/**
 * Step List Component - Left sidebar for managing operation steps
 */
import React from 'react';
import { Button, List, Popconfirm, message } from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  UndoOutlined,
  RedoOutlined,
  DragOutlined,
} from '@ant-design/icons';
import { useCanvasStore } from '@/stores/canvasStore';
import { SchemaStep } from '@/types/canvas';

const StepList: React.FC = () => {
  const {
    steps,
    currentStepIndex,
    setCurrentStepIndex,
    addStep,
    deleteStep,
    undo,
    redo,
    history,
    historyIndex,
  } = useCanvasStore();

  const handleAddStep = () => {
    const newStep: SchemaStep = {
      id: `step-${Date.now()}`,
      type: 'extract',
      name: `步骤 ${steps.length + 1}`,
      config: {},
      order: steps.length,
    };
    addStep(newStep);
    message.success('步骤已添加');
  };

  const handleDeleteStep = (index: number) => {
    deleteStep(index);
    message.success('步骤已删除');
  };

  const handleStepClick = (index: number) => {
    setCurrentStepIndex(index);
  };

  const canUndo = historyIndex > 0;
  const canRedo = historyIndex < history.length - 1;

  return (
    <div className="step-list-container">
      {/* Header with undo/redo */}
      <div className="step-list-header">
        <h3 style={{ color: '#fff', margin: 0, fontSize: '16px' }}>操作步骤</h3>
        <div className="step-list-actions">
          <Button
            icon={<UndoOutlined />}
            size="small"
            onClick={undo}
            disabled={!canUndo}
            style={{
              background: 'transparent',
              border: 'none',
              color: canUndo ? '#e0e0e0' : '#555',
            }}
            title="撤销 (Ctrl+Z)"
          />
          <Button
            icon={<RedoOutlined />}
            size="small"
            onClick={redo}
            disabled={!canRedo}
            style={{
              background: 'transparent',
              border: 'none',
              color: canRedo ? '#e0e0e0' : '#555',
            }}
            title="重做 (Ctrl+Y)"
          />
        </div>
      </div>

      {/* Step List */}
      <div className="step-list-content">
        {steps.length === 0 ? (
          <div className="step-list-empty">
            <p style={{ color: '#888', textAlign: 'center', marginTop: '40px' }}>
              暂无步骤，点击下方按钮添加
            </p>
          </div>
        ) : (
          <List
            dataSource={steps}
            renderItem={(step, index) => (
              <div
                key={step.id}
                className={`step-item ${index === currentStepIndex ? 'active' : ''}`}
                onClick={() => handleStepClick(index)}
              >
                <div className="step-item-header">
                  <DragOutlined style={{ color: '#888', marginRight: '8px' }} />
                  <span className="step-item-name">{step.name}</span>
                  <Popconfirm
                    title="确定删除此步骤？"
                    onConfirm={(e) => {
                      e?.stopPropagation();
                      handleDeleteStep(index);
                    }}
                    okText="确定"
                    cancelText="取消"
                  >
                    <Button
                      icon={<DeleteOutlined />}
                      size="small"
                      danger
                      type="text"
                      onClick={(e) => e.stopPropagation()}
                      style={{ marginLeft: 'auto' }}
                    />
                  </Popconfirm>
                </div>
                <div className="step-item-type">
                  <span style={{ color: '#888', fontSize: '12px' }}>
                    {getStepTypeLabel(step.type)}
                  </span>
                </div>
              </div>
            )}
          />
        )}
      </div>

      {/* Add Step Button */}
      <div className="step-list-footer">
        <Button
          icon={<PlusOutlined />}
          onClick={handleAddStep}
          block
          style={{
            background: '#2a2a2a',
            border: '1px solid #3a3a3a',
            color: '#e0e0e0',
          }}
        >
          添加步骤
        </Button>
      </div>
    </div>
  );
};

// Helper function to get step type label
function getStepTypeLabel(type: string): string {
  const labels: { [key: string]: string } = {
    extract: '数据提取',
    transform: '数据转换',
    validate: '数据验证',
    conditional: '条件逻辑',
    merge: '数据合并',
    output: '输出配置',
  };
  return labels[type] || type;
}

export default StepList;
