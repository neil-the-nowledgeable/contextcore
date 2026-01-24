// src/ui/statusBar.ts
import * as vscode from 'vscode';
import { ContextMapper } from '../mapping';
import { ProjectContext } from '../types';
import { buildTooltip } from './statusBarTooltip';

/**
 * Manages the status bar item for displaying project context information
 */
export class ContextStatusBar implements vscode.Disposable {
    private statusBarItem: vscode.StatusBarItem;
    private disposables: vscode.Disposable[] = [];

    constructor(private contextMapper: ContextMapper) {
        this.statusBarItem = vscode.window.createStatusBarItem(
            vscode.StatusBarAlignment.Left,
            100
        );
        this.statusBarItem.command = 'contextCore.showQuickPick';
        
        // Register click handler
        this.disposables.push(
            vscode.commands.registerCommand('contextCore.showQuickPick', () => {
                this.handleStatusBarClick().catch(error => {
                    console.error('Error handling status bar click:', error);
                });
            })
        );
        
        this.statusBarItem.show();
    }

    /**
     * Updates the status bar based on the current active editor
     */
    public update(editor: vscode.TextEditor | undefined): void {
        try {
            if (!editor) {
                this.statusBarItem.hide();
                return;
            }

            const context = this.contextMapper.getContextForFile(editor.document.uri.fsPath);
            if (!context) {
                this.statusBarItem.hide();
                return;
            }

            const style = this.getCriticalityStyle(context.criticality);
            this.statusBarItem.text = `${style.icon} Context`;
            this.statusBarItem.tooltip = buildTooltip(context);
            
            if (style.backgroundColor) {
                this.statusBarItem.backgroundColor = new vscode.ThemeColor(style.backgroundColor);
            } else {
                this.statusBarItem.backgroundColor = undefined;
            }
            
            this.statusBarItem.show();
        } catch (error) {
            console.error('Error updating status bar:', error);
            this.statusBarItem.hide();
        }
    }

    /**
     * Gets icon and background color based on criticality level
     */
    private getCriticalityStyle(criticality: string): { icon: string; backgroundColor?: string } {
        switch (criticality.toLowerCase()) {
            case 'critical':
                return { icon: '$(flame)', backgroundColor: 'statusBarItem.errorBackground' };
            case 'high':
                return { icon: '$(warning)', backgroundColor: 'statusBarItem.warningBackground' };
            case 'medium':
                return { icon: '$(info)' };
            case 'low':
                return { icon: '$(check)' };
            default:
                return { icon: '$(question)' };
        }
    }

    /**
     * Handles status bar click to show context menu
     */
    private async handleStatusBarClick(): Promise<void> {
        try {
            const activeEditor = vscode.window.activeTextEditor;
            if (!activeEditor) {
                return;
            }

            const context = this.contextMapper.getContextForFile(activeEditor.document.uri.fsPath);
            if (!context) {
                return;
            }

            const items: vscode.QuickPickItem[] = [
                {
                    label: '$(eye) View Context Details',
                    description: 'Show detailed context information'
                },
                {
                    label: '$(refresh) Refresh Context',
                    description: 'Reload context mapping'
                },
                {
                    label: '$(settings-gear) Configure Context',
                    description: 'Open context configuration'
                }
            ];

            const selected = await vscode.window.showQuickPick(items, {
                placeHolder: 'Choose a context action'
            });

            if (selected?.label.includes('View Context Details')) {
                await vscode.commands.executeCommand('contextCore.showContextDetails');
            } else if (selected?.label.includes('Refresh Context')) {
                await vscode.commands.executeCommand('contextCore.refresh');
            } else if (selected?.label.includes('Configure Context')) {
                await vscode.commands.executeCommand('workbench.action.openSettings', 'contextCore');
            }
        } catch (error) {
            vscode.window.showErrorMessage(`Context action failed: ${error}`);
        }
    }

    public dispose(): void {
        this.statusBarItem.dispose();
        this.disposables.forEach(d => d.dispose());
    }
}


// src/ui/statusBarTooltip.ts
import * as vscode from 'vscode';
import { ProjectContext } from '../types';

/**
 * Builds a formatted tooltip for the status bar item
 */
export function buildTooltip(context: ProjectContext): vscode.MarkdownString {
    const tooltip = new vscode.MarkdownString();
    tooltip.supportHtml = true;
    tooltip.isTrusted = true;

    tooltip.appendMarkdown(`**Project Context**\n\n`);
    tooltip.appendMarkdown(`**Project ID:** ${context.projectId}\n`);
    tooltip.appendMarkdown(`**Criticality:** ${context.criticality}\n`);
    
    if (context.owner) {
        tooltip.appendMarkdown(`**Owner:** ${context.owner}\n`);
    }

    if (context.risks?.length) {
        tooltip.appendMarkdown(`**Risks:** ${context.risks.length} identified\n`);
    }

    if (context.requirements?.targets?.length) {
        const targetCount = context.requirements.targets.length;
        tooltip.appendMarkdown(`**SLO Targets:** ${targetCount} defined\n`);
    }

    if (context.requirements?.description) {
        const summary = context.requirements.description.length > 100 
            ? context.requirements.description.substring(0, 100) + '...'
            : context.requirements.description;
        tooltip.appendMarkdown(`\n**Requirements:** ${summary}\n`);
    }

    return tooltip;
}


// src/ui/sidePanel/index.ts
export { ProjectTreeProvider } from './projectTreeProvider';
export { ContextTreeItem, TreeItemType } from './contextTreeItem';


// src/ui/sidePanel/contextTreeItem.ts
import * as vscode from 'vscode';

export enum TreeItemType {
    Project = 'project',
    Section = 'section',
    Risk = 'risk',
    Requirement = 'requirement',
    Target = 'target',
    Property = 'property'
}

/**
 * Tree item for displaying context information in the side panel
 */
export class ContextTreeItem extends vscode.TreeItem {
    constructor(
        label: string,
        collapsibleState: vscode.TreeItemCollapsibleState,
        public readonly type: TreeItemType,
        public readonly value?: any,
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


// src/ui/sidePanel/projectTreeProvider.ts
import * as vscode from 'vscode';
import { ContextTreeItem, TreeItemType } from './contextTreeItem';
import { ContextMapper } from '../../mapping';

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

        const context = this.contextMapper.getContextForFile(activeEditor.document.uri.fsPath);
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
        const context = element.value;
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
        if (context.risks?.length > 0) {
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

        return children;
    }

    private getSectionChildren(element: ContextTreeItem): ContextTreeItem[] {
        if (element.label === 'Risks') {
            return element.value.map((risk: any) => 
                new ContextTreeItem(
                    risk.description || risk.id || 'Risk',
                    vscode.TreeItemCollapsibleState.None,
                    TreeItemType.Risk,
                    risk,
                    risk.severity
                )
            );
        }

        if (element.label === 'Requirements' && element.value.targets) {
            return element.value.targets.map((target: any) =>
                new ContextTreeItem(
                    `${target.metric}: ${target.threshold}`,
                    vscode.TreeItemCollapsibleState.None,
                    TreeItemType.Target,
                    target
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


// src/ui/decorations/index.ts
export { DecorationProvider } from './decorationProvider';
