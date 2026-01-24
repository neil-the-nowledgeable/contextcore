// src/mapping/contextMapper.ts

import * as vscode from 'vscode';
import { findContextFiles } from './workspaceScanner';
import { matchesPattern } from './patternMatcher';
import * as path from 'path';

/**
 * Represents a project context with risk scope patterns
 */
export interface ProjectContext {
  name: string;
  description?: string;
  riskScopePatterns: string[];
  configPath: string;
}

/**
 * Provides access to project contexts for workspace folders
 */
export interface ContextProvider {
  getContexts(folder: vscode.WorkspaceFolder): ProjectContext[];
  getContextForConfigFile(configUri: vscode.Uri): ProjectContext | undefined;
}

/**
 * LRU Cache implementation for efficient file-to-context mapping
 */
class LRUCache<K, V> {
  private readonly maxSize: number;
  private cache = new Map<K, V>();
  private accessOrder: K[] = [];

  constructor(maxSize = 1000) {
    this.maxSize = maxSize;
  }

  get(key: K): V | undefined {
    const value = this.cache.get(key);
    if (value !== undefined) {
      this.moveToFront(key);
    }
    return value;
  }

  set(key: K, value: V): void {
    if (this.cache.has(key)) {
      this.moveToFront(key);
    } else {
      if (this.accessOrder.length >= this.maxSize) {
        const oldest = this.accessOrder.pop();
        if (oldest !== undefined) {
          this.cache.delete(oldest);
        }
      }
      this.accessOrder.unshift(key);
    }
    this.cache.set(key, value);
  }

  clear(): void {
    this.cache.clear();
    this.accessOrder = [];
  }

  private moveToFront(key: K): void {
    const index = this.accessOrder.indexOf(key);
    if (index > 0) {
      this.accessOrder.splice(index, 1);
      this.accessOrder.unshift(key);
    }
  }
}

/**
 * Maps workspace files to their relevant ProjectContext based on configuration,
 * risk scopes, and target patterns. Efficiently handles large workspaces with caching.
 */
export class ContextMapper implements vscode.Disposable {
  private readonly contextProvider: ContextProvider;
  private readonly fileToContextCache = new LRUCache<string, ProjectContext | undefined>(1000);
  private readonly contextFilesCache = new Map<string, vscode.Uri[]>();
  private readonly disposables: vscode.Disposable[] = [];
  private debounceTimer: NodeJS.Timeout | undefined;
  private isInitialized = false;

  constructor(contextProvider: ContextProvider) {
    this.contextProvider = contextProvider;
    this.setupWorkspaceChangeListener();
  }

  /**
   * Initialize the context mapper by scanning workspace folders
   */
  async initialize(): Promise<void> {
    if (this.isInitialized) {
      return;
    }

    try {
      await this.scanAllWorkspaceFolders();
      this.isInitialized = true;
    } catch (error) {
      console.error('Failed to initialize ContextMapper:', error);
      throw error;
    }
  }

  /**
   * Get the ProjectContext for a given file URI
   */
  getContextForFile(uri: vscode.Uri): ProjectContext | undefined {
    if (!this.isInitialized) {
      console.warn('ContextMapper not initialized. Call initialize() first.');
      return undefined;
    }

    const normalizedPath = this.normalizePath(uri.fsPath);
    const cached = this.fileToContextCache.get(normalizedPath);
    if (cached !== undefined) {
      return cached;
    }

    const context = this.findContextForFile(uri);
    this.fileToContextCache.set(normalizedPath, context);
    return context;
  }

  /**
   * Get the ProjectContext for a given document
   */
  getContextForDocument(document: vscode.TextDocument): ProjectContext | undefined {
    return this.getContextForFile(document.uri);
  }

  /**
   * Dispose of resources and event listeners
   */
  dispose(): void {
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }
    this.disposables.forEach(d => d.dispose());
    this.fileToContextCache.clear();
    this.contextFilesCache.clear();
  }

  private async scanAllWorkspaceFolders(): Promise<void> {
    const folders = vscode.workspace.workspaceFolders || [];
    
    for (const folder of folders) {
      try {
        const contextFiles = await findContextFiles(folder);
        this.contextFilesCache.set(folder.uri.toString(), contextFiles);
      } catch (error) {
        console.error(`Failed to scan workspace folder ${folder.name}:`, error);
      }
    }
  }

  private findContextForFile(uri: vscode.Uri): ProjectContext | undefined {
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(uri);
    if (!workspaceFolder) {
      return undefined;
    }

    const contexts = this.contextProvider.getContexts(workspaceFolder);
    const normalizedFilePath = this.normalizePath(uri.fsPath);

    // Priority 1: Check risk scope patterns
    for (const context of contexts) {
      for (const pattern of context.riskScopePatterns) {
        if (matchesPattern(normalizedFilePath, pattern)) {
          return context;
        }
      }
    }

    // Priority 2: Check closest parent directory with .contextcore
    const contextFiles = this.contextFilesCache.get(workspaceFolder.uri.toString()) || [];
    let closestContext: ProjectContext | undefined;
    let closestDistance = Infinity;

    for (const contextFile of contextFiles) {
      const contextDir = path.dirname(contextFile.fsPath);
      const normalizedContextDir = this.normalizePath(contextDir);
      
      if (normalizedFilePath.startsWith(normalizedContextDir)) {
        const distance = normalizedFilePath.length - normalizedContextDir.length;
        if (distance < closestDistance) {
          closestDistance = distance;
          closestContext = this.contextProvider.getContextForConfigFile(contextFile);
        }
      }
    }

    if (closestContext) {
      return closestContext;
    }

    // Priority 3: Fall back to workspace root context
    return contexts.find(ctx => ctx.configPath === workspaceFolder.uri.fsPath);
  }

  private setupWorkspaceChangeListener(): void {
    const changeListener = vscode.workspace.onDidChangeWorkspaceFolders(event => {
      this.onWorkspaceFoldersChanged(event);
    });
    this.disposables.push(changeListener);
  }

  private onWorkspaceFoldersChanged(event: vscode.WorkspaceFoldersChangeEvent): void {
    // Debounce workspace changes to avoid excessive scanning
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }

    this.debounceTimer = setTimeout(async () => {
      try {
        // Clear cache for removed folders
        for (const removed of event.removed) {
          this.contextFilesCache.delete(removed.uri.toString());
        }

        // Scan added folders
        for (const added of event.added) {
          const contextFiles = await findContextFiles(added);
          this.contextFilesCache.set(added.uri.toString(), contextFiles);
        }

        // Clear file cache to force re-evaluation
        this.fileToContextCache.clear();
      } catch (error) {
        console.error('Error handling workspace folder changes:', error);
      }
    }, 500);
  }

  private normalizePath(filePath: string): string {
    return filePath.replace(/\\/g, '/').toLowerCase();
  }
}

// src/mapping/patternMatcher.ts

import * as path from 'path';

/**
 * Check if a file path matches a glob pattern
 * @param filePath - The file path to test
 * @param pattern - The glob pattern (supports *, **, ?, and ! negation)
 * @returns true if the pattern matches
 */
export function matchesPattern(filePath: string, pattern: string): boolean {
  try {
    const normalizedPath = normalizePath(filePath);
    const normalizedPattern = normalizePattern(pattern);

    // Handle negation
    if (normalizedPattern.startsWith('!')) {
      const positivePattern = normalizedPattern.slice(1);
      return !createMatcher(positivePattern).test(normalizedPath);
    }

    return createMatcher(normalizedPattern).test(normalizedPath);
  } catch (error) {
    console.error(`Error matching pattern "${pattern}" against "${filePath}":`, error);
    return false;
  }
}

/**
 * Check if a file path matches any of the provided patterns
 */
export function matchesAnyPattern(filePath: string, patterns: string[]): boolean {
  return patterns.some(pattern => matchesPattern(filePath, pattern));
}

/**
 * Normalize a file path for consistent pattern matching
 */
function normalizePath(filePath: string): string {
  return path.normalize(filePath).replace(/\\/g, '/');
}

/**
 * Normalize a glob pattern for consistent matching
 */
function normalizePattern(pattern: string): string {
  return pattern.replace(/\\/g, '/').trim();
}

/**
 * Create a RegExp matcher from a glob pattern
 */
function createMatcher(pattern: string): RegExp {
  // Escape special regex characters except glob characters
  let regexPattern = pattern
    .replace(/[.+^${}()|[\]\\]/g, '\\$1')
    // Handle ** (match any path segments)
    .replace(/\*\*/g, '§DOUBLESTAR§')
    // Handle * (match single path segment)
    .replace(/\*/g, '[^/]*')
    // Handle ? (match single character)
    .replace(/\?/g, '.')
    // Restore ** as .*
    .replace(/§DOUBLESTAR§/g, '.*');

  // Anchor the pattern to match the full path
  regexPattern = `^${regexPattern}$`;

  return new RegExp(regexPattern, 'i'); // Case-insensitive matching
}

// src/mapping/workspaceScanner.ts

import * as vscode from 'vscode';

/**
 * Find all context configuration files in a workspace folder
 * @param folder - The workspace folder to scan
 * @returns Array of URIs pointing to context files
 */
export async function findContextFiles(folder: vscode.WorkspaceFolder): Promise<vscode.Uri[]> {
  try {
    const patterns = [
      '.contextcore',
      '.contextcore.yaml',
      '.contextcore.yml', 
      'projectcontext.yaml',
      'projectcontext.yml'
    ];

    const searchPattern = `**/{${patterns.join(',')}}`;
    const excludePattern = '**/node_modules/**';

    const files = await vscode.workspace.findFiles(
      new vscode.RelativePattern(folder, searchPattern),
      excludePattern
    );

    return files.sort((a, b) => {
      // Sort by depth (closer to root first) then by path
      const depthA = a.fsPath.split(vscode.workspace.fs.path.sep).length;
      const depthB = b.fsPath.split(vscode.workspace.fs.path.sep).length;
      
      if (depthA !== depthB) {
        return depthA - depthB;
      }
      
      return a.fsPath.localeCompare(b.fsPath);
    });

  } catch (error) {
    console.error(`Error finding context files in ${folder.name}:`, error);
    return [];
  }
}

/**
 * Find context files across all workspace folders
 * @returns Map of workspace folders to their context files
 */
export async function findAllContextFiles(): Promise<Map<vscode.WorkspaceFolder, vscode.Uri[]>> {
  const result = new Map<vscode.WorkspaceFolder, vscode.Uri[]>();
  const folders = vscode.workspace.workspaceFolders || [];

  await Promise.all(
    folders.map(async folder => {
      const contextFiles = await findContextFiles(folder);
      result.set(folder, contextFiles);
    })
  );

  return result;
}


const contextMapper = new ContextMapper(contextProvider);
await contextMapper.initialize();

// Later in your extension
const context = contextMapper.getContextForFile(document.uri);
