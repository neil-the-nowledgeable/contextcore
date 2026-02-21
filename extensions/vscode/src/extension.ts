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
  createShowRisksCommand,
  createManifestValidateCommand,
  createManifestShowCommand,
  createManifestFixCommand
} from './commands';

/**
 * Activates the ContextCore extension
 * @param context - VSCode extension context
 */
export async function activate(context: vscode.ExtensionContext): Promise<void> {
  try {
    // Initialize logger
    logger.initialize();
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
    context.subscriptions.push(createManifestValidateCommand());
    context.subscriptions.push(createManifestShowCommand());
    context.subscriptions.push(createManifestFixCommand());

    // Register show context details command
    context.subscriptions.push(
      vscode.commands.registerCommand('contextCore.showContextDetails', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
          vscode.window.showWarningMessage('ContextCore: No active editor');
          return;
        }

        const ctx = contextMapper.getContextForFile(editor.document.uri.fsPath);
        if (!ctx) {
          vscode.window.showWarningMessage('ContextCore: No context found for this file');
          return;
        }

        const details = [
          `Project ID: ${ctx.projectId}`,
          `Criticality: ${ctx.criticality}`,
          ctx.owner ? `Owner: ${ctx.owner}` : null,
          ctx.risks ? `Risks: ${ctx.risks.length} identified` : null
        ].filter(Boolean).join('\n');

        vscode.window.showInformationMessage(details, { modal: true });
      })
    );

    // Add provider to subscriptions for cleanup
    context.subscriptions.push(contextProvider);
    context.subscriptions.push(contextMapper);

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
  logger.dispose();
}
