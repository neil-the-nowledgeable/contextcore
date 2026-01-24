// src/providers/index.ts
export { ContextProvider } from './contextProvider';
export { loadLocalConfig } from './localConfigProvider';
export { loadFromCli } from './cliProvider';
export { loadFromKubernetes } from './kubernetesProvider';

// src/providers/contextProvider.ts
import * as vscode from 'vscode';
import { ProjectContext, ContextCoreConfig } from '../types';
import { Cache } from '../cache';
import { loadLocalConfig } from './localConfigProvider';
import { loadFromCli } from './cliProvider';
import { loadFromKubernetes } from './kubernetesProvider';
import { getFullConfig } from '../config';

/**
 * Provider that loads ProjectContext from multiple sources with caching and automatic refresh.
 * Sources are checked in priority order: local files -> CLI -> Kubernetes.
 */
export class ContextProvider implements vscode.Disposable {
    private _onContextChange: vscode.EventEmitter<ProjectContext | undefined> = new vscode.EventEmitter();
    private cache: Cache<ProjectContext>;
    private refreshTimer?: NodeJS.Timeout;
    private disposables: vscode.Disposable[] = [];

    constructor() {
        const config = getFullConfig();
        this.cache = new Cache<ProjectContext>(config.refreshInterval);
        this.disposables.push(this._onContextChange);
        this.setupAutoRefresh();
    }

    /**
     * Get project context for the given workspace folder.
     * Uses cache if available, otherwise loads from sources.
     */
    async getContext(workspaceFolder: vscode.WorkspaceFolder): Promise<ProjectContext | undefined> {
        const cacheKey = workspaceFolder.uri.toString();
        
        try {
            const cachedContext = this.cache.get(cacheKey);
            if (cachedContext) {
                return cachedContext;
            }

            const context = await this.loadFromSources(workspaceFolder);
            if (context) {
                this.cache.set(cacheKey, context);
                this._onContextChange.fire(context);
            }

            return context;
        } catch (error) {
            console.error(`Failed to get context for ${workspaceFolder.name}:`, error);
            return undefined;
        }
    }

    /**
     * Manually refresh all cached contexts by invalidating cache and reloading.
     */
    async refresh(): Promise<void> {
        try {
            this.cache.clear();
            this._onContextChange.fire(undefined);
        } catch (error) {
            console.error('Failed to refresh contexts:', error);
        }
    }

    /**
     * Event fired when context changes.
     */
    get onContextChange(): vscode.Event<ProjectContext | undefined> {
        return this._onContextChange.event;
    }

    /**
     * Load context from sources in priority order: local -> CLI -> Kubernetes.
     */
    private async loadFromSources(workspaceFolder: vscode.WorkspaceFolder): Promise<ProjectContext | undefined> {
        // Try local config first
        const localContext = await loadLocalConfig(workspaceFolder);
        if (localContext) {
            return localContext;
        }

        // Try CLI second
        const cliContext = await loadFromCli(workspaceFolder);
        if (cliContext) {
            return cliContext;
        }

        // Try Kubernetes last
        const kubernetesContext = await loadFromKubernetes(workspaceFolder.name);
        if (kubernetesContext) {
            return kubernetesContext;
        }

        return undefined;
    }

    /**
     * Set up automatic refresh timer based on configuration.
     */
    private setupAutoRefresh(): void {
        const config = getFullConfig();
        if (config.refreshInterval > 0) {
            this.refreshTimer = setInterval(() => {
                this.refresh();
            }, config.refreshInterval);
        }
    }

    dispose(): void {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = undefined;
        }
        
        this.disposables.forEach(disposable => {
            try {
                disposable.dispose();
            } catch (error) {
                console.error('Error disposing resource:', error);
            }
        });
        
        this.disposables = [];
    }
}

// src/providers/localConfigProvider.ts
import * as vscode from 'vscode';
import * as path from 'path';
import * as yaml from 'yaml';
import { ProjectContext } from '../types';

/**
 * Load project context from local configuration files.
 * Looks for .contextcore.yaml or .contextcore in workspace root.
 */
export async function loadLocalConfig(workspaceFolder: vscode.WorkspaceFolder): Promise<ProjectContext | undefined> {
    const configFiles = ['.contextcore.yaml', '.contextcore'];
    
    for (const fileName of configFiles) {
        try {
            const configPath = vscode.Uri.joinPath(workspaceFolder.uri, fileName);
            const configData = await vscode.workspace.fs.readFile(configPath);
            const configText = Buffer.from(configData).toString('utf8');
            
            const context = yaml.parse(configText) as ProjectContext;
            return context;
        } catch (error) {
            // File not found or parsing error - continue to next file
            continue;
        }
    }
    
    return undefined;
}

// src/providers/cliProvider.ts
import * as child_process from 'child_process';
import * as vscode from 'vscode';
import { ProjectContext } from '../types';

/**
 * Load project context from ContextCore CLI.
 * Executes 'contextcore context show --format json' command.
 */
export async function loadFromCli(workspaceFolder: vscode.WorkspaceFolder): Promise<ProjectContext | undefined> {
    return new Promise<ProjectContext | undefined>((resolve) => {
        const command = 'contextcore context show --format json';
        const options = {
            cwd: workspaceFolder.uri.fsPath,
            timeout: 10000 // 10 second timeout
        };

        child_process.exec(command, options, (error, stdout, stderr) => {
            if (error) {
                // Command failed - return undefined without throwing
                resolve(undefined);
                return;
            }

            try {
                const context = JSON.parse(stdout) as ProjectContext;
                resolve(context);
            } catch (parseError) {
                // JSON parsing failed - return undefined
                resolve(undefined);
            }
        });
    });
}

// src/providers/kubernetesProvider.ts
import * as k8s from '@kubernetes/client-node';
import { ProjectContext } from '../types';
import { getConfig } from '../config';

/**
 * Load project context from Kubernetes cluster as a Custom Resource.
 * Fetches ProjectContext CRD from the specified namespace.
 */
export async function loadFromKubernetes(name: string, namespace?: string): Promise<ProjectContext | undefined> {
    try {
        const kc = new k8s.KubeConfig();
        const config = getConfig();
        
        if (config.kubeconfigPath) {
            kc.loadFromFile(config.kubeconfigPath);
        } else {
            kc.loadFromDefault();
        }

        const k8sApi = kc.makeApiClient(k8s.CustomObjectsApi);
        
        // ProjectContext CRD details
        const group = 'contextcore.io';
        const version = 'v1';
        const plural = 'projectcontexts';
        const targetNamespace = namespace || 'default';

        const response = await k8sApi.getNamespacedCustomObject(
            group,
            version,
            targetNamespace,
            plural,
            name
        );

        // Extract spec from Kubernetes resource
        const k8sResource = response.body as any;
        if (k8sResource && k8sResource.spec) {
            return k8sResource.spec as ProjectContext;
        }

        return undefined;
    } catch (error) {
        // Kubernetes API call failed - return undefined without throwing
        return undefined;
    }
}
