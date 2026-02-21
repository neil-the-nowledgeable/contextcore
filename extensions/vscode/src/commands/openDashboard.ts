import * as vscode from 'vscode';
import { ContextMapper } from '../mapping';
import { getFullConfig } from '../config';
import * as logger from '../logger';

interface DashboardEntry {
  uid: string;
  label: string;
  description: string;
  category: string;
  supportsProjectVar: boolean;
}

const DASHBOARDS: DashboardEntry[] = [
  // Core
  { uid: 'contextcore-portfolio', label: 'Project Portfolio Overview', description: 'High-level portfolio health', category: 'Core', supportsProjectVar: true },
  { uid: 'contextcore-installation', label: 'Installation Verification', description: 'Self-monitoring verification status', category: 'Core', supportsProjectVar: false },
  { uid: 'contextcore-value', label: 'Value Capabilities Explorer', description: 'Capability value mapping', category: 'Core', supportsProjectVar: true },
  { uid: 'contextcore-progress', label: 'Project Progress', description: 'Task progress and burndown', category: 'Core', supportsProjectVar: true },
  { uid: 'contextcore-sprint', label: 'Sprint Metrics', description: 'Sprint velocity and completion', category: 'Core', supportsProjectVar: true },
  { uid: 'contextcore-ops', label: 'Project Operations', description: 'Operational health and events', category: 'Core', supportsProjectVar: true },
  { uid: 'contextcore-tasks', label: 'Project Tasks', description: 'Task spans from Tempo', category: 'Core', supportsProjectVar: true },
  { uid: 'contextcore-agent-insights', label: 'Agent Insights', description: 'Agent decisions and recommendations', category: 'Core', supportsProjectVar: true },
  { uid: 'agent-trigger', label: 'Agent Trigger', description: 'Agent trigger events', category: 'Core', supportsProjectVar: false },
  // Expansion packs
  { uid: 'fox-alert-automation', label: 'Fox Alert Automation', description: 'Alert-triggered automation pipeline', category: 'Fox', supportsProjectVar: true },
  { uid: 'beaver-lead-contractor', label: 'Lead Contractor Progress', description: 'Code generation pipeline status', category: 'Beaver', supportsProjectVar: true },
  { uid: 'skills-browser', label: 'Skills Browser', description: 'Squirrel skills discovery', category: 'Squirrel', supportsProjectVar: false },
];

/**
 * Creates and registers the open dashboard command for ContextCore.
 * Shows a QuickPick with all 14 dashboards grouped by category.
 */
export function createOpenDashboardCommand(contextMapper: ContextMapper): vscode.Disposable {
  return vscode.commands.registerCommand('contextcore.openDashboard', async () => {
    try {
      logger.info('Opening dashboard picker...');

      const config = getFullConfig();
      const grafanaUrl = config.grafanaUrl;
      if (!grafanaUrl) {
        vscode.window.showErrorMessage(
          'ContextCore: Grafana URL not configured. Set contextcore.grafanaUrl in settings.'
        );
        return;
      }

      const currentProject = await contextMapper.getCurrentProject();

      const items: vscode.QuickPickItem[] = DASHBOARDS.map(d => ({
        label: d.label,
        description: d.category,
        detail: d.description,
      }));

      const picked = await vscode.window.showQuickPick(items, {
        placeHolder: 'Select a dashboard to open',
        matchOnDescription: true,
        matchOnDetail: true,
      });

      if (!picked) {
        return;
      }

      const dashboard = DASHBOARDS.find(d => d.label === picked.label);
      if (!dashboard) {
        return;
      }

      let url = `${grafanaUrl}/d/${dashboard.uid}`;
      if (dashboard.supportsProjectVar && currentProject) {
        url += `?var-project=${encodeURIComponent(currentProject.id)}`;
      }

      await vscode.env.openExternal(vscode.Uri.parse(url));
      logger.info(`Dashboard opened: ${dashboard.label}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      logger.error('Failed to open dashboard', error);
      vscode.window.showErrorMessage(`ContextCore: Failed to open dashboard - ${message}`);
    }
  });
}
