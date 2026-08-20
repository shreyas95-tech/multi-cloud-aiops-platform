/**
 * API service layer for communicating with the FastAPI backend.
 */
import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 responses (session expired)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      const currentPath = window.location.pathname;
      if (currentPath !== '/login' && currentPath !== '/reset-password') {
        window.location.href = `/login?redirect=${encodeURIComponent(currentPath)}`;
      }
    }
    return Promise.reject(error);
  }
);

// --- Auth ---

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  must_reset_password: boolean;
}

export interface RegisterResponse {
  id: string;
  username: string;
  email: string;
  message: string;
}

export interface UserInfo {
  id: string;
  username: string;
  email: string;
  role: string;
  group_id: string | null;
  group_name: string | null;
  must_reset_password: boolean;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>('/auth/login', { username, password });
  return data;
}

export async function register(username: string, email: string, password: string): Promise<RegisterResponse> {
  const { data } = await api.post<RegisterResponse>('/auth/register', { username, email, password });
  return data;
}

export async function getMe(): Promise<UserInfo> {
  const { data } = await api.get<UserInfo>('/auth/me');
  return data;
}

// --- Reports ---

export interface ReportSummary {
  id: string;
  name: string;
  file_type: string;
  status: string;
  received_at: string;
  parsed_at: string | null;
  group_id: string | null;
  group_name: string | null;
}

export interface TrendDataPoint {
  value: number;
  timestamp: string;
  metric_name: string;
}

export interface TrendResult {
  id: string;
  metric_name: string;
  direction: string;
  rate_of_change_pct: number;
  algorithm_used: string;
  data_points_count: number;
  computed_at: string;
}

export interface TrendVisualization {
  report_name: string;
  trends: TrendResult[];
  data_points: TrendDataPoint[];
}

export interface Deviation {
  id: string;
  metric_name: string;
  expected_value: number;
  actual_value: number;
  deviation_score: number;
  severity: string;
  detected_at: string;
}

export async function getReports(): Promise<ReportSummary[]> {
  const { data } = await api.get<{ reports: ReportSummary[]; count: number }>('/reports');
  return data.reports;
}

export async function getReportTrends(reportName: string, days = 30): Promise<TrendVisualization> {
  const { data } = await api.get<TrendVisualization>(
    `/reports/${encodeURIComponent(reportName)}/trends`,
    { params: { days } }
  );
  return data;
}

export async function getReportDeviations(reportName: string, days = 30): Promise<Deviation[]> {
  const { data } = await api.get<{ deviations: Deviation[]; count: number }>(
    `/reports/${encodeURIComponent(reportName)}/deviations`,
    { params: { days } }
  );
  return data.deviations;
}

// --- Phone Numbers ---

export interface PhoneNumber {
  id: string;
  number: string;
  status: string;
  verified_at: string | null;
}

export async function getPhoneNumbers(): Promise<PhoneNumber[]> {
  const { data } = await api.get<{ phone_numbers: PhoneNumber[]; count: number }>('/phone-numbers');
  return data.phone_numbers;
}

export async function addPhoneNumber(number: string): Promise<PhoneNumber> {
  const { data } = await api.post<PhoneNumber>('/phone-numbers', { number });
  return data;
}

export async function verifyPhoneNumber(number: string, code: string): Promise<PhoneNumber> {
  const { data } = await api.post<PhoneNumber>('/phone-numbers/verify', { number, code });
  return data;
}

export async function removePhoneNumber(id: string): Promise<void> {
  await api.delete(`/phone-numbers/${id}`);
}

// --- Admin ---

export interface AdminUser {
  id: string;
  username: string;
  email: string;
  role: string;
  group_name: string | null;
  group_id: string | null;
  must_reset_password: boolean;
  last_active: string | null;
}

export interface AdminGroup {
  id: string;
  name: string;
  description: string | null;
  member_count: number;
}

export async function getUsers(): Promise<AdminUser[]> {
  const { data } = await api.get<{ users: AdminUser[]; count: number }>('/admin/users');
  return data.users;
}

export async function createUser(username: string, email: string, password: string, role: string, groupId?: string) {
  const { data } = await api.post('/admin/users', {
    username, email, password, role, group_id: groupId || null,
  });
  return data;
}

export async function getGroups(): Promise<AdminGroup[]> {
  const { data } = await api.get<{ groups: AdminGroup[]; count: number }>('/admin/groups');
  return data.groups;
}

export async function createGroup(name: string, description?: string) {
  const { data } = await api.post('/admin/groups', { name, description });
  return data;
}

export async function assignUserToGroup(userId: string, groupId: string | null) {
  const { data } = await api.put(`/admin/users/${userId}/group`, null, { params: { group_id: groupId } });
  return data;
}

export default api;
