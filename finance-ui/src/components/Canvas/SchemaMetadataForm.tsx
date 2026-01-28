/**
 * Schema Metadata Form - Step 1 of schema creation
 * Note: Type key generation and name checking are now handled through Dify API
 */
import React, { useState } from 'react';
import { Form, Input, Radio, Button, message } from 'antd';
import { SchemaMetadata } from '@/types/canvas';
import debounce from 'lodash/debounce';

interface SchemaMetadataFormProps {
  onNext: (metadata: SchemaMetadata) => void;
}

const SchemaMetadataForm: React.FC<SchemaMetadataFormProps> = ({ onNext }) => {
  const [form] = Form.useForm();
  const [typeKey, setTypeKey] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [checkingName, setCheckingName] = useState(false);
  const [nameValid, setNameValid] = useState(false);

  // Debounced function to generate type_key and check uniqueness
  // Note: This should be handled through Dify API in production
  const handleNameChange = debounce(async (nameCn: string) => {
    if (!nameCn || nameCn.trim().length === 0) {
      setTypeKey('');
      setNameValid(false);
      return;
    }

    try {
      setCheckingName(true);

      // TODO: Send to Dify API for type_key generation and name checking
      // For now, generate a simple type_key locally
      const type_key = nameCn
        .toLowerCase()
        .replace(/[^a-z0-9\u4e00-\u9fa5]/g, '_')
        .replace(/_+/g, '_')
        .replace(/^_|_$/g, '');

      setTypeKey(type_key);
      setNameValid(true);

      form.setFields([
        {
          name: 'name_cn',
          errors: [],
        },
      ]);
    } catch (error) {
      console.error('Error checking name:', error);
      message.error('检查名称失败');
      setNameValid(false);
    } finally {
      setCheckingName(false);
    }
  }, 500);

  const handleSubmit = async (values: any) => {
    setLoading(true);
    try {
      // TODO: Send to Dify API for final name checking
      // For now, just proceed with the metadata

      const metadata: SchemaMetadata = {
        name_cn: values.name_cn,
        type_key: typeKey,
        work_type: values.work_type,
        description: values.description,
      };

      onNext(metadata);
    } catch (error) {
      console.error('Error submitting form:', error);
      message.error('提交失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '40px', maxWidth: '600px', margin: '0 auto' }}>
      <h2 style={{ color: '#fff', marginBottom: '30px', fontSize: '20px' }}>
        创建规则 - 基本信息
      </h2>

      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
        initialValues={{
          work_type: 'DATA_PREPARATION',
        }}
      >
        <Form.Item
          label={<span style={{ color: '#e0e0e0' }}>工作类型</span>}
          name="work_type"
          rules={[{ required: true, message: '请选择工作类型' }]}
        >
          <Radio.Group>
            <Radio value="DATA_PREPARATION" style={{ color: '#e0e0e0' }}>
              数据整理
            </Radio>
            <Radio value="RECONCILIATION" style={{ color: '#e0e0e0' }}>
              数据对账
            </Radio>
          </Radio.Group>
        </Form.Item>

        <Form.Item
          label={<span style={{ color: '#e0e0e0' }}>规则名称（中文）</span>}
          name="name_cn"
          rules={[
            { required: true, message: '请输入规则名称' },
            { min: 1, max: 100, message: '名称长度应在1-100个字符之间' },
          ]}
          validateStatus={checkingName ? 'validating' : undefined}
          hasFeedback
        >
          <Input
            placeholder="例如：销售数据整理"
            onChange={(e) => handleNameChange(e.target.value)}
            style={{
              background: '#0f0f0f',
              border: '1px solid #2a2a2a',
              color: '#e0e0e0',
            }}
          />
        </Form.Item>

        <Form.Item
          label={<span style={{ color: '#e0e0e0' }}>描述（可选）</span>}
          name="description"
        >
          <Input.TextArea
            rows={4}
            placeholder="请输入规则描述"
            style={{
              background: '#0f0f0f',
              border: '1px solid #2a2a2a',
              color: '#e0e0e0',
            }}
          />
        </Form.Item>

        <Form.Item style={{ marginTop: '40px', marginBottom: 0 }}>
          <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              disabled={!nameValid || checkingName}
              style={{
                background: '#4a9eff',
                border: 'none',
              }}
            >
              下一步
            </Button>
          </div>
        </Form.Item>
      </Form>
    </div>
  );
};

export default SchemaMetadataForm;
