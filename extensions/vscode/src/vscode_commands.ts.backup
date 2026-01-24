// File: src/types/index.ts
export interface Risk {
  id: string;
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  impact: string;
  mitigation?: string;
}

export interface Project {
  id: string;
  name: string;
  path: string;
  risks: Risk[];
  dependencies: string[];
}

export interface ImpactResult {
  projectId: string;
  affectedProjects: string[];
  blastRadius: number;
  impactLevel: 'high' | 'medium' | 'low';
}

export interface ContextData {
  projects: Project[];
  currentProject?: Project;
}


// File: src/utils/cliRunner.ts
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

/**
 * Executes a contextcore CLI command and returns the result
 */
export async function runContextCoreCommand(command: string): Promise<string> {
  try {
    const { stdout, stderr } = await execAsync(command);
    if (stderr) {
      throw new Error(stderr);
    }
    return stdout.trim();
  } catch (error) {
    throw new Error(`CLI command failed: ${error.message}`);
  }
}


// File: src/contextProvider.ts
import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { promisify } from 'util';
import { ContextData, Project } from './types';

const readFileAsync = promisify(fs.readFile);
const existsAsync = promisify(fs.exists);

/**
 * Provides context data for the current workspace
 */
export class ContextProvider {
  private cache: Map<string, ContextData> = new Map();
  private readonly _onDidChangeContext = new vscode.EventEmitter<ContextData | undefined>();
  
  public readonly onDidChangeContext = this._onDidChangeContext.event;

  /**
   * Gets context data for the current workspace
   */
  async getContext(): Promise<ContextData | undefined> {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) {
      return undefined;
    }

    const cacheKey = workspaceFolder.uri.fsPath;
    if (this.cache.has(cacheKey)) {
      return this.cache.get(cacheKey);
    }

    const contextData = await this.loadContextData(workspaceFolder.uri.fsPath);
    if (contextData) {
      this.cache.set(cacheKey, contextData);
    }

    return contextData;
  }

  /**
   * Invalidates the cache for all workspaces
   */
  async invalidateCache(): Promise<void> {
    this.cache.clear();
  }

  /**
   * Refreshes context data and notifies listeners
   */
  async refresh(): Promise<void> {
    await this.invalidateCache();
    const contextData = await this.getContext();
    this._onDidChangeContext.fire(contextData);
  }

  /**
   * Loads context data from the workspace
   */
  private async loadContextData(workspacePath: string): Promise<ContextData | undefined> {
    try {
      const contextFilePath = path.join(workspacePath, '.contextcore', 'context.json');
      
      if (!(await existsAsync(contextFilePath))) {
        return undefined;
      }

      const contextFileContent = await readFileAsync(contextFilePath, 'utf-8');
      const contextData: ContextData = JSON.parse(contextFileContent);
      
      return contextData;
    } catch (error) {
      console.error('Failed to load context data:', error);
      return undefined;
    }
  }

  dispose(): void {
    this._onDidChangeContext.dispose();
    this.cache.clear();
  }
}


// File: src/contextMapper.ts
import * as vscode from 'vscode';
import { ContextProvider } from './contextProvider';
import { Project, Risk, ContextData } from './types';

/**
 * Maps context data and provides project-specific functionality
 */
export class ContextMapper {
  private contextData?: ContextData;

  constructor(private contextProvider: ContextProvider) {
    this.contextProvider.onDidChangeContext(this.onContextChanged, this);
  }

  /**
   * Initializes the context mapper
   */
  async initialize(): Promise<void> {
    this.contextData = await this.contextProvider.getContext();
  }

  /**
   * Gets the current active project based on the active editor
   */
  getCurrentProject(): Project | undefined {
    if (!this.contextData || !vscode.window.activeTextEditor) {
      return undefined;
    }

    const activeFilePath = vscode.window.activeTextEditor.document.uri.fsPath;
    
    // Find project that contains the active file
    return this.contextData.projects.find(project => 
      activeFilePath.startsWith(project.path)
    );
  }

  /**
   * Gets all projects in the current context
   */
  getProjects(): Project[] {
    return this.contextData?.projects ?? [];
  }

  /**
   * Gets risks for the current project
   */
  getRisks(): Risk[] {
    const currentProject = this.getCurrentProject();
    return currentProject?.risks ?? [];
  }

  /**
   * Gets risks for a specific project
   */
  getRisksForProject(projectId: string): Risk[] {
    const project = this.contextData?.projects.find(p => p.id === projectId);
    return project?.risks ?? [];
  }

  private onContextChanged(contextData?: ContextData): void {
    this.contextData = contextData;
  }

  dispose(): void {
    // Cleanup if needed
  }
}


// File: src/providers/projectTreeProvider.ts
import * as vscode from 'vscode';
import { ContextMapper } from '../contextMapper';
import { Project, Risk } from '../types';

export class ProjectTreeProvider implements vscode.TreeDataProvider<ProjectTreeItem> {
  private readonly _onDidChangeTreeData = new vscode.EventEmitter<ProjectTreeItem | undefined | null | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  constructor(private contextMapper: ContextMapper) {}

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: ProjectTreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: ProjectTreeItem): Thenable<ProjectTreeItem[]> {
    if (!element) {
      // Root level - return projects
      const projects = this.contextMapper.getProjects();
      return Promise.resolve(projects.map(project => new ProjectTreeItem(
        project.name,
        vscode.TreeItemCollapsibleState.Collapsed,
        'project',
        project
      )));
    } else if (element.contextValue === 'project' && element.project) {
      // Project level - return risks
      const risks = element.project.risks;
      return Promise.resolve(risks.map(risk => new ProjectTreeItem(
        `${risk.title} (${risk.priority})`,
        vscode.TreeItemCollapsibleState.None,
        'risk',
        undefined,
        risk
      )));
    }

    return Promise.resolve([]);
  }
}

class ProjectTreeItem extends vscode.TreeItem {
  constructor(
    public readonly label: string,
    public readonly collapsibleState: vscode.TreeItemCollapsibleState,
    public readonly contextValue: string,
    public readonly project?: Project,
    public readonly risk?: Risk
  ) {
    super(label, collapsibleState);

    if (contextValue === 'project') {
      this.iconPath = new vscode.ThemeIcon('folder');
      this.tooltip = `${this.label} - ${project?.path}`;
    } else if (contextValue === 'risk') {
      const iconName = risk?.priority === 'high' ? 'error' : 
                       risk?.priority === 'medium' ? 'warning' : 'info';
      this.iconPath = new vscode.ThemeIcon(iconName);
      this.tooltip = risk?.description;
    }
  }
}


// File: src/providers/statusBar.ts
import * as vscode from 'vscode';
import { ContextMapper } from '../contextMapper';

/**
 * Manages the status bar item for the current project context
 */
export class ContextStatusBar {
  private statusBarItem: vscode.StatusBarItem;

  constructor(private contextMapper: ContextMapper) {
    this.statusBarItem = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Left,
      100
    );
    this.statusBarItem.command = 'contextcore.showRisks';
    this.update();
  }

  /**
   * Updates the status bar with current project information
   */
  update(): void {
    const currentProject = this.contextMapper.getCurrentProject();
    
    if (currentProject) {
      const riskCount = currentProject.risks.length;
      const highRiskCount = currentProject.risks.filter(r => r.priority === 'high').length;
      
      this.statusBarItem.text = `$(project) ${currentProject.name}`;
      this.statusBarItem.tooltip = `Project: ${currentProject.name}\nRisks: ${riskCount} (${highRiskCount} high)`;
      this.statusBarItem.show();
    } else {
      this.statusBarItem.hide();
    }
  }

  dispose(): void {
    this.statusBarItem.dispose();
  }
}


// File: src/providers/decorationProvider.ts
import * as vscode from 'vscode';
import { ContextMapper } from '../contextMapper';

/**
 * Provides file decorations based on project context and risks
 */
export class DecorationProvider implements vscode.FileDecorationProvider {
  private readonly _onDidChangeFileDecorations = new vscode.EventEmitter<vscode.Uri | vscode.Uri[] | undefined>();
  readonly onDidChangeFileDecorations = this._onDidChangeFileDecorations.event;

  constructor(private contextMapper: ContextMapper) {}

  provideFileDecoration(uri: vscode.Uri): vscode.FileDecoration | undefined {
    const projects = this.contextMapper.getProjects();
    const project = projects.find(p => uri.fsPath.startsWith(p.path));
    
    if (project && project.risks.length > 0) {
      const highRiskCount = project.risks.filter(r => r.priority === 'high').length;
      
      if (highRiskCount > 0) {
        return {
          badge: highRiskCount.toString(),
          color: new vscode.ThemeColor('errorForeground'),
          tooltip: `${highRiskCount} high priority risks`
        };
      }
    }

    return undefined;
  }

  refresh(): void {
    this._onDidChangeFileDecorations.fire(undefined);
  }
}


// File: src/commands/refreshContext.ts
import * as vscode from 'vscode';
import { ContextProvider } from '../contextProvider';

/**
 * Creates the refresh context command
 */
export function createRefreshCommand(contextProvider: ContextProvider): vscode.Disposable {
  return vscode.commands.registerCommand('contextcore.refresh', async () => {
    try {
      await contextProvider.invalidateCache();
      await contextProvider.refresh();
      vscode.window.showInformationMessage('ContextCore: Context refreshed successfully');
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      vscode.window.showErrorMessage(`ContextCore: Failed to refresh context - ${errorMessage}`);
    }
  });
}


// File: src/commands/showImpact.ts
import * as vscode from 'vscode';
import { ContextMapper } from '../contextMapper';
import { runContextCoreCommand } from '../utils/cliRunner';
import { ImpactResult } from '../types';

/**
 * Creates the show impact command
 */
export function createShowImpactCommand(contextMapper: ContextMapper): vscode.Disposable {
  return vscode.commands.registerCommand('contextcore.showImpact', async () => {
    try {
      const currentProject = contextMapper.getCurrentProject();
      if (!currentProject) {
        vscode.window.showWarningMessage('ContextCore: No active project context found');
        return;
      }

      // Show progress while running analysis
      await vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: 'Analyzing project impact...',
        cancellable: false
      }, async () => {
        const command = `contextcore graph impact --project ${currentProject.id}`;
        const result = await runContextCoreCommand(command);
        
        const impactResult: ImpactResult = JSON.parse(result);
        
        // Create output channel to show detailed results
        const outputChannel = vscode.window.createOutputChannel('ContextCore Impact Analysis');
        outputChannel.clear();
        outputChannel.appendLine(`Impact Analysis for Project: ${currentProject.name}`);
        outputChannel.appendLine(`Blast Radius: ${impactResult.blastRadius}`);
        outputChannel.appendLine(`Impact Level: ${impactResult.impactLevel}`);
        outputChannel.appendLine('\nAffected Projects:');
        impactResult.affectedProjects.forEach(project => {
          outputChannel.appendLine(`  - ${project}`);
        });
        outputChannel.show();

        vscode.window.showInformationMessage(
          `Impact Analysis: ${impactResult.affectedProjects.length} projects affected`,
          'View Details'
        ).then(selection => {
          if (selection === 'View Details') {
            outputChannel.show();
          }
        });
      });

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      vscode.window.showErrorMessage(`ContextCore: Failed to analyze impact - ${errorMessage}`);
    }
  });
}


// File: src/commands/openDashboard.ts
import * as vscode from 'vscode';
import { ContextMapper } from '../contextMapper';

/**
 * Creates the open dashboard command
 */
export function createOpenDashboardCommand(contextMapper: ContextMapper): vscode.Disposable {
  return vscode.commands.registerCommand('contextcore.openDashboard', async () => {
    try {
      const currentProject = contextMapper.getCurrentProject();
      if (!currentProject) {
        vscode.window.showWarningMessage('ContextCore: No active project context found');
        return;
      }

      const config = vscode.workspace.getConfiguration('contextcore');
      const grafanaUrl = config.get<string>('grafanaUrl', 'http://localhost:3000');
      
      const dashboardUrl = `${grafanaUrl}/d/contextcore-project?var-project=${currentProject.id}`;
      
      await vscode.env.openExternal(vscode.Uri.parse(dashboardUrl));
      vscode.window.showInformationMessage('ContextCore: Opened project dashboard');

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      vscode.window.showErrorMessage(`ContextCore: Failed to open dashboard - ${errorMessage}`);
    }
  });
}
