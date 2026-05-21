import type { TaskStatus, TaskResponse, PresetConfig, PresetResponse, TranslateParams } from '../types';

const API_BASE = '/api';

export async function submitTranslation(
  file: File,
  params: TranslateParams
): Promise<TaskResponse> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('target_lang', params.target_lang);
  formData.append('format', params.format);
  formData.append('bilingual', String(params.bilingual));
  formData.append('temperature_terms', String(params.temperature_terms));
  formData.append('temperature_literal', String(params.temperature_literal));
  formData.append('temperature_polish', String(params.temperature_polish));
  formData.append('model_name', params.model_name);
  formData.append('api_url', params.api_url);
  formData.append('api_key', params.api_key);
  formData.append('batch_size', String(params.batch_size));
  formData.append('max_concurrent', String(params.max_concurrent));
  formData.append('rpm_limit', String(params.rpm_limit));
  formData.append('max_retries', String(params.max_retries));
  formData.append('retry_delay', String(params.retry_delay));
  formData.append('max_tokens', String(params.max_tokens));
  formData.append('enable_discovery', String(params.enable_discovery));
  formData.append('enable_names_db', String(params.enable_names_db));

  const response = await fetch(`${API_BASE}/translate`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Submit failed');
  }

  return response.json();
}

export async function getTaskStatus(taskId: string): Promise<TaskStatus> {
  const response = await fetch(`${API_BASE}/tasks/${taskId}?t=${Date.now()}`);
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to get status');
  }
  return response.json();
}

export async function getTaskLogs(taskId: string): Promise<{ logs: string[] }> {
  const response = await fetch(`${API_BASE}/tasks/${taskId}/logs?t=${Date.now()}`);
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to get logs');
  }
  return response.json();
}

export function getDownloadUrl(taskId: string): string {
  return `${API_BASE}/tasks/${taskId}/download?t=${Date.now()}`;
}

export async function getPresets(): Promise<Record<string, PresetConfig>> {
  const response = await fetch(`${API_BASE}/presets?t=${Date.now()}`);
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to get presets');
  }
  const data: PresetResponse = await response.json();
  return data.presets;
}

export async function savePreset(name: string, config: PresetConfig): Promise<{ success: boolean }> {
  const response = await fetch(`${API_BASE}/presets`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ name, config }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to save preset');
  }
  return response.json();
}

export async function getConfig(): Promise<PresetConfig> {
  const response = await fetch(`${API_BASE}/config?t=${Date.now()}`);
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to get config');
  }
  return response.json();
}
