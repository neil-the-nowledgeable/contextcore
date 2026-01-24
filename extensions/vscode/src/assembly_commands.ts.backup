// src/commands/index.ts
/**
 * Central export point for all ContextCore commands
 */
export { createRefreshCommand } from './refreshContext';
export { createShowImpactCommand } from './showImpact';
export { createOpenDashboardCommand } from './openDashboard';
export { createShowRisksCommand } from './showRisks';

// src/commands/refreshContext.ts
import * as vscode from 'vscode';
import { ContextProvider } from '../providers';
import * as logger from '../logger';

/**
 * Creates and registers the refresh command for ContextCore
 * @param contextProvider - The context provider instance
 * @returns Disposable command registration
 */
export function createRefreshCommand(contextProvider: ContextProvider): vscode.Disposable {
  return vscode.commands.registerCommand('contextcore.refresh', async () => {
    try {
      logger.info('Refreshing ContextCore data...');
      contextProvider.invalidateCache();
      await contextProvider.refresh();
      vscode.window.showInformationMessage('ContextCore: Data refreshed successfully');
      logger.info('ContextCore data refreshed successfully');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      logger.error('Failed to refresh ContextCore data', error);
      vscode.window.showErrorMessage(`ContextCore: Failed to refresh data - ${message}`);
    }
  });
}

// src/commands/showImpact.ts
import * as vscode from 'vscode';
import { ContextMapper } from '../mapping';
import { runContextCoreCommand } from '../utils/cliRunner';
import * as logger from '../logger';

/**
 * Creates and registers the show impact command for ContextCore
 * @param contextMapper - The context mapper instance
 * @returns Disposable command registration
 */
export function createShowImpactCommand(contextMapper: ContextMapper): vscode.Disposable {
  return vscode.commands.registerCommand('contextcore.showImpact', async () => {
    try {
      logger.info('Analyzing project impact...');
      const currentProject = await contextMapper.getCurrentProject();
      if (!currentProject) {
        vscode.window.showWarningMessage('ContextCore: No active project found');
        return;
      }

      const command = `graph impact --project ${currentProject.id}`;
      const result = await runContextCoreCommand(command);
      
      const outputChannel = vscode.window.createOutputChannel('ContextCore Impact');
      outputChannel.clear();
      outputChannel.appendLine(`Impact Analysis for Project: ${currentProject.name}`);
      outputChannel.appendLine('='.repeat(50));
      outputChannel.appendLine(result);
      outputChannel.show();
      
      logger.info(`Impact analysis completed for project: ${currentProject.id}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      logger.error('Failed to analyze impact', error);
      vscode.window.showErrorMessage(`ContextCore: Failed to analyze impact - ${message}`);
    }
  });
}

// src/commands/openDashboard.ts
import * as vscode from 'vscode';
import { ContextMapper } from '../mapping';
import { getConfig } from '../config';
import * as logger from '../logger';

/**
 * Creates and registers the open dashboard command for ContextCore
 * @param contextMapper - The context mapper instance
 * @returns Disposable command registration
 */
export function createOpenDashboardCommand(contextMapper: ContextMapper): vscode.Disposable {
  return vscode.commands.registerCommand('contextcore.openDashboard', async () => {
    try {
      logger.info('Opening ContextCore dashboard...');
      const currentProject = await contextMapper.getCurrentProject();
      if (!currentProject) {
        vscode.window.showWarningMessage('ContextCore: No active project found');
        return;
      }

      const config = getConfig();
      const grafanaUrl = config.grafanaUrl;
      if (!grafanaUrl) {
        vscode.window.showErrorMessage('ContextCore: Grafana URL not configured');
        return;
      }

      const projectId = encodeURIComponent(currentProject.id);
      const dashboardUrl = `${grafanaUrl}/d/contextcore-project?var-project=${projectId}`;
      
      await vscode.env.openExternal(vscode.Uri.parse(dashboardUrl));
      logger.info(`Dashboard opened for project: ${currentProject.id}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      logger.error('Failed to open dashboard', error);
      vscode.window.showErrorMessage(`ContextCore: Failed to open dashboard - ${message}`);
    }
  });
}

// src/commands/showRisks.ts
import * as vscode from 'vscode';
import { ContextMapper, Risk } from '../mapping';
import * as logger from '../logger';

interface RiskItem extends vscode.QuickPickItem {
  priority: string;
  component: string;
  risk: Risk | null;
}

/**
 * Creates and registers the show risks command for ContextCore
 * @param contextMapper - The context mapper instance
 * @returns Disposable command registration
 */
export function createShowRisksCommand(contextMapper: ContextMapper): vscode.Disposable {
  return vscode.commands.registerCommand('contextcore.showRisks', async () => {
    try {
      logger.info('Loading project risks...');
      const currentProject = await contextMapper.getCurrentProject();
      if (!currentProject) {
        vscode.window.showWarningMessage('ContextCore: No active project found');
        return;
      }

      const risks = await contextMapper.getProjectRisks(currentProject.id);
      if (!risks || risks.length === 0) {
        vscode.window.showInformationMessage('ContextCore: No risks found for current project');
        return;
      }

      const priorityOrder = ['P1', 'P2', 'P3', 'P4'];
      const groupedItems: RiskItem[] = [];

      for (const priority of priorityOrder) {
        const priorityRisks = risks.filter(risk => risk.priority === priority);
        if (priorityRisks.length > 0) {
          // Add separator for priority group
          groupedItems.push({
            label: `${priority} Risks (${priorityRisks.length})`,
            kind: vscode.QuickPickItemKind.Separator,
            priority,
            component: '',
            risk: null
          });

          // Add individual risks
          priorityRisks.forEach(risk => {
            groupedItems.push({
              label: `$(warning) ${risk.title}`,
              description: risk.component,
              detail: risk.description,
              priority: risk.priority,
              component: risk.component,
              risk
            });
          });
        }
      }

      const selected = await vscode.window.showQuickPick(groupedItems, {
        placeHolder: 'Select a risk to view details',
        matchOnDescription: true,
        matchOnDetail: true
      });

      if (selected?.risk) {
        const risk = selected.risk;
        const message = `Risk: ${risk.title}\n\nComponent: ${risk.component}\nPriority: ${risk.priority}\n\nDescription: ${risk.description}\n\nMitigation: ${risk.mitigation || 'Not specified'}`;

        const action = await vscode.window.showInformationMessage(
          message,
          { modal: true },
          'View in Dashboard',
          'Close'
        );

        if (action === 'View in Dashboard') {
          await vscode.commands.executeCommand('contextcore.openDashboard');
        }
      }

      logger.info(`Displayed ${risks.length} risks for project: ${currentProject.id}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      logger.error('Failed to show risks', error);
      vscode.window.showErrorMessage(`ContextCore: Failed to load risks - ${message}`);
    }
  });
}

// src/utils/cliRunner.ts
import { exec } from 'child_process';
import { promisify } from 'util';
import * as logger from '../logger';

const execAsync = promisify(exec);

interface CliOptions {
  timeout?: number;
  maxBuffer?: number;
  cwd?: string;
}

/**
 * Executes a ContextCore CLI command
 * @param command - The command to execute (without 'contextcore' prefix)
 * @param options - Additional execution options
 * @returns Promise resolving to command output
 */
export async function runContextCoreCommand(
  command: string,
  options: CliOptions = {}
): Promise<string> {
  const {
    timeout = 30000,
    maxBuffer = 1024 * 1024 * 10, // 10MB
    cwd = process.cwd()
  } = options;

  const fullCommand = `contextcore ${command}`;

  try {
    logger.info(`Executing CLI command: ${fullCommand}`);
    const { stdout, stderr } = await execAsync(fullCommand, {
      timeout,
      maxBuffer,
      cwd,
      env: {
        ...process.env,
        CONTEXTCORE_OUTPUT_FORMAT: 'json'
      }
    });

    if (stderr && stderr.trim()) {
      logger.warn(`CLI command stderr: ${stderr}`);
    }

    const result = stdout.trim();
    logger.info(`CLI command completed successfully, output length: ${result.length}`);
    return result;
  } catch (error: unknown) {
    let errorMessage = 'Unknown error executing CLI command';

    if (error && typeof error === 'object') {
      const execError = error as { code?: string; stderr?: string };
      
      if (execError.code === 'ETIMEDOUT') {
        errorMessage = `Command timed out after ${timeout}ms`;
      } else if (execError.code === 'ENOENT') {
        errorMessage = 'ContextCore CLI not found. Please ensure it is installed and in PATH';
      } else if (execError.stderr) {
        errorMessage = `CLI error: ${execError.stderr.trim()}`;
      }
    }

    logger.error(`CLI command failed: ${errorMessage}`, error);
    throw new Error(errorMessage);
  }
}

// src/extension.ts
import * as vscode from 'vscode';
import * as logger from './logger';
import { ContextProvider } from './providers';
import { ContextMapper } from './mapping';
import { ContextStatusBar } from './ui/statusBar';
import { ProjectTreeProvider } from './ui/sidePanel';
import { DecorationProvider } from './ui/decorations';
import {
  createRefreshCommand,
  createShowImpactCommand,
  createOpenDashboardCommand,
  createShowRisksCommand
} from './commands';

/**
 * Activates the ContextCore extension
 * @param context - VSCode extension context
 */
export async function activate(context: vscode.ExtensionContext): Promise<void> {
  try {
    // Initialize logger
    logger.info('ContextCore extension activating...');

    // Create and initialize ContextProvider
    const contextProvider = new ContextProvider();
    await contextProvider.initialize();
    logger.info('ContextProvider initialized');

    // Create and initialize ContextMapper
    const contextMapper = new ContextMapper(contextProvider);
    await contextMapper.initialize();
    logger.info('ContextMapper initialized');

    // Create UI components
    const statusBar = new ContextStatusBar(contextMapper);
    context.subscriptions.push(statusBar);

    const treeProvider = new ProjectTreeProvider(contextMapper);
    const treeView = vscode.window.registerTreeDataProvider('contextcore.projectView', treeProvider);
    context.subscriptions.push(treeView);

    const decorationProvider = new DecorationProvider(contextMapper);
    context.subscriptions.push(decorationProvider);

    // Register commands
    context.subscriptions.push(createRefreshCommand(contextProvider));
    context.subscriptions.push(createShowImpactCommand(contextMapper));
    context.subscriptions.push(createOpenDashboardCommand(contextMapper));
    context.subscriptions.push(createShowRisksCommand(contextMapper));

    logger.info('ContextCore extension activated');
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    logger.error('Failed to activate ContextCore extension', error);
    vscode.window.showErrorMessage(`ContextCore: Activation failed - ${message}`);
    throw error; // Re-throw to ensure extension fails to activate if critical error
  }
}

/**
 * Deactivates the ContextCore extension
 * Cleanup is handled automatically by disposables in context.subscriptions
 */
export function deactivate(): void {
  logger.info('ContextCore extension deactivated');
}
