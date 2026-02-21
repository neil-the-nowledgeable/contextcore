import * as vscode from 'vscode';
import { ContextTreeItem, TreeItemType } from './contextTreeItem';
import { ContextMapper } from '../../mapping';

/**
 * Flattened context for tree display
 */
interface FlattenedContext {
  projectId: string;
  criticality: string;
  owner?: string;
  risks?: { id?: string; description?: string; severity?: string }[];
  requirements?: {
    targets?: { metric: string; threshold: string }[];
    description?: string;
  };
  ecosystem?: {
    packages?: { name: string; animal: string; purpose: string; status: string }[];
  };
}

/**
 * Provides tree data for the context side panel
 */
export class ProjectTreeProvider implements vscode.TreeDataProvider<ContextTreeItem>, vscode.Disposable {
  private _onDidChangeTreeData: vscode.EventEmitter<ContextTreeItem | undefined | null | void> =
    new vscode.EventEmitter<ContextTreeItem | undefined | null | void>();
  readonly onDidChangeTreeData: vscode.Event<ContextTreeItem | undefined | null | void> =
    this._onDidChangeTreeData.event;

  private disposables: vscode.Disposable[] = [];

  constructor(private contextMapper: ContextMapper) {
    this.disposables.push(this._onDidChangeTreeData);

    // Listen for active editor changes
    this.disposables.push(
      vscode.window.onDidChangeActiveTextEditor(() => {
        this.refresh();
      })
    );
  }

  getTreeItem(element: ContextTreeItem): vscode.TreeItem {
    return element;
  }

  async getChildren(element?: ContextTreeItem): Promise<ContextTreeItem[]> {
    try {
      if (!element) {
        return this.getRootElements();
      }

      switch (element.type) {
        case TreeItemType.Project:
          return this.getProjectChildren(element);
        case TreeItemType.Section:
          return this.getSectionChildren(element);
        default:
          return [];
      }
    } catch (error) {
      console.error('Error getting tree children:', error);
      return [];
    }
  }

  private getRootElements(): ContextTreeItem[] {
    const activeEditor = vscode.window.activeTextEditor;
    if (!activeEditor) {
      return [new ContextTreeItem(
        'No active file',
        vscode.TreeItemCollapsibleState.None,
        TreeItemType.Property
      )];
    }

    const context = this.contextMapper.getContextForFile(activeEditor.document.uri.fsPath) as FlattenedContext | undefined;
    if (!context) {
      return [new ContextTreeItem(
        'No context available',
        vscode.TreeItemCollapsibleState.None,
        TreeItemType.Property
      )];
    }

    return [new ContextTreeItem(
      context.projectId,
      vscode.TreeItemCollapsibleState.Expanded,
      TreeItemType.Project,
      context
    )];
  }

  private getProjectChildren(element: ContextTreeItem): ContextTreeItem[] {
    const context = element.value as FlattenedContext;
    const children: ContextTreeItem[] = [];

    // Project properties
    children.push(new ContextTreeItem(
      `Criticality: ${context.criticality}`,
      vscode.TreeItemCollapsibleState.None,
      TreeItemType.Property,
      context.criticality
    ));

    if (context.owner) {
      children.push(new ContextTreeItem(
        `Owner: ${context.owner}`,
        vscode.TreeItemCollapsibleState.None,
        TreeItemType.Property,
        context.owner
      ));
    }

    // Risks section
    if (context.risks && context.risks.length > 0) {
      children.push(new ContextTreeItem(
        'Risks',
        vscode.TreeItemCollapsibleState.Collapsed,
        TreeItemType.Section,
        context.risks,
        undefined,
        context.risks.length
      ));
    }

    // Requirements section
    if (context.requirements) {
      children.push(new ContextTreeItem(
        'Requirements',
        vscode.TreeItemCollapsibleState.Collapsed,
        TreeItemType.Section,
        context.requirements
      ));
    }

    // Expansion Packs section
    const packages = context.ecosystem?.packages;
    if (packages && packages.length > 0) {
      children.push(new ContextTreeItem(
        'Expansion Packs',
        vscode.TreeItemCollapsibleState.Collapsed,
        TreeItemType.Section,
        packages,
        undefined,
        packages.length
      ));
    }

    return children;
  }

  private getSectionChildren(element: ContextTreeItem): ContextTreeItem[] {
    if (element.label === 'Risks') {
      const risks = element.value as { id?: string; description?: string; severity?: string }[];
      return risks.map((risk) =>
        new ContextTreeItem(
          risk.description || risk.id || 'Risk',
          vscode.TreeItemCollapsibleState.None,
          TreeItemType.Risk,
          risk,
          risk.severity
        )
      );
    }

    if (element.label === 'Requirements') {
      const requirements = element.value as { targets?: { metric: string; threshold: string }[] };
      if (requirements.targets) {
        return requirements.targets.map((target) =>
          new ContextTreeItem(
            `${target.metric}: ${target.threshold}`,
            vscode.TreeItemCollapsibleState.None,
            TreeItemType.Target,
            target
          )
        );
      }
    }

    if (element.label === 'Expansion Packs') {
      const packages = element.value as { name: string; animal: string; purpose: string; status: string }[];
      return packages.map((pkg) =>
        new ContextTreeItem(
          `${pkg.animal} (${pkg.name})`,
          vscode.TreeItemCollapsibleState.None,
          TreeItemType.ExpansionPack,
          pkg,
          pkg.status
        )
      );
    }

    return [];
  }

  public refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  public dispose(): void {
    this.disposables.forEach(d => d.dispose());
  }
}
