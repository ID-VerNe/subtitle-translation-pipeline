import type { TaskStatus } from '../types';

interface ProgressViewProps {
  status: TaskStatus | null;
  logs: string[];
}

export default function ProgressView({ status, logs }: ProgressViewProps) {
  const getStatusClass = (taskStatus: string) => {
    switch (taskStatus) {
      case 'completed':
        return 'status-completed';
      case 'failed':
        return 'status-failed';
      case 'processing':
        return 'status-processing';
      default:
        return 'status-pending';
    }
  };

  const getStatusText = (taskStatus: string) => {
    switch (taskStatus) {
      case 'pending':
        return 'Pending';
      case 'processing':
        return 'Processing';
      case 'completed':
        return 'Completed';
      case 'failed':
        return 'Failed';
      default:
        return taskStatus;
    }
  };

  return (
    <div className="card-flat">
      <div className="flex items-center justify-between mb-6">
        <h2
          style={{
            fontSize: '17px',
            lineHeight: '1.29',
            letterSpacing: '-0.224px',
            fontWeight: '600',
            color: '#1d1d1f'
          }}
        >
          Progress
        </h2>
        {status && (
          <span className={`status-badge ${getStatusClass(status.status)}`}>
            {getStatusText(status.status)}
          </span>
        )}
      </div>

      {status && (
        <div className="mb-6">
          <div className="progress-bar">
            <div
              className="progress-bar-fill"
              style={{ width: `${status.progress}%` }}
            />
          </div>
          <div className="flex justify-between mt-2">
            <span
              style={{
                fontSize: '12px',
                lineHeight: '1.33',
                letterSpacing: '-0.12px',
                color: 'rgba(0, 0, 0, 0.6)'
              }}
            >
              {status.current_stage || 'Preparing'}
            </span>
            <span
              style={{
                fontSize: '12px',
                lineHeight: '1.33',
                letterSpacing: '-0.12px',
                color: '#0071e3',
                fontWeight: '500'
              }}
            >
              {status.progress}%
            </span>
          </div>
        </div>
      )}

      <div style={{ borderTop: '1px solid rgba(0, 0, 0, 0.08)', paddingTop: '16px' }}>
        <h3
          className="mb-3"
          style={{
            fontSize: '12px',
            lineHeight: '1.33',
            letterSpacing: '-0.12px',
            fontWeight: '600',
            color: 'rgba(0, 0, 0, 0.6)',
            textTransform: 'uppercase'
          }}
        >
          Logs
        </h3>
        <div className="log-container">
          {logs.length === 0 ? (
            <p
              className="text-center py-8"
              style={{ color: 'rgba(0, 0, 0, 0.4)' }}
            >
              No logs yet
            </p>
          ) : (
            logs.map((log, index) => (
              <p
                key={index}
                className="log-line"
                style={{
                  color: '#1d1d1f',
                  fontSize: '12px',
                  lineHeight: '1.5'
                }}
              >
                {log}
              </p>
            ))
          )}
        </div>
      </div>

      {status?.error && (
        <div
          className="mt-4 rounded-lg p-4"
          style={{ backgroundColor: 'rgba(255, 59, 48, 0.08)' }}
        >
          <p
            style={{
              fontSize: '14px',
              lineHeight: '1.43',
              letterSpacing: '-0.224px',
              color: '#ff3b30'
            }}
          >
            {status.error}
          </p>
        </div>
      )}
    </div>
  );
}
