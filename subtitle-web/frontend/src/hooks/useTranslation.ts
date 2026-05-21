import { useState, useCallback } from 'react';
import { getTaskStatus, getTaskLogs, getDownloadUrl } from '../services/api';
import type { TaskStatus } from '../types';

export function useTranslation() {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [status, setStatus] = useState<TaskStatus | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pollingInterval, setPollingInterval] = useState<number | null>(null);

  const startPolling = useCallback((id: string) => {
    setTaskId(id);
    setError(null);

    const poll = async () => {
      try {
        const taskStatus = await getTaskStatus(id);
        setStatus(taskStatus);

        const logData = await getTaskLogs(id);
        setLogs(logData.logs);

        if (taskStatus.status === 'completed' || taskStatus.status === 'failed') {
          if (pollingInterval) {
            clearInterval(pollingInterval);
            setPollingInterval(null);
          }
        }
      } catch (err) {
        console.error('轮询错误:', err);
      }
    };

    poll();
    const interval = window.setInterval(poll, 1000);
    setPollingInterval(interval);
  }, [pollingInterval]);

  const stopPolling = useCallback(() => {
    if (pollingInterval) {
      clearInterval(pollingInterval);
      setPollingInterval(null);
    }
  }, [pollingInterval]);

  const reset = useCallback(() => {
    stopPolling();
    setTaskId(null);
    setStatus(null);
    setLogs([]);
    setError(null);
  }, [stopPolling]);

  const downloadUrl = taskId && status?.status === 'completed' ? getDownloadUrl(taskId) : null;

  return {
    taskId,
    status,
    logs,
    error,
    downloadUrl,
    startPolling,
    stopPolling,
    reset,
  };
}
