// src/ui/statusBar.ts

import * as vscode from 'vscode';
import { ContextMapper, ProjectContext } from '../context/ContextMapper';
import { buildTooltip } from './statusBarTooltip';

/**
 * Status bar component that displays project context and criticality information
 * for the currently active file in VSCode.
 */
export class ContextStatusBar implements vscode.Disposable {
  private statusBarItem: vscode.StatusBarItem;
  private disposables: vscode.Disposable[] = [];

  /**
   * Creates a new ContextStatusBar instance.
   * @param contextMapper - The context mapper service for retrieving project context
   */
  constructor(private readonly contextMapper: ContextMapper) {
    // Create status bar item with right alignment and high priority
    this.statusBarItem = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100
    );
    this.statusBarItem.command = 'contextcore.statusBarClick';

    // Register event listeners
    this.disposables.push(
      vscode.window.onDidChangeActiveTextEditor(
        (editor) => this.update(editor),
        this
      ),
      // Register the click command handler
      vscode.commands.registerCommand('contextcore.statusBarClick', () => this.handleStatusBarClick())
    );

    // Initialize with current active editor
    this.update(vscode.window.activeTextEditor);
    this.statusBarItem.show();
  }

  /**
   * Updates the status bar item based on the active editor.
   * @param editor - The currently active text editor
   */
  private async update(editor: vscode.TextEditor | undefined): Promise<void> {
    if (!editor) {
      this.statusBarItem.hide();
      return;
    }

    try {
      const context = await this.contextMapper.getContext(editor.document);
      this.updateStatusBarDisplay(context);
      this.statusBarItem.show();
    } catch (error) {
      this.showUnknownContext();
      console.error('Failed to retrieve project context:', error);
    }
  }

  /**
   * Updates the status bar item display with project context information.
   * @param context - The project context to display
   */
  private updateStatusBarDisplay(context: ProjectContext): void {
    const { icon, backgroundColor } = this.getCriticalityStyle(context.criticality);
    const displayText = this.formatProjectId(context.id);

    this.statusBarItem.text = `${icon} ${displayText}`;
    this.statusBarItem.backgroundColor = backgroundColor;
    this.statusBarItem.tooltip = buildTooltip(context);
  }

  /**
   * Gets the appropriate icon and background color for a criticality level.
   * @param criticality - The project criticality level
   * @returns Object containing icon and background color
   */
  private getCriticalityStyle(criticality: string): { icon: string; backgroundColor?: vscode.ThemeColor } {
    switch (criticality.toLowerCase()) {
      case 'critical':
        return {
          icon: '$(flame)',
          backgroundColor: new vscode.ThemeColor('statusBarItem.errorBackground')
        };
      case 'high':
        return {
          icon: '$(warning)',
          backgroundColor: new vscode.ThemeColor('statusBarItem.warningBackground')
        };
      case 'medium':
        return {
          icon: '$(info)',
          backgroundColor: undefined
        };
      case 'low':
        return {
          icon: '$(check)',
          backgroundColor: undefined
        };
      default:
        return {
          icon: '$(question)',
          backgroundColor: undefined
        };
    }
  }

  /**
   * Formats the project ID for display, truncating if necessary.
   * @param projectId - The project ID to format
   * @returns Formatted project ID string
   */
  private formatProjectId(projectId: string): string {
    return projectId.length > 20 
      ? `${projectId.substring(0, 20)}...` 
      : projectId;
  }

  /**
   * Shows unknown context state in the status bar.
   */
  private showUnknownContext(): void {
    this.statusBarItem.text = '$(question) Unknown';
    this.statusBarItem.tooltip = 'Unable to determine project context';
    this.statusBarItem.backgroundColor = undefined;
    this.statusBarItem.show();
  }

  /**
   * Handles status bar item click events by showing a quick pick menu.
   */
  private async handleStatusBarClick(): Promise<void> {
    const options: vscode.QuickPickItem[] = [
      {
        label: '$(eye) Show Full Context',
        description: 'View complete project information'
      },
      {
        label: '$(graph) Show Impact Analysis',
        description: 'Evaluate project impact'
      },
      {
        label: '$(link-external) Open in Grafana',
        description: 'View project dashboard'
      },
      {
        label: '$(warning) Show Risks',
        description: 'Display identified project risks'
      }
    ];

    const selected = await vscode.window.showQuickPick(options, {
      placeHolder: 'Choose an action for this project',
      matchOnDescription: true
    });

    if (selected) {
      await this.executeSelectedAction(selected.label);
    }
  }

  /**
   * Executes the command corresponding to the selected quick pick option.
   * @param selectedLabel - The label of the selected quick pick item
   */
  private async executeSelectedAction(selectedLabel: string): Promise<void> {
    const commandMap: Record<string, string> = {
      '$(eye) Show Full Context': 'contextcore.showFullContext',
      '$(graph) Show Impact Analysis': 'contextcore.showImpact',
      '$(link-external) Open in Grafana': 'contextcore.openDashboard',
      '$(warning) Show Risks': 'contextcore.showRisks'
    };

    const command = commandMap[selectedLabel];
    if (command) {
      try {
        await vscode.commands.executeCommand(command);
      } catch (error) {
        vscode.window.showErrorMessage(`Failed to execute action: ${error}`);
      }
    }
  }

  /**
   * Disposes of all resources and event listeners.
   */
  dispose(): void {
    this.statusBarItem.dispose();
    this.disposables.forEach(disposable => disposable.dispose());
    this.disposables.length = 0;
  }
}


// src/ui/statusBarTooltip.ts

import * as vscode from 'vscode';
import { ProjectContext } from '../context/ContextMapper';

/**
 * Builds a rich markdown tooltip for the status bar item containing project context details.
 * @param context - The project context to display in the tooltip
 * @returns A MarkdownString containing formatted project information
 */
export function buildTooltip(context: ProjectContext): vscode.MarkdownString {
  const tooltip = new vscode.MarkdownString();
  tooltip.isTrusted = true;
  
  // Header
  tooltip.appendMarkdown('## 📋 Project Context\n\n');
  
  // Core project information
  tooltip.appendMarkdown(`**Project ID:** \`${context.id}\`\n\n`);
  tooltip.appendMarkdown(`**Criticality:** ${getCriticalityEmoji(context.criticality)} ${context.criticality}\n\n`);
  tooltip.appendMarkdown(`**Owner:** ${context.owner || 'Not specified'}\n\n`);
  
  // Risk information
  const riskCount = context.risks?.length || 0;
  tooltip.appendMarkdown(`**Risks Identified:** ${riskCount}\n\n`);
  
  // Requirements summary
  if (context.requirementsSummary) {
    tooltip.appendMarkdown('**Requirements Summary:**\n\n');
    tooltip.appendMarkdown(`${context.requirementsSummary}\n\n`);
  }
  
  // Footer with action hint
  tooltip.appendMarkdown('---\n\n💡 *Click for more actions*');
  
  return tooltip;
}

/**
 * Gets an appropriate emoji for the criticality level.
 * @param criticality - The criticality level
 * @returns Emoji string representing the criticality
 */
function getCriticalityEmoji(criticality: string): string {
  switch (criticality.toLowerCase()) {
    case 'critical':
      return '🔥';
    case 'high':
      return '⚠️';
    case 'medium':
      return 'ℹ️';
    case 'low':
      return '✅';
    default:
      return '❓';
  }
}


// In extension.ts activate function
const statusBar = new ContextStatusBar(contextMapper);
context.subscriptions.push(statusBar);
