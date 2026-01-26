/**
 * Excel Preview Area Component - Center area for displaying Excel files
 */
import React, { useState } from 'react';
import { Upload, Tabs, Table, Button, message } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import { useCanvasStore } from '@/stores/canvasStore';
import type { UploadProps } from 'antd';

const { Dragger } = Upload;

const ExcelPreviewArea: React.FC = () => {
  const { uploadedFiles, uploadFiles } = useCanvasStore();
  const [activeFileId, setActiveFileId] = useState<string | null>(null);
  const [activeSheetName, setActiveSheetName] = useState<string>('');

  const handleUpload: UploadProps['customRequest'] = async ({ file, onSuccess, onError }) => {
    try {
      // Convert to File array
      const files = [file as File];
      await uploadFiles(files);
      message.success(`${(file as File).name} 上传成功`);
      onSuccess?.('ok');
    } catch (error) {
      console.error('Upload error:', error);
      message.error('上传失败');
      onError?.(error as Error);
    }
  };

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: true,
    accept: '.xlsx,.xls',
    customRequest: handleUpload,
    showUploadList: false,
    beforeUpload: (file) => {
      const isExcel =
        file.type === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
        file.type === 'application/vnd.ms-excel' ||
        file.name.endsWith('.xlsx') ||
        file.name.endsWith('.xls');

      if (!isExcel) {
        message.error('只能上传 Excel 文件！');
        return false;
      }

      const isLt100M = file.size / 1024 / 1024 < 100;
      if (!isLt100M) {
        message.error('文件大小不能超过 100MB！');
        return false;
      }

      return true;
    },
  };

  // Set active file when files are uploaded
  React.useEffect(() => {
    if (uploadedFiles.length > 0 && !activeFileId) {
      const firstFile = uploadedFiles[0];
      setActiveFileId(firstFile.id);
      if (firstFile.sheets.length > 0) {
        setActiveSheetName(firstFile.sheets[0].name);
      }
    }
  }, [uploadedFiles, activeFileId]);

  const renderFileContent = (fileId: string) => {
    const file = uploadedFiles.find((f) => f.id === fileId);
    if (!file) return null;

    // Create tabs for sheets
    const sheetTabs = file.sheets.map((sheet) => ({
      key: sheet.name,
      label: sheet.name,
      children: (
        <div className="sheet-preview">
          <Table
            dataSource={sheet.rows.map((row, index) => ({
              key: index,
              ...row.reduce((acc, cell, cellIndex) => {
                acc[sheet.headers[cellIndex] || `col_${cellIndex}`] = cell;
                return acc;
              }, {} as any),
            }))}
            columns={sheet.headers.map((header, index) => ({
              title: header,
              dataIndex: header || `col_${index}`,
              key: header || `col_${index}`,
              width: 150,
              ellipsis: true,
            }))}
            pagination={{
              pageSize: 20,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 行`,
            }}
            scroll={{ x: 'max-content', y: 400 }}
            size="small"
            bordered
            style={{
              background: '#1a1a1a',
            }}
          />
          <div style={{ marginTop: '12px', color: '#888', fontSize: '12px' }}>
            共 {sheet.total_rows} 行 × {sheet.total_columns} 列
          </div>
        </div>
      ),
    }));

    return (
      <Tabs
        activeKey={activeSheetName}
        onChange={setActiveSheetName}
        items={sheetTabs}
        style={{ height: '100%' }}
      />
    );
  };

  if (uploadedFiles.length === 0) {
    return (
      <div className="excel-preview-empty">
        <Dragger {...uploadProps} style={{ background: '#1a1a1a', border: '1px dashed #3a3a3a' }}>
          <p className="ant-upload-drag-icon">
            <InboxOutlined style={{ color: '#4a9eff' }} />
          </p>
          <p className="ant-upload-text" style={{ color: '#e0e0e0' }}>
            点击或拖拽文件到此区域上传
          </p>
          <p className="ant-upload-hint" style={{ color: '#888' }}>
            支持上传 Excel 文件（.xlsx, .xls），单个文件不超过 100MB
          </p>
        </Dragger>
      </div>
    );
  }

  // Create tabs for files
  const fileTabs = uploadedFiles.map((file) => ({
    key: file.id,
    label: file.filename,
    children: renderFileContent(file.id),
  }));

  return (
    <div className="excel-preview-container">
      <div className="excel-preview-header">
        <h3 style={{ color: '#fff', margin: 0, fontSize: '16px' }}>Excel 文件预览</h3>
        <Upload {...uploadProps} showUploadList={false}>
          <Button
            size="small"
            style={{
              background: '#2a2a2a',
              border: '1px solid #3a3a3a',
              color: '#e0e0e0',
            }}
          >
            继续上传
          </Button>
        </Upload>
      </div>

      <div className="excel-preview-content">
        <Tabs
          activeKey={activeFileId || undefined}
          onChange={setActiveFileId}
          items={fileTabs}
          type="card"
          style={{ height: '100%' }}
        />
      </div>
    </div>
  );
};

export default ExcelPreviewArea;
