/**
 * Create Schema Modal - Main modal component with two-step wizard
 */
import React, { useState } from 'react';
import { Modal } from 'antd';
import SchemaMetadataForm from './SchemaMetadataForm';
import SchemaCanvas from './SchemaCanvas';
import { SchemaMetadata, Schema } from '@/types/canvas';

interface CreateSchemaModalProps {
  visible: boolean;
  messageId: string | null;
  onClose: () => void;
  onSuccess: (schema: Schema) => void;
}

const CreateSchemaModal: React.FC<CreateSchemaModalProps> = ({
  visible,
  messageId: _messageId,
  onClose,
  onSuccess,
}) => {
  const [currentStep, setCurrentStep] = useState<1 | 2>(1);
  const [schemaMetadata, setSchemaMetadata] = useState<SchemaMetadata | null>(null);

  const handleMetadataNext = (metadata: SchemaMetadata) => {
    setSchemaMetadata(metadata);
    setCurrentStep(2);
  };

  const handleCanvasBack = () => {
    setCurrentStep(1);
  };

  const handleCanvasSave = (schema: Schema) => {
    onSuccess(schema);
    handleClose();
  };

  const handleClose = () => {
    // Reset state
    setCurrentStep(1);
    setSchemaMetadata(null);
    onClose();
  };

  return (
    <Modal
      open={visible}
      onCancel={handleClose}
      width="100vw"
      style={{ top: 0, maxWidth: '100vw', padding: 0 }}
      bodyStyle={{
        height: 'calc(100vh - 110px)',
        padding: 0,
        background: '#0f0f0f',
      }}
      footer={null}
      destroyOnClose
      title={
        <span style={{ color: '#fff' }}>
          {currentStep === 1 ? '创建规则 - 基本信息' : '创建规则 - 配置画布'}
        </span>
      }
      styles={{
        header: {
          background: '#1a1a1a',
          borderBottom: '1px solid #2a2a2a',
        },
        body: {
          background: '#0f0f0f',
        },
      }}
    >
      {currentStep === 1 ? (
        <SchemaMetadataForm
          onNext={handleMetadataNext}
        />
      ) : (
        <SchemaCanvas
          metadata={schemaMetadata!}
          onBack={handleCanvasBack}
          onSave={handleCanvasSave}
          onCancel={handleClose}
        />
      )}
    </Modal>
  );
};

export default CreateSchemaModal;
