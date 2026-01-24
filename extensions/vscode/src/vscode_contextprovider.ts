// File: src/providers/contextProvider.ts
import * as vscode from 'vscode';
import { loadLocalConfig } from './localConfigProvider';
import { loadFromCli } from './cliProvider';
import { loadFromKubernetes } from './kubernetesProvider';
import { Cache } from '../cache';
import { ProjectContext, ContextCoreConfig } from '../types';

/**
 * Main context provider that orchestrates loading ProjectContext from multiple sources.
 * Implements caching and automatic refresh capabilities.
 */
export class ContextProvider implements vscode.Disposable {
  private _onContextChange: vscode.EventEmitter<ProjectContext | undefined>;
  private cache: Cache<ProjectContext>;
  private refreshTimer?: NodeJS.Timer;
  private disposables: vscode.Disposable[];

  constructor(private config: ContextCoreConfig) {
    this._onContextChange = new vscode.EventEmitter<ProjectContext | undefined>();
    this.cache = new Cache<ProjectContext>(config.refreshInterval * 1000);
    this.disposables = [this._onContextChange];
    this.setupAutoRefresh();
  }

  /**
   * Gets the ProjectContext for the specified workspace folder.
   * Returns cached version if available, otherwise loads from sources.
   */
  async getContext(workspaceFolder: vscode.WorkspaceFolder): Promise<ProjectContext | undefined> {
    const cacheKey = workspaceFolder.uri.toString();
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
  }

  /**
   * Forces a refresh of the context from all sources, bypassing cache.
   */
  async refresh(): Promise<void> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
      return;
    }

    // Refresh all workspace folders
    for (const workspaceFolder of workspaceFolders) {
      const cacheKey = workspaceFolder.uri.toString();
      this.cache.invalidate(cacheKey);
      
      const context = await this.loadFromSources(workspaceFolder);
      if (context) {
        this.cache.set(cacheKey, context);
        this._onContextChange.fire(context);
      }
    }
  }

  /**
   * Event fired when context changes.
   */
  readonly onContextChange = this._onContextChange.event;

  /**
   * Loads context from sources in priority order: local file -> CLI -> Kubernetes.
   */
  private async loadFromSources(workspaceFolder: vscode.WorkspaceFolder): Promise<ProjectContext | undefined> {
    try {
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
      const k8sContext = await loadFromKubernetes(workspaceFolder.name, 'default');
      return k8sContext;
    } catch (error) {
      console.error(`Error loading context from sources: ${error}`);
      return undefined;
    }
  }

  private setupAutoRefresh(): void {
    if (this.config.refreshInterval > 0) {
      this.refreshTimer = setInterval(() => {
        this.refresh().catch(error => {
          console.error(`Auto-refresh failed: ${error}`);
        });
      }, this.config.refreshInterval * 1000);
    }
  }

  dispose(): void {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = undefined;
    }
    
    this.cache.clear();
    this.disposables.forEach(disposable => disposable.dispose());
    this.disposables = [];
  }
}

// File: src/providers/localConfigProvider.ts
import * as vscode from 'vscode';
import * as path from 'path';
import * as yaml from 'js-yaml';
import { ProjectContext } from '../types';

/**
 * Loads ProjectContext from local .contextcore or .contextcore.yaml files.
 */
export async function loadLocalConfig(workspaceFolder: vscode.WorkspaceFolder): Promise<ProjectContext | undefined> {
  try {
    const configFilePath = await findConfigFile(workspaceFolder.uri.fsPath);
    if (!configFilePath) {
      return undefined;
    }

    return await parseConfigFile(configFilePath);
  } catch (error) {
    console.error(`Failed to load local config: ${error}`);
    return undefined;
  }
}

async function findConfigFile(workspaceRoot: string): Promise<string | undefined> {
  const possibleFiles = [
    path.join(workspaceRoot, '.contextcore.yaml'),
    path.join(workspaceRoot, '.contextcore')
  ];

  for (const filePath of possibleFiles) {
    try {
      const uri = vscode.Uri.file(filePath);
      await vscode.workspace.fs.stat(uri);
      return filePath;
    } catch {
      // File doesn't exist, continue to next
      continue;
    }
  }

  return undefined;
}

async function parseConfigFile(filePath: string): Promise<ProjectContext> {
  const uri = vscode.Uri.file(filePath);
  const fileContents = await vscode.workspace.fs.readFile(uri);
  const yamlContent = new TextDecoder().decode(fileContents);
  
  const parsed = yaml.load(yamlContent);
  if (!parsed || typeof parsed !== 'object') {
    throw new Error('Invalid YAML content');
  }
  
  return parsed as ProjectContext;
}

// File: src/providers/cliProvider.ts
import * as child_process from 'child_process';
import * as vscode from 'vscode';
import { ProjectContext } from '../types';

/**
 * Loads ProjectContext using the contextcore CLI command.
 */
export async function loadFromCli(workspaceFolder: vscode.WorkspaceFolder): Promise<ProjectContext | undefined> {
  try {
    const command = 'contextcore context show --format json';
    const options: child_process.ExecOptions = {
      cwd: workspaceFolder.uri.fsPath,
      timeout: 30000 // 30 second timeout
    };

    const output = await execAsync(command, options);
    return parseCliOutput(output);
  } catch (error) {
    console.error(`CLI provider failed: ${error}`);
    return undefined;
  }
}

function execAsync(command: string, options: child_process.ExecOptions = {}): Promise<string> {
  return new Promise((resolve, reject) => {
    child_process.exec(command, options, (error, stdout, stderr) => {
      if (error) {
        reject(new Error(`Command failed: ${error.message}. Stderr: ${stderr}`));
        return;
      }
      resolve(stdout.trim());
    });
  });
}

function parseCliOutput(output: string): ProjectContext {
  if (!output || output.trim() === '') {
    throw new Error('Empty CLI output');
  }

  try {
    return JSON.parse(output) as ProjectContext;
  } catch (error) {
    throw new Error(`Invalid JSON from CLI: ${error}`);
  }
}

// File: src/providers/kubernetesProvider.ts
import * as k8s from '@kubernetes/client-node';
import { ProjectContext } from '../types';

/**
 * Loads ProjectContext from Kubernetes Custom Resource Definition.
 */
export async function loadFromKubernetes(name: string, namespace: string = 'default'): Promise<ProjectContext | undefined> {
  try {
    const kubeClient = createKubeClient();
    if (!kubeClient) {
      return undefined;
    }

    const response = await kubeClient.getNamespacedCustomObject(
      'contextcore.io',
      'v1alpha1',
      namespace,
      'projectcontexts',
      name
    );

    return parseProjectContextCrd(response.body);
  } catch (error) {
    console.error(`Kubernetes provider failed: ${error}`);
    return undefined;
  }
}

function createKubeClient(): k8s.CustomObjectsApi | undefined {
  try {
    const kc = new k8s.KubeConfig();
    kc.loadFromDefault();
    return kc.makeApiClient(k8s.CustomObjectsApi);
  } catch (error) {
    console.error(`Failed to create Kubernetes client: ${error}`);
    return undefined;
  }
}

function parseProjectContextCrd(crdData: unknown): ProjectContext {
  if (!crdData || typeof crdData !== 'object') {
    throw new Error('Invalid CRD data');
  }

  const crd = crdData as any;
  if (!crd.spec) {
    throw new Error('CRD missing spec field');
  }

  return crd.spec as ProjectContext;
}

// File: src/cache.ts
/**
 * Generic cache with TTL (Time To Live) support.
 */
export class Cache<T> {
  private storage: Map<string, CacheEntry<T>>;
  private defaultTtlMs: number;

  constructor(defaultTtlMs: number) {
    this.storage = new Map();
    this.defaultTtlMs = Math.max(defaultTtlMs, 1000); // Minimum 1 second TTL
  }

  /**
   * Gets a cached value if it exists and hasn't expired.
   */
  get(key: string): T | undefined {
    const entry = this.storage.get(key);
    if (!entry) {
      return undefined;
    }

    if (Date.now() >= entry.expiresAt) {
      this.storage.delete(key);
      return undefined;
    }

    return entry.value;
  }

  /**
   * Sets a value in the cache with optional custom TTL.
   */
  set(key: string, value: T, ttlMs: number = this.defaultTtlMs): void {
    const expiresAt = Date.now() + Math.max(ttlMs, 1000);
    this.storage.set(key, { value, expiresAt });
    
    // Periodic cleanup to prevent memory leaks
    if (this.storage.size > 100) {
      this.cleanup();
    }
  }

  /**
   * Removes a specific key from the cache.
   */
  invalidate(key: string): void {
    this.storage.delete(key);
  }

  /**
   * Clears all cached entries.
   */
  clear(): void {
    this.storage.clear();
  }

  /**
   * Gets the current cache size.
   */
  size(): number {
    return this.storage.size;
  }

  private cleanup(): void {
    const now = Date.now();
    const expiredKeys: string[] = [];

    for (const [key, entry] of this.storage.entries()) {
      if (entry.expiresAt <= now) {
        expiredKeys.push(key);
      }
    }

    expiredKeys.forEach(key => this.storage.delete(key));
  }
}

interface CacheEntry<T> {
  value: T;
  expiresAt: number;
}


   export interface ProjectContext {
     // Define your ProjectContext structure
   }
   
   export interface ContextCoreConfig {
     refreshInterval: number; // in seconds
   }
   

   const config: ContextCoreConfig = { refreshInterval: 300 }; // 5 minutes
   const provider = new ContextProvider(config);
   
   // Register for disposal
   context.subscriptions.push(provider);
   