import React, { useState, useCallback, useEffect, useRef } from 'react';
import { PanelProps } from '@grafana/data';
import { getTemplateSrv } from '@grafana/runtime';
import { Button, useStyles2, Alert, LoadingPlaceholder, ConfirmModal, Badge } from '@grafana/ui';
import { css } from '@emotion/css';
import {
  WorkflowPanelOptions,
  WorkflowStatus,
  DryRunResponse,
  ExecuteResponse,
  StatusResponse,
  DryRunStep,
} from '../types';

interface Props extends PanelProps<WorkflowPanelOptions> {}

export const WorkflowPanel: React.FC<Props> = ({ options, width, height }) => {
  const [status, setStatus] = useState<WorkflowStatus>('idle');
  const [runId, setRunId] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<StatusResponse | null>(null);
  const [dryRunSteps, setDryRunSteps] = useState<DryRunStep[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const styles = useStyles2(getStyles);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  // Resolve template variables in project ID
  const resolvedProjectId = getTemplateSrv().replace(options.projectId);

  // Poll for status updates when running
  useEffect(() => {
    if (status === 'running' && runId && options.refreshInterval > 0) {
      intervalRef.current = setInterval(async () => {
        try {
          // Call Rabbit's trigger endpoint with beaver_workflow_status action
          const res = await fetch(`${options.apiUrl}/trigger`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              action: 'beaver_workflow_status',
              payload: { run_id: runId },
              context: {},
            }),
          });
          if (res.ok) {
            const data = await res.json();
            if (data.status === 'success' && data.data) {
              const runData = data.data as StatusResponse;
              setLastRun(runData);
              if (runData.status === 'completed') {
                setStatus('completed');
              } else if (runData.status === 'failed') {
                setStatus('failed');
                setError(runData.error || 'Workflow failed');
              }
            }
          }
        } catch (err) {
          // Silently ignore polling errors
        }
      }, options.refreshInterval * 1000);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [status, runId, options.apiUrl, options.refreshInterval]);

  const handleDryRun = useCallback(async () => {
    setLoading(true);
    setError(null);
    setDryRunSteps(null);

    try {
      // Call Rabbit's trigger endpoint with beaver_workflow_dry_run action
      const res = await fetch(`${options.apiUrl}/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'beaver_workflow_dry_run',
          payload: { project_id: resolvedProjectId },
          context: { source: 'grafana_panel' },
        }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }

      const data = await res.json();

      if (data.status === 'success') {
        // Rabbit returns data in the 'data' field
        const actionData = data.data || {};
        setDryRunSteps(actionData.steps || []);
        setRunId(data.run_id || actionData.run_id);
      } else {
        setError(data.message || 'Dry run failed');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect to Rabbit API');
    } finally {
      setLoading(false);
    }
  }, [options.apiUrl, resolvedProjectId]);

  const handleExecute = useCallback(async () => {
    if (options.confirmExecution) {
      setShowConfirm(true);
      return;
    }
    await executeWorkflow();
  }, [options.confirmExecution]);

  const executeWorkflow = useCallback(async () => {
    setLoading(true);
    setError(null);
    setStatus('running');
    setDryRunSteps(null);

    try {
      // Call Rabbit's trigger endpoint with beaver_workflow action (fire-and-forget)
      const res = await fetch(`${options.apiUrl}/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'beaver_workflow',
          payload: { project_id: resolvedProjectId, dry_run: false },
          context: { source: 'grafana_panel' },
        }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }

      const data = await res.json();

      if (data.status === 'success') {
        // Rabbit fires and forgets - workflow is now running in background
        const actionData = data.data || {};
        setRunId(actionData.run_id);
      } else {
        setError(data.message || 'Failed to start workflow');
        setStatus('failed');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect to Rabbit API');
      setStatus('failed');
    } finally {
      setLoading(false);
    }
  }, [options.apiUrl, resolvedProjectId]);

  const handleConfirmExecute = useCallback(async () => {
    setShowConfirm(false);
    await executeWorkflow();
  }, [executeWorkflow]);

  const getStatusBadge = () => {
    switch (status) {
      case 'running':
        return <Badge text="Running" color="blue" icon="sync" />;
      case 'completed':
        return <Badge text="Completed" color="green" icon="check" />;
      case 'failed':
        return <Badge text="Failed" color="red" icon="exclamation-triangle" />;
      default:
        return <Badge text="Idle" color="purple" />;
    }
  };

  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleString();
  };

  const formatDuration = (seconds: number) => {
    if (seconds < 60) {
      return `${seconds}s`;
    }
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  };

  return (
    <div className={styles.container} style={{ width, height }}>
      <div className={styles.header}>
        <div className={styles.projectInfo}>
          <span className={styles.label}>Project:</span>
          <span className={styles.value}>{resolvedProjectId}</span>
        </div>
        <div className={styles.statusBadge}>{getStatusBadge()}</div>
      </div>

      <div className={styles.buttonRow}>
        {options.showDryRun && (
          <Button
            onClick={handleDryRun}
            disabled={loading || status === 'running'}
            variant="secondary"
            icon="sync"
          >
            Dry Run
          </Button>
        )}
        {options.showExecute && (
          <Button
            onClick={handleExecute}
            disabled={loading || status === 'running'}
            variant="primary"
            icon="play"
          >
            Execute
          </Button>
        )}
      </div>

      {loading && (
        <div className={styles.loadingSection}>
          <LoadingPlaceholder text="Processing..." />
        </div>
      )}

      {error && (
        <Alert severity="error" title="Error">
          {error}
        </Alert>
      )}

      {dryRunSteps && (
        <div className={styles.stepsSection}>
          <div className={styles.sectionTitle}>Dry Run Preview</div>
          <div className={styles.stepsList}>
            {dryRunSteps.map((step, index) => (
              <div key={index} className={styles.step}>
                <span className={styles.stepStatus}>
                  {step.status === 'would_execute' ? '✓' : step.status === 'would_skip' ? '○' : '✗'}
                </span>
                <span className={styles.stepName}>{step.name}</span>
                {step.reason && <span className={styles.stepReason}>({step.reason})</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {lastRun && (
        <div className={styles.lastRunSection}>
          <div className={styles.sectionTitle}>Last Run</div>
          <div className={styles.lastRunInfo}>
            <div>
              <span className={styles.label}>Run ID:</span>
              <span className={styles.value}>{lastRun.run_id}</span>
            </div>
            <div>
              <span className={styles.label}>Started:</span>
              <span className={styles.value}>{formatTime(lastRun.started_at)}</span>
            </div>
            {lastRun.completed_at && (
              <div>
                <span className={styles.label}>Completed:</span>
                <span className={styles.value}>{formatTime(lastRun.completed_at)}</span>
              </div>
            )}
            {lastRun.duration_seconds !== undefined && (
              <div>
                <span className={styles.label}>Duration:</span>
                <span className={styles.value}>{formatDuration(lastRun.duration_seconds)}</span>
              </div>
            )}
            <div>
              <span className={styles.label}>Progress:</span>
              <span className={styles.value}>
                {lastRun.steps_completed}/{lastRun.steps_total} steps
              </span>
            </div>
          </div>
        </div>
      )}

      <ConfirmModal
        isOpen={showConfirm}
        title="Execute Workflow"
        body={`Are you sure you want to execute the workflow for project "${resolvedProjectId}"?`}
        confirmText="Execute"
        onConfirm={handleConfirmExecute}
        onDismiss={() => setShowConfirm(false)}
      />
    </div>
  );
};

const getStyles = () => ({
  container: css`
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 12px;
    height: 100%;
    overflow: auto;
  `,
  header: css`
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border-weak);
  `,
  projectInfo: css`
    display: flex;
    gap: 8px;
    align-items: center;
  `,
  statusBadge: css`
    display: flex;
    align-items: center;
  `,
  label: css`
    font-size: 12px;
    color: var(--text-secondary);
  `,
  value: css`
    font-weight: 500;
    color: var(--text-primary);
  `,
  buttonRow: css`
    display: flex;
    gap: 8px;
  `,
  loadingSection: css`
    display: flex;
    justify-content: center;
    padding: 20px;
  `,
  stepsSection: css`
    background: var(--background-secondary);
    border-radius: 4px;
    padding: 12px;
  `,
  sectionTitle: css`
    font-weight: 500;
    font-size: 13px;
    margin-bottom: 8px;
    color: var(--text-primary);
  `,
  stepsList: css`
    display: flex;
    flex-direction: column;
    gap: 4px;
  `,
  step: css`
    display: flex;
    gap: 8px;
    align-items: center;
    font-size: 12px;
  `,
  stepStatus: css`
    width: 16px;
    text-align: center;
  `,
  stepName: css`
    color: var(--text-primary);
  `,
  stepReason: css`
    color: var(--text-secondary);
    font-style: italic;
  `,
  lastRunSection: css`
    background: var(--background-secondary);
    border-radius: 4px;
    padding: 12px;
  `,
  lastRunInfo: css`
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;

    > div {
      display: flex;
      gap: 8px;
    }
  `,
});
