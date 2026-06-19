import apiClient from './client';
import { AuthFormValues, AuthResponse } from '../types';

const MOCK_CREDENTIALS = {
  email: 'admin',
  password: 'humanai1029',
};

const MOCK_RESPONSE: AuthResponse = {
  access_token: 'mock-token-richclub',
  user: {
    id: '1',
    email: 'admin',
    name: 'Admin',
  },
};

export const login = (data: Pick<AuthFormValues, 'email' | 'password'>): Promise<AuthResponse> => {
  if (data.email === MOCK_CREDENTIALS.email && data.password === MOCK_CREDENTIALS.password) {
    return Promise.resolve(MOCK_RESPONSE);
  }
  return apiClient.post<AuthResponse>('/auth/login', data).then((res) => res.data);
};

export const signup = (data: AuthFormValues): Promise<AuthResponse> =>
  apiClient.post<AuthResponse>('/auth/signup', data).then((res) => res.data);

export const logout = (): Promise<void> =>
  apiClient.post('/auth/logout').then(() => {
    localStorage.removeItem('access_token');
  });
