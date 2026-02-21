import * as vscode from 'vscode';
import { runContextCoreCommand } from '../utils/cliRunner';
import * as logger from '../logger';

/**
 * Creates and registers the manifest show command.
 * Runs `contextcore manifest show` and displays the summary.
 */
export function createManifestShowCommand(): vscode.Disposable {
  return vscode.commands.registerCommand('contextcore.manifestShow', async () => {
    try {
      logger.info('Running manifest show...');
      const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
      if (!workspaceFolder) {
        vscode.window.showWarningMessage('ContextCore: No workspace folder open');
        return;
      }

      const output = await runContextCoreCommand(
        'manifest show --path .contextcore.yaml --format summary',
        { cwd: workspaceFolder.uri.fsPath }
      );

      const outputChannel = vscode.window.createOutputChannel('ContextCore');
      outputChannel.clear();
      outputChannel.appendLine('--- Manifest Summary ---');
      outputChannel.appendLine(output);
      outputChannel.show();

      logger.info('Manifest show complete');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      logger.error('Manifest show failed', error);
      vscode.window.showErrorMessage(`ContextCore: Failed to show manifest - ${message}`);
    }
  });
}
