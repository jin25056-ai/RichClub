import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import AuthPage from '../pages/AuthPage';
import ExamplePage from '../pages/ExamplePage';
import MLOpsDashboard from '../pages/MLOpsDashboard';

const AppRouter: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ExamplePage />} />
        <Route path="/auth" element={<AuthPage />} />
        <Route path="/mlops" element={<MLOpsDashboard />} />
      </Routes>
    </BrowserRouter>
  );
};

export default AppRouter;
