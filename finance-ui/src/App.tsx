/**
 * Main App component - Direct AI Chat Interface
 */
import React from 'react';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import Home from '@/components/Home/Home';

const App: React.FC = () => {
  return (
    <ConfigProvider locale={zhCN}>
      <Home />
    </ConfigProvider>
  );
};

export default App;
