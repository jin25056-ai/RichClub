import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import apiClient from '../api/client';

export interface ModelInfo {
  id: string;
  name: string;
  description: string;
  available: boolean;
}

interface ModelContextValue {
  models: ModelInfo[];
  selectedModel: string;
  setSelectedModel: (id: string) => void;
  loading: boolean;
}

const ModelContext = createContext<ModelContextValue>({
  models: [],
  selectedModel: 'ju-model-v2',
  setSelectedModel: () => {},
  loading: false,
});

export const ModelProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModelState] = useState<string>(
    localStorage.getItem('selected_model') ?? 'ju-model-v2'
  );
  const [loading, setLoading] = useState(false);

  const fetchModels = useCallback(async () => {
    if (!localStorage.getItem('access_token')) return;
    setLoading(true);
    try {
      const res = await apiClient.get<ModelInfo[]>('/api/v1/models');
      setModels(res.data);
      // 선택된 모델이 사용 불가면 사용 가능한 첫 번째로 변경
      const current = res.data.find((m) => m.id === selectedModel);
      if (!current || !current.available) {
        const available = res.data.find((m) => m.available);
        if (available) setSelectedModelState(available.id);
      }
    } catch {
      // 실패 시 기본값 유지
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  const setSelectedModel = (id: string) => {
    setSelectedModelState(id);
    localStorage.setItem('selected_model', id);
  };

  return (
    <ModelContext.Provider value={{ models, selectedModel, setSelectedModel, loading }}>
      {children}
    </ModelContext.Provider>
  );
};

export const useModel = () => useContext(ModelContext);
