export interface User {
  id: string;
  email: string;
  name: string;
  created_at: string;
  plan: string;
}

export interface AuthFormValues {
  email: string;
  password: string;
  name?: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}
