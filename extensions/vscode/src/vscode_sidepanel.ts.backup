// File: src/ui/sidePanel/contextTreeItem.ts
import * as vscode from 'vscode';

/**
 * Enum defining the types of tree items in the project context tree
 */
export enum TreeItemType {
  Project = 'project',
  Section = 'section', 
  Risk = 'risk',
  Requirement = 'requirement',
  Target = 'target',
  Property = 'property'
}

/**
 * Tree item representing nodes in the project context tree view
 */
export class ContextTreeItem extends vscode.TreeItem {
  /**
   * Creates a new context tree item
   * @param label Display label for the item
   * @param collapsibleState Whether the item can be expanded/collapsed
   * @param type The type of tree item
   * @param value Optional value to display
   * @param priority Optional priority for risk items
   * @param count Optional count for section badges
   */
  constructor(
    public readonly label: string,
    public readonly collapsibleState: vscode.TreeItemCollapsibleState,
    public readonly type: TreeItemType,
    public readonly value?: string,
    public readonly priority?: string,
    public readonly count?: number
  ) {
    super(label, collapsibleState);
    
    this.contextValue = `contextCore.${type}`;
    this.tooltip = this.createTooltip();
    this.iconPath = this.getIcon();
    this.description = this.createDescription();
  }

  /**
   * Creates tooltip text for the tree item
   */
  private createTooltip(): string {
    if (this.value) {
      return `${this.label}: ${this.value}`;
    }
    if (this.count !== undefined) {
      return `${this.label} (${this.count} items)`;
    }
    return this.label;
  }

  /**
   * Creates description text shown after the label
   */
  private createDescription(): string | undefined {
    if (this.count !== undefined) {
      return `(${this.count})`;
    }
    return this.value;
  }

  /**
   * Gets the appropriate icon for the tree item type
   */
  private getIcon(): vscode.ThemeIcon {
    switch (this.type) {
      case TreeItemType.Project:
        return new vscode.ThemeIcon('package');
      case TreeItemType.Section:
        return this.getSectionIcon();
      case TreeItemType.Risk:
        return this.getPriorityIcon(this.priority || 'P4');
      case TreeItemType.Requirement:
        return new vscode.ThemeIcon('graph');
      case TreeItemType.Target:
        return new vscode.ThemeIcon('symbol-class');
      case TreeItemType.Property:
        return new vscode.ThemeIcon('key');
      default:
        return new vscode.ThemeIcon('circle-outline');
    }
  }

  /**
   * Gets section-specific icons based on label
   */
  private getSectionIcon(): vscode.ThemeIcon {
    switch (this.label.toLowerCase().split(' ')[0]) {
      case 'business':
        return new vscode.ThemeIcon('organization');
      case 'risks':
        return new vscode.ThemeIcon('warning');
      case 'requirements':
        return new vscode.ThemeIcon('graph');
      case 'targets':
        return new vscode.ThemeIcon('symbol-class');
      default:
        return new vscode.ThemeIcon('folder');
    }
  }

  /**
   * Gets priority-based icon with color for risk items
   */
  private getPriorityIcon(priority: string): vscode.ThemeIcon {
    switch (priority) {
      case 'P1':
        return new vscode.ThemeIcon('error', new vscode.ThemeColor('errorForeground'));
      case 'P2':
        return new vscode.ThemeIcon('warning', new vscode.ThemeColor('editorWarning.foreground'));
      case 'P3':
        return new vscode.ThemeIcon('info', new vscode.ThemeColor('editorInfo.foreground'));
      case 'P4':
        return new vscode.ThemeIcon('circle-outline', new vscode.ThemeColor('editorInfo.foreground'));
      default:
        return new vscode.ThemeIcon('circle-outline');
    }
  }
}


// File: src/ui/sidePanel/projectTreeProvider.ts
import * as vscode from 'vscode';
import { ContextTreeItem, TreeItemType } from './contextTreeItem';
import { ContextMapper } from '../../contextMapper';

/**
 * Tree data provider for the project context side panel
 */
export class ProjectTreeProvider implements vscode.TreeDataProvider<ContextTreeItem>, vscode.Disposable {
  private _onDidChangeTreeData: vscode.EventEmitter<ContextTreeItem | undefined>;
  public readonly onDidChangeTreeData: vscode.Event<ContextTreeItem | undefined>;
  private disposables: vscode.Disposable[] = [];
  private currentProjectContexts: Map<string, any> = new Map();

  /**
   * Creates a new project tree provider
   * @param contextMapper The context mapper instance
   */
  constructor(private contextMapper: ContextMapper) {
    this._onDidChangeTreeData = new vscode.EventEmitter<ContextTreeItem | undefined>();
    this.onDidChangeTreeData = this._onDidChangeTreeData.event;

    // Subscribe to context changes
    if (this.contextMapper.onContextChanged) {
      this.disposables.push(
        this.contextMapper.onContextChanged(() => {
          this.refresh();
        })
      );
    }
  }

  /**
   * Gets the tree item representation for an element
   */
  getTreeItem(element: ContextTreeItem): vscode.TreeItem {
    return element;
  }

  /**
   * Gets children for a tree element
   */
  async getChildren(element?: ContextTreeItem): Promise<ContextTreeItem[]> {
    try {
      if (!element) {
        return await this.getRootNodes();
      }

      return await this.getElementChildren(element);
    } catch (error) {
      console.error('Error getting tree children:', error);
      return [new ContextTreeItem(
        'Error loading data',
        vscode.TreeItemCollapsibleState.None,
        TreeItemType.Property
      )];
    }
  }

  /**
   * Gets root level nodes (projects)
   */
  private async getRootNodes(): Promise<ContextTreeItem[]> {
    const projectContexts = await this.contextMapper.getProjectContexts();
    
    if (!projectContexts || projectContexts.length === 0) {
      return [new ContextTreeItem(
        'No projects found',
        vscode.TreeItemCollapsibleState.None,
        TreeItemType.Project
      )];
    }

    // Cache project contexts for later use
    projectContexts.forEach(project => {
      this.currentProjectContexts.set(project.name, project);
    });

    return projectContexts.map(project => 
      new ContextTreeItem(
        project.name,
        vscode.TreeItemCollapsibleState.Collapsed,
        TreeItemType.Project
      )
    );
  }

  /**
   * Gets children for a specific element
   */
  private async getElementChildren(element: ContextTreeItem): Promise<ContextTreeItem[]> {
    switch (element.type) {
      case TreeItemType.Project:
        return this.createProjectSections(element.label);
      case TreeItemType.Section:
        return this.createSectionChildren(element);
      default:
        return [];
    }
  }

  /**
   * Creates section nodes for a project
   */
  private createProjectSections(projectName: string): ContextTreeItem[] {
    const project = this.currentProjectContexts.get(projectName);
    
    const sections: ContextTreeItem[] = [
      new ContextTreeItem('Business', vscode.TreeItemCollapsibleState.Collapsed, TreeItemType.Section),
    ];

    // Add Risks section with count if available
    const riskCount = project?.risks?.length || 0;
    sections.push(new ContextTreeItem(
      'Risks',
      vscode.TreeItemCollapsibleState.Collapsed,
      TreeItemType.Section,
      undefined,
      undefined,
      riskCount
    ));

    sections.push(
      new ContextTreeItem('Requirements', vscode.TreeItemCollapsibleState.Collapsed, TreeItemType.Section),
      new ContextTreeItem('Targets', vscode.TreeItemCollapsibleState.Collapsed, TreeItemType.Section)
    );

    return sections;
  }

  /**
   * Creates children for section nodes
   */
  private createSectionChildren(element: ContextTreeItem): ContextTreeItem[] {
    const sectionName = element.label.split(' ')[0]; // Remove count suffix
    
    switch (sectionName) {
      case 'Business':
        return this.createBusinessProperties();
      case 'Risks':
        return this.createRiskItems();
      case 'Requirements':
        return this.createRequirementItems();
      case 'Targets':
        return this.createTargetItems();
      default:
        return [];
    }
  }

  /**
   * Creates business property items
   */
  private createBusinessProperties(): ContextTreeItem[] {
    // Get business properties from current project context
    const properties = [
      { key: 'Criticality', value: 'High' },
      { key: 'Owner', value: 'Engineering Team' },
      { key: 'Value', value: 'Core Service' }
    ];

    return properties.map(prop =>
      new ContextTreeItem(
        prop.key,
        vscode.TreeItemCollapsibleState.None,
        TreeItemType.Property,
        prop.value
      )
    );
  }

  /**
   * Creates risk items with priority icons
   */
  private createRiskItems(): ContextTreeItem[] {
    // Sample risks - in real implementation, get from context
    const risks = [
      { name: 'Database Failure', priority: 'P1', description: 'Primary database unavailable' },
      { name: 'Network Latency', priority: 'P2', description: 'High network latency issues' },
      { name: 'Cache Invalidation', priority: 'P3', description: 'Cache consistency problems' }
    ];

    return risks.map(risk =>
      new ContextTreeItem(
        risk.name,
        vscode.TreeItemCollapsibleState.None,
        TreeItemType.Risk,
        risk.description,
        risk.priority
      )
    );
  }

  /**
   * Creates requirement items
   */
  private createRequirementItems(): ContextTreeItem[] {
    const requirements = [
      { name: 'Availability', value: '99.9%' },
      { name: 'Latency P99', value: '<100ms' },
      { name: 'Throughput', value: '1000 RPS' }
    ];

    return requirements.map(req =>
      new ContextTreeItem(
        req.name,
        vscode.TreeItemCollapsibleState.None,
        TreeItemType.Requirement,
        req.value
      )
    );
  }

  /**
   * Creates target items
   */
  private createTargetItems(): ContextTreeItem[] {
    const targets = [
      { name: 'Production Deployment', kind: 'kubernetes' },
      { name: 'Load Balancer', kind: 'service' },
      { name: 'Database Instance', kind: 'database' }
    ];

    return targets.map(target =>
      new ContextTreeItem(
        target.name,
        vscode.TreeItemCollapsibleState.None,
        TreeItemType.Target,
        target.kind
      )
    );
  }

  /**
   * Refreshes the tree view
   */
  refresh(): void {
    this._onDidChangeTreeData.fire(undefined);
  }

  /**
   * Disposes of resources
   */
  dispose(): void {
    this._onDidChangeTreeData.dispose();
    this.disposables.forEach(d => d.dispose());
    this.disposables = [];
  }
}


// File: src/extension.ts (registration example)
import * as vscode from 'vscode';
import { ProjectTreeProvider } from './ui/sidePanel/projectTreeProvider';
import { ContextMapper } from './contextMapper';

export function activate(context: vscode.ExtensionContext) {
  try {
    // Initialize context mapper
    const contextMapper = new ContextMapper();
    
    // Create and register tree provider
    const treeProvider = new ProjectTreeProvider(contextMapper);
    const treeView = vscode.window.createTreeView('contextCore.projectTree', {
      treeDataProvider: treeProvider,
      showCollapseAll: true
    });

    // Register disposables
    context.subscriptions.push(
      treeProvider,
      treeView,
      vscode.window.registerTreeDataProvider('contextCore.projectTree', treeProvider)
    );

    // Optional: Add refresh command
    context.subscriptions.push(
      vscode.commands.registerCommand('contextCore.refreshProjectTree', () => {
        treeProvider.refresh();
      })
    );

  } catch (error) {
    console.error('Failed to activate project tree provider:', error);
    vscode.window.showErrorMessage('Failed to initialize project tree view');
  }
}
