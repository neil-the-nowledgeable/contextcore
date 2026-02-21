import * as child_process from 'child_process';
import * as vscode from 'vscode';
import { ProjectContext } from '../types';

/**
 * Load project context from ContextCore CLI.
 * Executes 'contextcore manifest show --path .contextcore.yaml --format json' command.
 */
export async function loadFromCli(workspaceFolder: vscode.WorkspaceFolder): Promise<ProjectContext | undefined> {
    return new Promise<ProjectContext | undefined>((resolve) => {
        const command = 'contextcore manifest show --path .contextcore.yaml --format json';
        const options = {
            cwd: workspaceFolder.uri.fsPath,
            timeout: 10000 // 10 second timeout
        };

        child_process.exec(command, options, (error, stdout) => {
            if (error) {
                // Command failed - return undefined without throwing
                resolve(undefined);
                return;
            }

            try {
                const context = JSON.parse(stdout) as ProjectContext;
                resolve(context);
            } catch {
                // JSON parsing failed - return undefined
                resolve(undefined);
            }
        });
    });
}
