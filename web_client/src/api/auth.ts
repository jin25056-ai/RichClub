import apiClient from './client';
import { AuthFormValues, AuthResponse } from '../types';

export const login = (data: Pick<AuthFormValues, 'email' | 'password'>): Promise<AuthResponse> =>
  apiClient.post<AuthResponse>('/auth/login', data).then((res) => res.data);

export const signup = (data: AuthFormValues): Promise<AuthResponse> =>
  apiClient.post<AuthResponse>('/auth/signup', data).then((res) => res.data);

export const logout = (): Promise<void> =>
  apiClient.post('/auth/logout').then(() => {
    localStorage.removeItem('access_token');
  });
