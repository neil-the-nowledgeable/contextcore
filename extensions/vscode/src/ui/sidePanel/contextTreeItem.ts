import * as vscode from 'vscode';

export enum TreeItemType {
  Project = 'project',
  Section = 'section',
  Risk = 'risk',
  Requirement = 'requirement',
  Target = 'target',
  Property = 'property',
  ExpansionPack = 'expansionPack'
}

/**
 * Tree item for displaying context information in the side panel
 */
export class ContextTreeItem extends vscode.TreeItem {
  constructor(
    label: string,
    collapsibleState: vscode.TreeItemCollapsibleState,
    public readonly type: TreeItemType,
    public readonly value?: unknown,
    public readonly priority?: string,
    public readonly count?: number
  ) {
    super(label, collapsibleState);

    this.iconPath = this.getIcon();
    this.contextValue = this.type;

    if (count !== undefined && count > 0) {
      this.description = `(${count})`;
    }

    if (value !== undefined && typeof value === 'string') {
      this.tooltip = value;
    }
  }

  /**
   * Gets the appropriate icon based on type and priority
   */
  private getIcon(): vscode.ThemeIcon {
    switch (this.type) {
      case TreeItemType.Project:
        return new vscode.ThemeIcon('project');
      case TreeItemType.Section:
        return new vscode.ThemeIcon('folder');
      case TreeItemType.Risk:
        return this.getRiskIcon();
      case TreeItemType.Requirement:
        return new vscode.ThemeIcon('checklist');
      case TreeItemType.Target:
        return new vscode.ThemeIcon('target');
      case TreeItemType.Property:
        return new vscode.ThemeIcon('symbol-property');
      case TreeItemType.ExpansionPack:
        return new vscode.ThemeIcon('package');
      default:
        return new vscode.ThemeIcon('circle-outline');
    }
  }

  private getRiskIcon(): vscode.ThemeIcon {
    if (this.priority) {
      switch (this.priority.toLowerCase()) {
        case 'critical':
          return new vscode.ThemeIcon('error', new vscode.ThemeColor('errorForeground'));
        case 'high':
          return new vscode.ThemeIcon('warning', new vscode.ThemeColor('warningForeground'));
        case 'medium':
          return new vscode.ThemeIcon('info', new vscode.ThemeColor('foreground'));
        case 'low':
          return new vscode.ThemeIcon('circle-outline', new vscode.ThemeColor('descriptionForeground'));
        default:
          return new vscode.ThemeIcon('question');
      }
    }
    return new vscode.ThemeIcon('warning');
  }
}
