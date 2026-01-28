/**
 * Step Config Panel Component - Right sidebar for configuring steps
 */
import React from 'react';
import { Form, Input, Select, Button, message } from 'antd';
import { useCanvasStore } from '@/stores/canvasStore';
import { SchemaStep, StepType } from '@/types/canvas';

const { Option } = Select;

const StepConfigPanel: React.FC = () => {
  const { steps, currentStepIndex, updateStep, uploadedFiles } = useCanvasStore();
  const [form] = Form.useForm();

  const currentStep = currentStepIndex >= 0 ? steps[currentStepIndex] : null;

  // Update form when current step changes
  React.useEffect(() => {
    if (currentStep) {
      form.setFieldsValue({
        name: currentStep.name,
        type: currentStep.type,
        ...currentStep.config,
      });
    } else {
      form.resetFields();
    }
  }, [currentStep, form]);

  const handleSave = () => {
    if (!currentStep) return;

    form.validateFields().then((values) => {
      const { name, type, ...config } = values;

      const updatedStep: SchemaStep = {
        ...currentStep,
        name,
        type,
        config,
      };

      updateStep(currentStepIndex, updatedStep);
      message.success('步骤已更新');
    });
  };

  const handleStepTypeChange = (type: StepType) => {
    // Reset config fields when type changes
    const currentValues = form.getFieldsValue();
    form.setFieldsValue({
      name: currentValues.name,
      type,
    });
  };

  if (!currentStep) {
    return (
      <div className="step-config-empty">
        <p style={{ color: '#888', textAlign: 'center', marginTop: '40px' }}>
          请选择或添加一个步骤
        </p>
      </div>
    );
  }

  // Get available files and columns for dropdowns
  const fileOptions = uploadedFiles.map((file) => ({
    label: file.filename,
    value: file.id,
    sheets: file.sheets,
  }));

  const getColumnsForFile = (fileId: string, sheetName?: string) => {
    const file = uploadedFiles.find((f) => f.id === fileId);
    if (!file) return [];

    if (sheetName) {
      const sheet = file.sheets.find((s) => s.name === sheetName);
      return sheet?.headers || [];
    }

    // Return all columns from all sheets
    return file.sheets.flatMap((sheet) => sheet.headers);
  };

  return (
    <div className="step-config-container">
      <div className="step-config-header">
        <h3 style={{ color: '#fff', margin: 0, fontSize: '16px' }}>步骤配置</h3>
      </div>

      <div className="step-config-content">
        <Form form={form} layout="vertical">
          <Form.Item
            label={<span style={{ color: '#e0e0e0' }}>步骤名称</span>}
            name="name"
            rules={[{ required: true, message: '请输入步骤名称' }]}
          >
            <Input
              placeholder="例如：提取销售数据"
              style={{
                background: '#0f0f0f',
                border: '1px solid #2a2a2a',
                color: '#e0e0e0',
              }}
            />
          </Form.Item>

          <Form.Item
            label={<span style={{ color: '#e0e0e0' }}>步骤类型</span>}
            name="type"
            rules={[{ required: true, message: '请选择步骤类型' }]}
          >
            <Select
              onChange={handleStepTypeChange}
              style={{
                width: '100%',
              }}
            >
              <Option value="extract">数据提取</Option>
              <Option value="transform">数据转换</Option>
              <Option value="validate">数据验证</Option>
              <Option value="conditional">条件逻辑</Option>
              <Option value="merge">数据合并</Option>
              <Option value="output">输出配置</Option>
            </Select>
          </Form.Item>

          {/* Dynamic config fields based on step type */}
          {renderConfigFields(currentStep.type, fileOptions, getColumnsForFile)}

          <Form.Item style={{ marginTop: '24px' }}>
            <Button
              type="primary"
              onClick={handleSave}
              block
              style={{
                background: '#4a9eff',
                border: 'none',
              }}
            >
              保存配置
            </Button>
          </Form.Item>
        </Form>
      </div>
    </div>
  );
};

// Render config fields based on step type
function renderConfigFields(
  stepType: StepType,
  fileOptions: any[],
  _getColumnsForFile: (fileId: string, sheetName?: string) => string[]
) {
  switch (stepType) {
    case 'extract':
      return (
        <>
          <Form.Item
            label={<span style={{ color: '#e0e0e0' }}>源文件</span>}
            name="source_file"
            rules={[{ required: true, message: '请选择源文件' }]}
          >
            <Select placeholder="选择文件">
              {fileOptions.map((file) => (
                <Option key={file.value} value={file.value}>
                  {file.label}
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            label={<span style={{ color: '#e0e0e0' }}>目标名称</span>}
            name="target_name"
            rules={[{ required: true, message: '请输入目标名称' }]}
          >
            <Input
              placeholder="提取后的数据名称"
              style={{
                background: '#0f0f0f',
                border: '1px solid #2a2a2a',
                color: '#e0e0e0',
              }}
            />
          </Form.Item>
        </>
      );

    case 'transform':
      return (
        <>
          <Form.Item
            label={<span style={{ color: '#e0e0e0' }}>数据源</span>}
            name="source"
            rules={[{ required: true, message: '请输入数据源' }]}
          >
            <Input
              placeholder="数据源名称"
              style={{
                background: '#0f0f0f',
                border: '1px solid #2a2a2a',
                color: '#e0e0e0',
              }}
            />
          </Form.Item>

          <Form.Item
            label={<span style={{ color: '#e0e0e0' }}>操作类型</span>}
            name="operation"
            rules={[{ required: true, message: '请选择操作类型' }]}
          >
            <Select placeholder="选择操作">
              <Option value="map">映射</Option>
              <Option value="filter">筛选</Option>
              <Option value="calculate">计算</Option>
            </Select>
          </Form.Item>

          <Form.Item
            label={<span style={{ color: '#e0e0e0' }}>表达式</span>}
            name="expression"
            rules={[{ required: true, message: '请输入表达式' }]}
          >
            <Input.TextArea
              rows={3}
              placeholder="例如：amount * 1.13"
              style={{
                background: '#0f0f0f',
                border: '1px solid #2a2a2a',
                color: '#e0e0e0',
              }}
            />
          </Form.Item>
        </>
      );

    case 'conditional':
      return (
        <>
          <div style={{ color: '#e0e0e0', marginBottom: '12px', fontSize: '14px' }}>
            条件配置
          </div>

          <Form.Item
            label={<span style={{ color: '#e0e0e0' }}>如果 [列]</span>}
            name={['condition', 'source_column']}
            rules={[{ required: true, message: '请选择列' }]}
          >
            <Input
              placeholder="列名"
              style={{
                background: '#0f0f0f',
                border: '1px solid #2a2a2a',
                color: '#e0e0e0',
              }}
            />
          </Form.Item>

          <Form.Item
            label={<span style={{ color: '#e0e0e0' }}>运算符</span>}
            name={['condition', 'operator']}
            rules={[{ required: true, message: '请选择运算符' }]}
          >
            <Select placeholder="选择运算符">
              <Option value="equals">等于</Option>
              <Option value="not_equals">不等于</Option>
              <Option value="contains">包含</Option>
              <Option value="greater_than">大于</Option>
              <Option value="less_than">小于</Option>
            </Select>
          </Form.Item>

          <Form.Item
            label={<span style={{ color: '#e0e0e0' }}>值</span>}
            name={['condition', 'value']}
            rules={[{ required: true, message: '请输入值' }]}
          >
            <Input
              placeholder="比较值"
              style={{
                background: '#0f0f0f',
                border: '1px solid #2a2a2a',
                color: '#e0e0e0',
              }}
            />
          </Form.Item>

          <div style={{ color: '#e0e0e0', marginTop: '20px', marginBottom: '12px', fontSize: '14px' }}>
            则执行
          </div>

          <Form.Item
            label={<span style={{ color: '#e0e0e0' }}>目标列</span>}
            name={['then_action', 'target_column']}
            rules={[{ required: true, message: '请输入目标列' }]}
          >
            <Input
              placeholder="目标列名"
              style={{
                background: '#0f0f0f',
                border: '1px solid #2a2a2a',
                color: '#e0e0e0',
              }}
            />
          </Form.Item>
        </>
      );

    case 'merge':
      return (
        <>
          <Form.Item
            label={<span style={{ color: '#e0e0e0' }}>合并类型</span>}
            name="merge_type"
            rules={[{ required: true, message: '请选择合并类型' }]}
          >
            <Select placeholder="选择合并类型">
              <Option value="inner">内连接</Option>
              <Option value="left">左连接</Option>
              <Option value="right">右连接</Option>
              <Option value="outer">外连接</Option>
            </Select>
          </Form.Item>

          <Form.Item
            label={<span style={{ color: '#e0e0e0' }}>目标名称</span>}
            name="target_name"
            rules={[{ required: true, message: '请输入目标名称' }]}
          >
            <Input
              placeholder="合并后的数据名称"
              style={{
                background: '#0f0f0f',
                border: '1px solid #2a2a2a',
                color: '#e0e0e0',
              }}
            />
          </Form.Item>
        </>
      );

    case 'output':
      return (
        <>
          <Form.Item
            label={<span style={{ color: '#e0e0e0' }}>数据源</span>}
            name="source"
            rules={[{ required: true, message: '请输入数据源' }]}
          >
            <Input
              placeholder="数据源名称"
              style={{
                background: '#0f0f0f',
                border: '1px solid #2a2a2a',
                color: '#e0e0e0',
              }}
            />
          </Form.Item>

          <Form.Item
            label={<span style={{ color: '#e0e0e0' }}>输出格式</span>}
            name="output_format"
            rules={[{ required: true, message: '请选择输出格式' }]}
          >
            <Select placeholder="选择格式">
              <Option value="excel">Excel</Option>
              <Option value="csv">CSV</Option>
              <Option value="json">JSON</Option>
            </Select>
          </Form.Item>
        </>
      );

    default:
      return null;
  }
}

export default StepConfigPanel;
