interface PresetConfig {
  api_url?: string;
  api_key?: string;
  model_name?: string;
  batch_size: number;
  max_concurrent: number;
  rpm_limit: number;
  max_retries: number;
  retry_delay: number;
  max_tokens: number;
  enable_discovery: boolean;
  enable_names_db: boolean;
  target_lang: string;
  target_format: string;
  bilingual: boolean;
  temp_terms: number;
  temp_literal: number;
  temp_polish: number;
}

export interface TaskStatus {
  task_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  current_stage: string;
  error: string | null;
}

export interface TaskResponse {
  task_id: string;
  status: string;
}

export interface PresetResponse {
  presets: Record<string, PresetConfig>;
}

export interface TranslateParams {
  target_lang: 'zh' | 'en';
  format: 'ass' | 'srt';
  bilingual: boolean;
  temperature_terms: number;
  temperature_literal: number;
  temperature_polish: number;
  model_name: string;
  api_url: string;
  api_key: string;
  batch_size: number;
  max_concurrent: number;
  rpm_limit: number;
  max_retries: number;
  retry_delay: number;
  max_tokens: number;
  enable_discovery: boolean;
  enable_names_db: boolean;
}
