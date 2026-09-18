export type AuthMethod = 'basic' | 'integrated' | 'public' | 'sso';

export interface ServiceRoute {
  host: string;
  name: string;
  description: string;
  path: string;
  auth: AuthMethod[];
  url: string;
}