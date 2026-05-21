interface TranslationConfigProps {
  targetLang: 'zh' | 'en';
  onTargetLangChange: (lang: 'zh' | 'en') => void;
  format: 'ass' | 'srt';
  onFormatChange: (format: 'ass' | 'srt') => void;
  bilingual: boolean;
  onBilingualChange: (bilingual: boolean) => void;
  tempTerms: number;
  onTempTermsChange: (temp: number) => void;
  tempLiteral: number;
  onTempLiteralChange: (temp: number) => void;
  tempPolish: number;
  onTempPolishChange: (temp: number) => void;
  disabled?: boolean;
}

export default function TranslationConfig({
  targetLang,
  onTargetLangChange,
  format,
  onFormatChange,
  bilingual,
  onBilingualChange,
  tempTerms,
  onTempTermsChange,
  tempLiteral,
  onTempLiteralChange,
  tempPolish,
  onTempPolishChange,
  disabled,
}: TranslationConfigProps) {
  return (
    <div className="card-flat">
      <h2
        className="mb-6"
        style={{
          fontSize: '17px',
          lineHeight: '1.29',
          letterSpacing: '-0.224px',
          fontWeight: '600',
          color: '#1d1d1f'
        }}
      >
        Translation Settings
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
        <div>
          <label
            className="block mb-2"
            style={{
              fontSize: '14px',
              lineHeight: '1.43',
              letterSpacing: '-0.224px',
              fontWeight: '500',
              color: 'rgba(0, 0, 0, 0.8)'
            }}
          >
            Target Language
          </label>
          <select
            value={targetLang}
            onChange={(e) => onTargetLangChange(e.target.value as 'zh' | 'en')}
            disabled={disabled}
            className="input-select w-full"
          >
            <option value="zh">Chinese</option>
            <option value="en">English</option>
          </select>
        </div>

        <div>
          <label
            className="block mb-2"
            style={{
              fontSize: '14px',
              lineHeight: '1.43',
              letterSpacing: '-0.224px',
              fontWeight: '500',
              color: 'rgba(0, 0, 0, 0.8)'
            }}
          >
            Output Format
          </label>
          <select
            value={format}
            onChange={(e) => onFormatChange(e.target.value as 'ass' | 'srt')}
            disabled={disabled}
            className="input-select w-full"
          >
            <option value="ass">ASS Subtitle</option>
            <option value="srt">SRT Subtitle</option>
          </select>
        </div>

        <div className="flex items-center">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={bilingual}
              onChange={(e) => onBilingualChange(e.target.checked)}
              disabled={disabled}
              className="input-checkbox"
            />
            <span
              style={{
                fontSize: '14px',
                lineHeight: '1.43',
                letterSpacing: '-0.224px',
                fontWeight: '500',
                color: 'rgba(0, 0, 0, 0.8)'
              }}
            >
              Bilingual Subtitle
            </span>
          </label>
        </div>
      </div>

      <div
        className="pt-6"
        style={{ borderTop: '1px solid rgba(0, 0, 0, 0.08)' }}
      >
        <h3
          className="mb-4"
          style={{
            fontSize: '14px',
            lineHeight: '1.43',
            letterSpacing: '-0.224px',
            fontWeight: '600',
            color: 'rgba(0, 0, 0, 0.8)'
          }}
        >
          Temperature Parameters
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <div className="flex justify-between items-center mb-2">
              <label
                style={{
                  fontSize: '12px',
                  lineHeight: '1.33',
                  letterSpacing: '-0.12px',
                  color: 'rgba(0, 0, 0, 0.6)'
                }}
              >
                Terms
              </label>
              <span
                style={{
                  fontSize: '12px',
                  lineHeight: '1.33',
                  letterSpacing: '-0.12px',
                  color: '#0071e3',
                  fontWeight: '500'
                }}
              >
                {tempTerms.toFixed(2)}
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={tempTerms}
              onChange={(e) => onTempTermsChange(parseFloat(e.target.value))}
              disabled={disabled}
              className="input-range"
            />
          </div>

          <div>
            <div className="flex justify-between items-center mb-2">
              <label
                style={{
                  fontSize: '12px',
                  lineHeight: '1.33',
                  letterSpacing: '-0.12px',
                  color: 'rgba(0, 0, 0, 0.6)'
                }}
              >
                Literal
              </label>
              <span
                style={{
                  fontSize: '12px',
                  lineHeight: '1.33',
                  letterSpacing: '-0.12px',
                  color: '#0071e3',
                  fontWeight: '500'
                }}
              >
                {tempLiteral.toFixed(2)}
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={tempLiteral}
              onChange={(e) => onTempLiteralChange(parseFloat(e.target.value))}
              disabled={disabled}
              className="input-range"
            />
          </div>

          <div>
            <div className="flex justify-between items-center mb-2">
              <label
                style={{
                  fontSize: '12px',
                  lineHeight: '1.33',
                  letterSpacing: '-0.12px',
                  color: 'rgba(0, 0, 0, 0.6)'
                }}
              >
                Polish
              </label>
              <span
                style={{
                  fontSize: '12px',
                  lineHeight: '1.33',
                  letterSpacing: '-0.12px',
                  color: '#0071e3',
                  fontWeight: '500'
                }}
              >
                {tempPolish.toFixed(2)}
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={tempPolish}
              onChange={(e) => onTempPolishChange(parseFloat(e.target.value))}
              disabled={disabled}
              className="input-range"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
