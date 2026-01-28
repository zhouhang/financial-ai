/**
 * Schema Canvas - Step 2 of schema creation with 3-column layout
 */
import React, { useEffect } from 'react';
import { Button, message } from 'antd';
import { SaveOutlined, PlayCircleOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import StepList from './StepList';
import ExcelPreviewArea from './ExcelPreviewArea';
import StepConfigPanel from './StepConfigPanel';
import { SchemaMetadata, Schema } from '@/types/canvas';
import { useCanvasStore } from '@/stores/canvasStore';
import './Canvas.css';

interface SchemaCanvasProps {
  metadata: SchemaMetadata;
  onBack: () => void;
  onSave: (schema: Schema) => void;
  onCancel: () => void;
}

const SchemaCanvas: React.FC<SchemaCanvasProps> = ({
  metadata,
  onBack,
  onSave,
  onCancel,
}) => {
  const {
    steps,
    uploadedFiles,
    currentStepIndex: _currentStepIndex,
    validateSchema,
    testSchema,
    saveSchema,
    reset,
  } = useCanvasStore();

  const [saving, setSaving] = React.useState(false);
  const [testing, setTesting] = React.useState(false);

  // Reset canvas state when component mounts
  useEffect(() => {
    reset();
  }, [reset]);

  const handleTest = async () => {
    if (uploadedFiles.length === 0) {
      message.warning('请先上传Excel文件');
      return;
    }

    if (steps.length === 0) {
      message.warning('请先添加处理步骤');
      return;
    }

    setTesting(true);
    try {
      const result = await testSchema();
      if (result.success) {
        message.success(`测试成功！执行时间：${result.execution_time.toFixed(2)}秒`);
        // TODO: Show preview in modal
      } else {
        message.error('测试失败');
        result.errors.forEach((error) => {
          message.error(error);
        });
      }
    } catch (error) {
      console.error('Test error:', error);
      message.error('测试失败，请重试');
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    // Validate first
    setSaving(true);
    try {
      const validation = await validateSchema();
      if (!validation.valid) {
        message.error('规则配置验证失败');
        validation.errors.forEach((error) => {
          message.error(error);
        });
        setSaving(false);
        return;
      }

      if (validation.warnings.length > 0) {
        validation.warnings.forEach((warning) => {
          message.warning(warning);
        });
      }

      // Save schema
      const schema = await saveSchema(metadata);
      message.success('规则保存成功！');
      onSave(schema);
    } catch (error) {
      console.error('Save error:', error);
      message.error('保存失败，请重试');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="schema-canvas">
      {/* Header */}
      <div className="canvas-header">
        <div className="canvas-header-left">
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={onBack}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#e0e0e0',
            }}
          >
            返回
          </Button>
          <span className="canvas-title">{metadata.name_cn}</span>
        </div>
        <div className="canvas-header-right">
          <Button
            icon={<PlayCircleOutlined />}
            onClick={handleTest}
            loading={testing}
            disabled={uploadedFiles.length === 0 || steps.length === 0}
            style={{
              background: '#2a5a2a',
              border: 'none',
              color: '#4ade80',
            }}
          >
            测试
          </Button>
          <Button
            icon={<SaveOutlined />}
            type="primary"
            onClick={handleSave}
            loading={saving}
            style={{
              background: '#4a9eff',
              border: 'none',
            }}
          >
            保存
          </Button>
          <Button
            onClick={onCancel}
            style={{
              background: '#2a2a2a',
              border: 'none',
              color: '#e0e0e0',
            }}
          >
            取消
          </Button>
        </div>
      </div>

      {/* Main Content - 3 columns */}
      <div className="canvas-content">
        {/* Left: Step List */}
        <div className="step-list-sidebar">
          <StepList />
        </div>

        {/* Center: Excel Preview */}
        <div className="excel-preview-area">
          <ExcelPreviewArea />
        </div>

        {/* Right: Step Config */}
        <div className="step-config-panel">
          <StepConfigPanel />
        </div>
      </div>
    </div>
  );
};

export default SchemaCanvas;
