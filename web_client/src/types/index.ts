export interface User {
  id: string;
  email: string;
  name: string;
}

export interface AuthFormValues {
  email: string;
  password: string;
  name?: string;
}

export interface AuthResponse {
  access_token: string;
  user: User;
}
