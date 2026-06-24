import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import MainPage from '../pages/MainPage';
import AuthPage from '../pages/AuthPage';
import ChartPage from '../pages/ChartPage';
import ExamplePage from '../pages/ExamplePage';
import MLOpsDashboard from '../pages/MLOpsDashboard';

const AppRouter: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainPage />} />
        <Route path="/auth" element={<AuthPage />} />
        <Route path="/chart" element={<ChartPage />} />
        <Route path="/example" element={<ExamplePage />} />
        <Route path="/mlops" element={<MLOpsDashboard />} />
      </Routes>
    </BrowserRouter>
  );
};

export default AppRouter;
