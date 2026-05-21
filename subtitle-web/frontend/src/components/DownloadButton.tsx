interface DownloadButtonProps {
  downloadUrl: string | null;
  filename?: string;
}

export default function DownloadButton({ downloadUrl, filename }: DownloadButtonProps) {
  if (!downloadUrl) return null;

  const handleDownload = () => {
    if (!downloadUrl) return;

    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = filename || 'translated_subtitle';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div
      className="card flex items-center justify-between"
      style={{ backgroundColor: 'rgba(52, 199, 89, 0.08)' }}
    >
      <div className="flex items-center gap-4">
        <div
          className="w-12 h-12 rounded-full flex items-center justify-center"
          style={{ backgroundColor: 'rgba(52, 199, 89, 0.15)' }}
        >
          <span style={{ fontSize: '24px' }}>✅</span>
        </div>
        <div>
          <h2
            style={{
              fontSize: '17px',
              lineHeight: '1.29',
              letterSpacing: '-0.224px',
              fontWeight: '600',
              color: '#1d1d1f'
            }}
          >
            Translation Complete
          </h2>
          <p
            style={{
              fontSize: '14px',
              lineHeight: '1.43',
              letterSpacing: '-0.224px',
              color: 'rgba(0, 0, 0, 0.6)'
            }}
          >
            Click below to download your translated subtitle
          </p>
        </div>
      </div>
      <button
        onClick={handleDownload}
        className="btn-primary flex items-center gap-2"
        style={{ padding: '12px 24px' }}
      >
        <span>Download</span>
        <span>↓</span>
      </button>
    </div>
  );
}
