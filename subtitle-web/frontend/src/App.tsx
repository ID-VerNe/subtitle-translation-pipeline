import { useState, useCallback, useEffect } from 'react';
import { useTranslation } from './hooks/useTranslation';
import { submitTranslation, getConfig, getPresets, savePreset } from './services/api';
import type { PresetConfig, TranslateParams } from './types';

export default function App() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [config, setConfig] = useState<PresetConfig | null>(null);
  const [presets, setPresets] = useState<Record<string, PresetConfig>>({});
  const [currentPreset, setCurrentPreset] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { status, logs, downloadUrl, startPolling, reset } = useTranslation();

  const loadInitialData = useCallback(async () => {
    try {
      setError(null);
      const [initialConfig, initialPresets] = await Promise.all([
        getConfig(),
        getPresets()
      ]);
      setConfig(initialConfig);
      setPresets(initialPresets);
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : 'Could not reach server');
    }
  }, []);

  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
  }, []);

  const handlePresetChange = useCallback((presetName: string) => {
    setCurrentPreset(presetName);
    if (presets[presetName]) {
      setConfig(presets[presetName]);
    }
  }, [presets]);

  const handleSavePreset = useCallback(async () => {
    if (!config) return;
    const name = prompt('Enter a name for this preset:');
    if (!name) return;
    await savePreset(name, config);
    const updated = await getPresets();
    setPresets(updated);
    setCurrentPreset(name);
    alert(`Preset "${name}" has been saved.`);
  }, [config]);

  const handleSubmit = useCallback(async () => {
    if (!selectedFile || !config) return;

    setIsSubmitting(true);
    reset();

    try {
      const params: TranslateParams = {
        target_lang: config.target_lang as 'zh' | 'en',
        format: config.target_format as 'ass' | 'srt',
        bilingual: config.bilingual,
        temperature_terms: config.temp_terms,
        temperature_literal: config.temp_literal,
        temperature_polish: config.temp_polish,
        model_name: config.model_name || '',
        api_url: config.api_url || '',
        api_key: config.api_key || '',
        batch_size: config.batch_size,
        max_concurrent: config.max_concurrent,
        rpm_limit: config.rpm_limit,
        max_retries: config.max_retries,
        retry_delay: config.retry_delay,
        max_tokens: config.max_tokens,
        enable_discovery: config.enable_discovery,
        enable_names_db: config.enable_names_db,
      };

      const response = await submitTranslation(selectedFile, params);
      startPolling(response.task_id);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Submission failed. Please check your settings.');
    } finally {
      setIsSubmitting(false);
    }
  }, [selectedFile, config, reset, startPolling]);

  const handleReset = useCallback(() => {
    reset();
    setSelectedFile(null);
  }, [reset]);

  const getStatusBadgeClass = (s?: string) => {
    switch (s) {
      case 'processing': return 'status-processing';
      case 'completed': return 'status-completed';
      case 'failed': return 'status-failed';
      default: return 'status-pending';
    }
  };

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white p-6">
        <div className="card shadow-xl max-w-md w-full text-center space-y-6">
          <div className="text-airbnb-rausch">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-16 h-16 mx-auto">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
          </div>
          <div>
            <h2 className="text-xl font-bold mb-2">Something went wrong</h2>
            <p className="text-airbnb-secondary-gray text-sm">{error}</p>
          </div>
          <button onClick={loadInitialData} className="btn-primary w-full py-3">
            Try Again
          </button>
        </div>
      </div>
    );
  }

  if (!config) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white">
        <div className="flex flex-col items-center gap-6">
          <div className="w-14 h-14 border-4 border-gray-100 border-t-airbnb-rausch rounded-full animate-spin"></div>
          <div className="text-airbnb-near-black font-semibold text-lg animate-pulse">Setting up your experience...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white text-airbnb-near-black">
      <header className="header-airbnb">
        <div className="logo-text">
          <svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg" style={{ display: 'block', height: '32px', width: '32px', fill: 'currentcolor' }}>
            <path d="M16 1c2.008 0 3.463.963 4.751 3.269l.533 1.025c1.954 3.83 6.114 12.54 7.1 14.836l.145.353c.667 1.591.91 2.472.96 3.396l.01.415.001.228c0 4.062-2.877 6.478-6.357 6.478-2.224 0-4.556-1.258-6.709-3.386l-.257-.26-.172-.179h-.011l-.176.185c-2.044 2.1-4.392 3.42-6.72 3.42-3.481 0-6.358-2.416-6.358-6.478l.002-.455c.03-.924.272-1.805.94-3.396l.144-.353c.987-2.297 5.147-11.007 7.1-14.836l.533-1.025C12.537 1.963 13.992 1 16 1zm0 2c-1.239 0-2.053.539-2.987 2.21l-.523 1.008c-1.926 3.776-6.06 12.43-7.031 14.692l-.145.353c-.567 1.356-.756 2.04-.803 2.739l-.012.418v.228c0 2.966 2.025 4.478 4.358 4.478 1.62 0 3.482-1.039 5.433-3.134l.284-.31.364-.391L16 23.44l1.042 1.12c.124.133.245.26.364.391l.282.31c1.954 2.095 3.817 3.134 5.437 3.134 2.333 0 4.357-1.512 4.357-4.478l-.001-.228v-.134l-.013-.284c-.047-.7-.236-1.383-.804-2.739l-.145-.353c-.971-2.262-5.105-10.916-7.031-14.692l-.523-1.008C18.053 3.539 17.24 3 16 3zm.01 10.316l-.105.106c-1.127 1.154-1.838 2.37-2.133 3.647l-.101.488-.042.274-.012.115c-.104 1.135.093 2.181.593 3.111l.214.363.144.226c.214.312.484.593.811.841l.307.218.423.256.126.068.125-.069.422-.256.308-.218c.327-.248.597-.529.811-.84l.146-.228.212-.362c.5-.93.697-1.977.593-3.111l-.012-.115-.041-.274-.102-.488c-.295-1.277-1.006-2.493-2.132-3.647l-.106-.106zm-.01 2c.813.824 1.353 1.723 1.611 2.697l.06.27.03.181c.045.55-.04 1.054-.254 1.511l-.093.183-.066.113c-.107.165-.246.315-.417.452l-.121.092-.122.083-.122-.083-.122-.092c-.17-.137-.309-.287-.417-.452l-.065-.113-.093-.183c-.214-.457-.3-1.012-.255-1.511l.03-.181.06-.27c.258-.974.798-1.873 1.611-2.697z"></path>
          </svg>
          Subtitle Pipeline
        </div>
        <div className="flex items-center gap-6">
          <span className="text-sm font-semibold cursor-pointer">Explore</span>
          <span className="text-sm font-semibold cursor-pointer">Status</span>
          <div className="flex items-center gap-2 p-1 border border-airbnb-border-gray rounded-full shadow-sm hover:shadow-md transition-shadow cursor-pointer bg-white">
            <svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg" style={{ display: 'block', fill: 'none', height: '16px', width: '16px', stroke: 'currentColor', strokeWidth: '3', marginLeft: '8px' }}>
              <g fill="none"><path d="M2 16h28M2 24h28M2 8h28"></path></g>
            </svg>
            <div className="w-8 h-8 rounded-full bg-gray-500 flex items-center justify-center text-white">
              <svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg" style={{ display: 'block', fill: 'currentcolor', height: '20px', width: '20px' }}>
                <path d="m16 .7c-8.437 0-15.3 6.863-15.3 15.3s6.863 15.3 15.3 15.3 15.3-6.863 15.3-15.3-6.863-15.3-15.3-15.3zm0 28c-4.021 0-7.605-1.884-9.933-4.81a12.425 12.425 0 0 1 6.451-4.4 6.507 6.507 0 0 1 -3.018-5.49c0-3.584 2.916-6.5 6.5-6.5s6.5 2.916 6.5 6.5a6.513 6.513 0 0 1 -3.019 5.491 12.42 12.42 0 0 1 6.452 4.4c-2.328 2.925-5.912 4.809-9.933 4.809z"></path>
              </svg>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-12 md:px-12">
        <div className="mb-12">
          <h1 className="text-3xl font-bold mb-2">Refine your subtitles with AI</h1>
          <p className="text-airbnb-secondary-gray text-lg">A seamless pipeline to translate and polish your video content.</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12">
          {/* Configuration Section */}
          <div className="lg:col-span-8 space-y-12">
            
            {/* 1. File Upload */}
            <section>
              <h2 className="text-2xl font-bold mb-6">1. Your Media</h2>
              <div className="card-flat">
                <div className="flex flex-col items-center justify-center border-2 border-dashed border-airbnb-border-gray rounded-2xl p-12 hover:border-airbnb-rausch transition-colors cursor-pointer relative">
                  <input
                    type="file"
                    accept=".mkv,.srt,.ass"
                    onChange={handleFileSelect}
                    className="absolute inset-0 opacity-0 cursor-pointer"
                  />
                  <div className="text-center">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-12 h-12 mx-auto mb-4 text-airbnb-secondary-gray">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                      <polyline points="17 8 12 3 7 8"></polyline>
                      <line x1="12" y1="3" x2="12" y2="15"></line>
                    </svg>
                    <div className="font-bold text-lg mb-1">Click to upload or drag and drop</div>
                    <div className="text-airbnb-secondary-gray text-sm">SRT, ASS, or MKV (we'll extract subtitles)</div>
                  </div>
                </div>
                {selectedFile && (
                  <div className="mt-4 flex items-center gap-3 p-4 bg-green-50 rounded-xl border border-green-100">
                    <div className="bg-green-500 rounded-full p-1 text-white">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" className="w-4 h-4">
                        <polyline points="20 6 9 17 4 12"></polyline>
                      </svg>
                    </div>
                    <div>
                      <div className="font-bold text-green-800">{selectedFile.name}</div>
                      <div className="text-xs text-green-600">Ready to be processed</div>
                    </div>
                  </div>
                )}
              </div>
            </section>

            {/* 2. Destination */}
            <section>
              <h2 className="text-2xl font-bold mb-6">2. Destination</h2>
              <div className="card-flat grid grid-cols-1 md:grid-cols-2 gap-8">
                <div className="space-y-4">
                  <label className="block text-xs font-bold uppercase tracking-widest text-airbnb-secondary-gray">Target Language</label>
                  <select
                    value={config.target_lang}
                    onChange={e => setConfig({ ...config, target_lang: e.target.value })}
                    className="input-select w-full"
                  >
                    <option value="zh">Chinese (Simplified)</option>
                    <option value="en">English</option>
                  </select>
                </div>
                <div className="space-y-4">
                  <label className="block text-xs font-bold uppercase tracking-widest text-airbnb-secondary-gray">Format</label>
                  <select
                    value={config.target_format}
                    onChange={e => setConfig({ ...config, target_format: e.target.value })}
                    className="input-select w-full"
                  >
                    <option value="ass">ASS (Preserve styles)</option>
                    <option value="srt">SRT (Plain text)</option>
                  </select>
                </div>
                
                <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="flex items-center justify-between p-4 border border-airbnb-border-gray rounded-xl hover:bg-airbnb-light-surface transition-colors">
                    <div>
                      <div className="font-bold">Bilingual</div>
                      <div className="text-xs text-airbnb-secondary-gray">Keep original text</div>
                    </div>
                    <input
                      type="checkbox"
                      checked={config.bilingual}
                      onChange={e => setConfig({ ...config, bilingual: e.target.checked })}
                      className="input-checkbox"
                    />
                  </div>
                  <div className="flex items-center justify-between p-4 border border-airbnb-border-gray rounded-xl hover:bg-airbnb-light-surface transition-colors">
                    <div>
                      <div className="font-bold">Discovery</div>
                      <div className="text-xs text-airbnb-secondary-gray">Pre-scan for terms</div>
                    </div>
                    <input
                      type="checkbox"
                      checked={config.enable_discovery}
                      onChange={e => setConfig({ ...config, enable_discovery: e.target.checked })}
                      className="input-checkbox"
                    />
                  </div>
                  <div className="flex items-center justify-between p-4 border border-airbnb-border-gray rounded-xl hover:bg-airbnb-light-surface transition-colors">
                    <div>
                      <div className="font-bold">Names DB</div>
                      <div className="text-xs text-airbnb-secondary-gray">Use local glossary</div>
                    </div>
                    <input
                      type="checkbox"
                      checked={config.enable_names_db}
                      onChange={e => setConfig({ ...config, enable_names_db: e.target.checked })}
                      className="input-checkbox"
                    />
                  </div>
                </div>
              </div>
            </section>

            {/* 3. AI Engine */}
            <section>
              <h2 className="text-2xl font-bold mb-6">3. AI Engine</h2>
              <div className="card-flat space-y-8">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  <div className="space-y-4">
                    <label className="block text-xs font-bold uppercase tracking-widest text-airbnb-secondary-gray">API Endpoint</label>
                    <input
                      type="text"
                      value={config.api_url || ''}
                      onChange={e => setConfig({ ...config, api_url: e.target.value })}
                      className="input-field"
                      placeholder="https://api.openai.com/v1"
                    />
                  </div>
                  <div className="space-y-4">
                    <label className="block text-xs font-bold uppercase tracking-widest text-airbnb-secondary-gray">API Key</label>
                    <input
                      type="password"
                      value={config.api_key || ''}
                      onChange={e => setConfig({ ...config, api_key: e.target.value })}
                      className="input-field"
                      placeholder="sk-..."
                    />
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  <div className="space-y-4">
                    <label className="block text-xs font-bold uppercase tracking-widest text-airbnb-secondary-gray">Model Name</label>
                    <input
                      type="text"
                      value={config.model_name || ''}
                      onChange={e => setConfig({ ...config, model_name: e.target.value })}
                      className="input-field"
                      placeholder="gpt-4o"
                    />
                  </div>
                  <div className="space-y-4">
                    <label className="block text-xs font-bold uppercase tracking-widest text-airbnb-secondary-gray">Max Output Tokens</label>
                    <input
                      type="number"
                      value={config.max_tokens}
                      onChange={e => setConfig({ ...config, max_tokens: parseInt(e.target.value) || 4096 })}
                      className="input-field"
                    />
                  </div>
                </div>
              </div>
            </section>

            {/* 4. Fine-tuning */}
            <section>
              <h2 className="text-2xl font-bold mb-6">4. Fine-tuning</h2>
              <div className="card-flat space-y-12">
                <div className="space-y-6">
                  <div className="flex justify-between items-end">
                    <div>
                      <div className="font-bold text-lg">Creativity Levels</div>
                      <div className="text-sm text-airbnb-secondary-gray">Adjust temperatures for different stages</div>
                    </div>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                    <div className="space-y-4">
                      <div className="flex justify-between text-sm">
                        <span className="font-medium">Discovery</span>
                        <span className="text-airbnb-rausch font-bold">{config.temp_terms.toFixed(1)}</span>
                      </div>
                      <input
                        type="range" min="0" max="1" step="0.1"
                        value={config.temp_terms}
                        onChange={e => setConfig({ ...config, temp_terms: parseFloat(e.target.value) })}
                        className="input-range"
                      />
                    </div>
                    <div className="space-y-4">
                      <div className="flex justify-between text-sm">
                        <span className="font-medium">Literal</span>
                        <span className="text-airbnb-rausch font-bold">{config.temp_literal.toFixed(1)}</span>
                      </div>
                      <input
                        type="range" min="0" max="1" step="0.1"
                        value={config.temp_literal}
                        onChange={e => setConfig({ ...config, temp_literal: parseFloat(e.target.value) })}
                        className="input-range"
                      />
                    </div>
                    <div className="space-y-4">
                      <div className="flex justify-between text-sm">
                        <span className="font-medium">Polish</span>
                        <span className="text-airbnb-rausch font-bold">{config.temp_polish.toFixed(1)}</span>
                      </div>
                      <input
                        type="range" min="0" max="1" step="0.1"
                        value={config.temp_polish}
                        onChange={e => setConfig({ ...config, temp_polish: parseFloat(e.target.value) })}
                        className="input-range"
                      />
                    </div>
                  </div>
                </div>

                <div className="pt-8 border-t border-airbnb-border-gray">
                  <div className="font-bold text-lg mb-6">Advanced Pipeline</div>
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
                    <div className="space-y-2">
                      <label className="text-xs font-bold uppercase tracking-widest text-airbnb-secondary-gray">Batch Size</label>
                      <input
                        type="number" value={config.batch_size}
                        onChange={e => setConfig({ ...config, batch_size: parseInt(e.target.value) || 8 })}
                        className="input-field py-2"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-xs font-bold uppercase tracking-widest text-airbnb-secondary-gray">Concurrent</label>
                      <input
                        type="number" value={config.max_concurrent}
                        onChange={e => setConfig({ ...config, max_concurrent: parseInt(e.target.value) || 4 })}
                        className="input-field py-2"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-xs font-bold uppercase tracking-widest text-airbnb-secondary-gray">RPM Limit</label>
                      <input
                        type="number" value={config.rpm_limit}
                        onChange={e => setConfig({ ...config, rpm_limit: parseInt(e.target.value) || 60 })}
                        className="input-field py-2"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-xs font-bold uppercase tracking-widest text-airbnb-secondary-gray">Retries</label>
                      <input
                        type="number" value={config.max_retries}
                        onChange={e => setConfig({ ...config, max_retries: parseInt(e.target.value) || 3 })}
                        className="input-field py-2"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-xs font-bold uppercase tracking-widest text-airbnb-secondary-gray">Delay (s)</label>
                      <input
                        type="number" value={config.retry_delay}
                        onChange={e => setConfig({ ...config, retry_delay: parseInt(e.target.value) || 1 })}
                        className="input-field py-2"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>

          {/* Action Sidebar */}
          <div className="lg:col-span-4">
            <div className="sticky top-28 space-y-6">
              <div className="card shadow-xl border border-airbnb-border-gray">
                <div className="text-2xl font-bold mb-6">Reservation</div>
                
                <div className="space-y-6">
                  <div>
                    <label className="block text-xs font-bold uppercase tracking-widest text-airbnb-secondary-gray mb-3">Choose Profile</label>
                    <select
                      value={currentPreset}
                      onChange={e => handlePresetChange(e.target.value)}
                      className="input-select w-full"
                    >
                      <option value="">Standard Setup</option>
                      {Object.keys(presets).map(name => (
                        <option key={name} value={name}>{name}</option>
                      ))}
                    </select>
                  </div>

                  <button
                    onClick={handleSubmit}
                    disabled={!selectedFile || isSubmitting || status?.status === 'processing'}
                    className="btn-primary w-full py-4 rounded-xl text-lg shadow-lg hover:shadow-xl active:scale-95 transition-all"
                  >
                    {isSubmitting ? 'Confirming...' : status?.status === 'processing' ? 'Processing Trip...' : 'Reserve Translation'}
                  </button>

                  <p className="text-center text-xs text-airbnb-secondary-gray">
                    Your credits will be applied upon completion.
                  </p>

                  {status && (
                    <div className="pt-6 border-t border-airbnb-border-gray">
                      <div className="flex justify-between items-center mb-3">
                        <span className="font-bold text-sm uppercase tracking-widest">{status.current_stage || 'Preparing'}</span>
                        <span className={`status-badge ${getStatusBadgeClass(status.status)}`}>
                          {status.progress}%
                        </span>
                      </div>
                      <div className="progress-bar mb-6">
                        <div className="progress-bar-fill" style={{ width: `${status.progress}%` }} />
                      </div>
                      {status.error && (
                        <div className="p-3 bg-red-50 text-red-600 rounded-lg text-xs font-medium mb-4 border border-red-100">
                          {status.error}
                        </div>
                      )}
                    </div>
                  )}

                  <div className="log-container h-40 overflow-y-auto scroll-smooth">
                    {logs.length === 0 ? (
                      <div className="flex flex-col items-center justify-center h-full text-gray-300 opacity-60">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" className="w-10 h-10 mb-2">
                          <circle cx="12" cy="12" r="10"></circle>
                          <line x1="12" y1="8" x2="12" y2="12"></line>
                          <line x1="12" y1="16" x2="12.01" y2="16"></line>
                        </svg>
                        <span className="text-xs">Waiting for takeoff</span>
                      </div>
                    ) : (
                      logs.map((log, i) => (
                        <p key={i} className="text-[11px] leading-relaxed py-1.5 border-b border-airbnb-border-gray/30 last:border-0 font-mono">
                          {log}
                        </p>
                      ))
                    )}
                  </div>

                  {downloadUrl && (
                    <a
                      href={downloadUrl}
                      download
                      className="btn-secondary w-full py-4 text-center block rounded-xl shadow-md hover:shadow-lg transition-all"
                    >
                      Retrieve Results
                    </a>
                  )}

                  {(status?.status === 'completed' || status?.status === 'failed') && (
                    <button onClick={handleReset} className="btn-outline w-full py-4 rounded-xl">
                      Plan Another Task
                    </button>
                  )}
                </div>
              </div>

              <div className="p-6 border border-airbnb-border-gray rounded-2xl text-center">
                <div className="font-bold mb-1">Save this itinerary?</div>
                <div className="text-xs text-airbnb-secondary-gray mb-4">Keep your configuration for future use.</div>
                <button onClick={handleSavePreset} className="btn-outline w-full text-xs py-3">
                  Create New Preset
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>

      <footer className="mt-24 py-16 border-t border-airbnb-border-gray bg-airbnb-light-surface">
        <div className="max-w-7xl mx-auto px-6 grid grid-cols-2 md:grid-cols-4 gap-12">
          <div className="space-y-4">
            <h4 className="font-bold text-sm uppercase tracking-widest">Support</h4>
            <ul className="text-sm space-y-3 text-airbnb-secondary-gray">
              <li className="hover:underline cursor-pointer">Help Center</li>
              <li className="hover:underline cursor-pointer">Safety information</li>
              <li className="hover:underline cursor-pointer">Cancellation options</li>
            </ul>
          </div>
          <div className="space-y-4">
            <h4 className="font-bold text-sm uppercase tracking-widest">Community</h4>
            <ul className="text-sm space-y-3 text-airbnb-secondary-gray">
              <li className="hover:underline cursor-pointer">Disaster relief housing</li>
              <li className="hover:underline cursor-pointer">Combating discrimination</li>
            </ul>
          </div>
          <div className="space-y-4">
            <h4 className="font-bold text-sm uppercase tracking-widest">Pipeline</h4>
            <ul className="text-sm space-y-3 text-airbnb-secondary-gray">
              <li className="hover:underline cursor-pointer">How it works</li>
              <li className="hover:underline cursor-pointer">API reference</li>
              <li className="hover:underline cursor-pointer">Privacy policy</li>
            </ul>
          </div>
          <div className="space-y-4">
            <h4 className="font-bold text-sm uppercase tracking-widest">About</h4>
            <ul className="text-sm space-y-3 text-airbnb-secondary-gray">
              <li className="hover:underline cursor-pointer">Newsroom</li>
              <li className="hover:underline cursor-pointer">New features</li>
              <li className="hover:underline cursor-pointer">Investors</li>
            </ul>
          </div>
        </div>
        <div className="max-w-7xl mx-auto px-6 mt-16 pt-8 border-t border-airbnb-border-gray flex flex-col md:flex-row justify-between items-center gap-4 text-xs text-airbnb-secondary-gray">
          <div className="flex gap-4">
            <span>© 2026 Subtitle Pipeline, Inc.</span>
            <span className="hover:underline cursor-pointer">Privacy</span>
            <span className="hover:underline cursor-pointer">Terms</span>
            <span className="hover:underline cursor-pointer">Sitemap</span>
          </div>
          <div className="flex gap-6 font-bold text-airbnb-near-black items-center">
            <div className="flex items-center gap-2 hover:underline cursor-pointer">
              <svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" style={{ display: 'block', height: '16px', width: '16px', fill: 'currentcolor' }}>
                <path d="m8 0c4.4 0 8 3.6 8 8s-3.6 8-8 8-8-3.6-8-8 3.6-8 8-8zm0 15.1c3.9 0 7.1-3.2 7.1-7.1s-3.2-7.1-7.1-7.1-7.1 3.2-7.1 7.1 3.2 7.1 7.1 7.1zm.7-10.8v2.1h2.1v1.4h-2.1v2.1h-1.4v-2.1h-2.1v-1.4h2.1v-2.1z"></path>
              </svg>
              English (US)
            </div>
            <div className="hover:underline cursor-pointer">$ USD</div>
          </div>
        </div>
      </footer>
    </div>
  );
}
