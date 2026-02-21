import * as vscode from 'vscode';
import { runContextCoreCommand } from '../utils/cliRunner';
import * as logger from '../logger';

/**
 * Creates and registers the manifest fix command.
 * Runs a dry-run first, shows the user what would change, then applies on confirmation.
 */
export function createManifestFixCommand(): vscode.Disposable {
  return vscode.commands.registerCommand('contextcore.manifestFix', async () => {
    try {
      logger.info('Running manifest fix (dry-run)...');
      const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
      if (!workspaceFolder) {
        vscode.window.showWarningMessage('ContextCore: No workspace folder open');
        return;
      }

      const cwd = workspaceFolder.uri.fsPath;

      // Dry-run first
      const dryRunOutput = await runContextCoreCommand(
        'manifest fix --path .contextcore.yaml --dry-run',
        { cwd }
      );

      if (!dryRunOutput.trim()) {
        vscode.window.showInformationMessage('ContextCore: No fixes needed');
        return;
      }

      const outputChannel = vscode.window.createOutputChannel('ContextCore');
      outputChannel.clear();
      outputChannel.appendLine('--- Manifest Fix (Dry Run) ---');
      outputChannel.appendLine(dryRunOutput);
      outputChannel.show();

      const choice = await vscode.window.showInformationMessage(
        'ContextCore: Apply the proposed manifest fixes?',
        'Apply',
        'Cancel'
      );

      if (choice !== 'Apply') {
        logger.info('Manifest fix cancelled by user');
        return;
      }

      const applyOutput = await runContextCoreCommand(
        'manifest fix --path .contextcore.yaml',
        { cwd }
      );

      outputChannel.appendLine('');
      outputChannel.appendLine('--- Applied ---');
      outputChannel.appendLine(applyOutput);
      outputChannel.show();

      vscode.window.showInformationMessage('ContextCore: Manifest fixes applied');
      logger.info('Manifest fix applied');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      logger.error('Manifest fix failed', error);
      vscode.window.showErrorMessage(`ContextCore: Manifest fix failed - ${message}`);
    }
  });
}
