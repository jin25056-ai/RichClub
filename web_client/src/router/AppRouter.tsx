import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import AuthPage from '../pages/AuthPage';
import ExamplePage from '../pages/ExamplePage';
import MLOpsDashboard from '../pages/MLOpsDashboard';
import TradePage from '../pages/TradePage';
import PricingPage from '../pages/PricingPage';
import PerformancePage from '../pages/PerformancePage';
import { ModelProvider } from '../contexts/ModelContext';

const AppRouter: React.FC = () => {
  return (
    <BrowserRouter>
      <ModelProvider>
        <Routes>
          <Route path="/" element={<ExamplePage />} />
          <Route path="/auth" element={<AuthPage />} />
          <Route path="/mlops" element={<MLOpsDashboard />} />
          <Route path="/trade" element={<TradePage />} />
          <Route path="/pricing" element={<PricingPage />} />
          <Route path="/performance" element={<PerformancePage />} />
        </Routes>
      </ModelProvider>
    </BrowserRouter>
  );
};

export default AppRouter;
