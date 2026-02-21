import * as vscode from 'vscode';
import { runContextCoreCommand } from '../utils/cliRunner';
import * as logger from '../logger';

/**
 * Creates and registers the manifest validate command.
 * Runs `contextcore manifest validate` on the workspace .contextcore.yaml.
 */
export function createManifestValidateCommand(): vscode.Disposable {
  return vscode.commands.registerCommand('contextcore.manifestValidate', async () => {
    try {
      logger.info('Running manifest validate...');
      const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
      if (!workspaceFolder) {
        vscode.window.showWarningMessage('ContextCore: No workspace folder open');
        return;
      }

      const output = await runContextCoreCommand(
        'manifest validate --path .contextcore.yaml',
        { cwd: workspaceFolder.uri.fsPath }
      );

      const outputChannel = vscode.window.createOutputChannel('ContextCore');
      outputChannel.clear();
      outputChannel.appendLine('--- Manifest Validation ---');
      outputChannel.appendLine(output);
      outputChannel.show();

      vscode.window.showInformationMessage('ContextCore: Manifest validation complete');
      logger.info('Manifest validation complete');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      logger.error('Manifest validation failed', error);
      vscode.window.showErrorMessage(`ContextCore: Manifest validation failed - ${message}`);
    }
  });
}
