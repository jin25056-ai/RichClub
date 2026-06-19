import apiClient from './client';
import { AuthFormValues, AuthResponse, User } from '../types';

export const login = (data: Pick<AuthFormValues, 'email' | 'password'>): Promise<AuthResponse> =>
  apiClient.post<AuthResponse>('/api/v1/auth/login', data).then((res) => res.data);

export const signup = (data: AuthFormValues): Promise<AuthResponse> =>
  apiClient.post<AuthResponse>('/api/v1/auth/signup', data).then((res) => res.data);

export const refresh = (refreshToken: string): Promise<AuthResponse> =>
  apiClient
    .post<AuthResponse>('/api/v1/auth/refresh', { refresh_token: refreshToken })
    .then((res) => res.data);

export const getMe = (): Promise<User> =>
  apiClient.get<User>('/api/v1/auth/me').then((res) => res.data);

export const logout = (): void => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
};
