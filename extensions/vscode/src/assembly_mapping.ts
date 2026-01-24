// src/mapping/index.ts
export { ContextMapper } from './contextMapper';
export { matchesPattern, matchesAnyPattern } from './patternMatcher';
export { findContextFiles } from './workspaceScanner';


// src/mapping/contextMapper.ts
import * as vscode from 'vscode';
import * as path from 'path';
import { ProjectContext } from '../types';
import { ContextProvider } from '../providers';
import { matchesPattern } from './patternMatcher';
import { findContextFiles } from './workspaceScanner';

/**
 * Maps workspace files to their relevant ProjectContext based on configuration,
 * risk scopes, and directory structure.
 */
export class ContextMapper implements vscode.Disposable {
  private contextProvider: ContextProvider;
  private fileToContextCache: Map<string, ProjectContext | undefined>;
  private contextFilesCache: Map<string, vscode.Uri[]>;
  private disposables: vscode.Disposable[];
  private isInitialized: boolean;

  constructor(contextProvider: ContextProvider) {
    this.contextProvider = contextProvider;
    this.fileToContextCache = new Map();
    this.contextFilesCache = new Map();
    this.disposables = [];
    this.isInitialized = false;
  }

  /**
   * Initialize the context mapper by scanning workspace folders
   */
  async initialize(): Promise<void> {
    try {
      const workspaceFolders = vscode.workspace.workspaceFolders || [];
      
      for (const folder of workspaceFolders) {
        const contextFiles = await findContextFiles(folder);
        this.contextFilesCache.set(folder.uri.toString(), contextFiles);
      }
      
      this.setupWorkspaceChangeListener();
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
      console.warn('ContextMapper not initialized');
      return undefined;
    }

    const cacheKey = uri.fsPath;
    if (this.fileToContextCache.has(cacheKey)) {
      return this.fileToContextCache.get(cacheKey);
    }

    const context = this.findContextForFile(uri);
    this.fileToContextCache.set(cacheKey, context);
    return context;
  }

  /**
   * Get the ProjectContext for a given document
   */
  getContextForDocument(document: vscode.TextDocument): ProjectContext | undefined {
    return this.getContextForFile(document.uri);
  }

  /**
   * Find context for file using priority system:
   * 1. Risk scope patterns
   * 2. Closest parent with .contextcore
   * 3. Workspace root context
   */
  private findContextForFile(uri: vscode.Uri): ProjectContext | undefined {
    try {
      // Priority 1: Check risk scope patterns
      const riskScopeContext = this.findRiskScopeContext(uri);
      if (riskScopeContext) {
        return riskScopeContext;
      }

      // Priority 2: Closest parent with .contextcore
      const parentContext = this.findParentDirectoryContext(uri);
      if (parentContext) {
        return parentContext;
      }

      // Priority 3: Workspace root context
      return this.findWorkspaceRootContext(uri);
    } catch (error) {
      console.error('Error finding context for file:', uri.fsPath, error);
      return undefined;
    }
  }

  private findRiskScopeContext(uri: vscode.Uri): ProjectContext | undefined {
    const contexts = this.contextProvider.getAllContexts();
    const relativePath = this.getRelativePath(uri);

    for (const context of contexts) {
      if (context.risk?.scope) {
        for (const pattern of context.risk.scope) {
          if (matchesPattern(relativePath, pattern)) {
            return context;
          }
        }
      }
    }
    return undefined;
  }

  private findParentDirectoryContext(uri: vscode.Uri): ProjectContext | undefined {
    let currentDir = path.dirname(uri.fsPath);
    const workspaceRoot = this.getWorkspaceRoot(uri);

    while (currentDir && currentDir !== workspaceRoot && currentDir !== path.dirname(currentDir)) {
      const contextFile = path.join(currentDir, '.contextcore');
      const context = this.contextProvider.getContextByPath(contextFile);
      if (context) {
        return context;
      }
      currentDir = path.dirname(currentDir);
    }
    return undefined;
  }

  private findWorkspaceRootContext(uri: vscode.Uri): ProjectContext | undefined {
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(uri);
    if (!workspaceFolder) {
      return undefined;
    }

    const rootContextFile = path.join(workspaceFolder.uri.fsPath, '.contextcore');
    return this.contextProvider.getContextByPath(rootContextFile);
  }

  private getRelativePath(uri: vscode.Uri): string {
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(uri);
    if (!workspaceFolder) {
      return uri.fsPath;
    }
    return path.relative(workspaceFolder.uri.fsPath, uri.fsPath);
  }

  private getWorkspaceRoot(uri: vscode.Uri): string | undefined {
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(uri);
    return workspaceFolder?.uri.fsPath;
  }

  /**
   * Set up file system watchers for context files
   */
  private setupWorkspaceChangeListener(): void {
    const patterns = [
      '**/.contextcore',
      '**/.contextcore.yaml',
      '**/.contextcore.yml',
      '**/projectcontext.yaml',
      '**/projectcontext.yml'
    ];

    for (const pattern of patterns) {
      const watcher = vscode.workspace.createFileSystemWatcher(pattern);
      
      watcher.onDidCreate((uri) => this.handleContextFileChange(uri));
      watcher.onDidChange((uri) => this.handleContextFileChange(uri));
      watcher.onDidDelete((uri) => this.handleContextFileChange(uri));
      
      this.disposables.push(watcher);
    }

    // Listen for file changes to invalidate cache
    const fileWatcher = vscode.workspace.onDidChangeTextDocument((event) => {
      this.fileToContextCache.delete(event.document.uri.fsPath);
    });
    
    this.disposables.push(fileWatcher);
  }

  private handleContextFileChange(uri: vscode.Uri): void {
    // Invalidate relevant cache entries
    this.fileToContextCache.clear();
    
    // Update context files cache
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(uri);
    if (workspaceFolder) {
      findContextFiles(workspaceFolder).then(contextFiles => {
        this.contextFilesCache.set(workspaceFolder.uri.toString(), contextFiles);
      }).catch(error => {
        console.error('Error updating context files cache:', error);
      });
    }
  }

  /**
   * Dispose of all resources
   */
  dispose(): void {
    this.disposables.forEach(disposable => {
      try {
        disposable.dispose();
      } catch (error) {
        console.error('Error disposing resource:', error);
      }
    });
    this.disposables = [];
    this.fileToContextCache.clear();
    this.contextFilesCache.clear();
  }
}


// src/mapping/patternMatcher.ts

/**
 * Check if a file path matches a given pattern
 * Supports glob patterns: *, **, ?, and negation with !
 */
export function matchesPattern(filePath: string, pattern: string): boolean {
  // Normalize path separators
  const normalizedPath = filePath.replace(/\\/g, '/');
  let normalizedPattern = pattern.replace(/\\/g, '/');
  
  // Handle negation
  const isNegated = normalizedPattern.startsWith('!');
  if (isNegated) {
    normalizedPattern = normalizedPattern.slice(1);
  }
  
  // Convert glob pattern to regex
  const regex = globToRegex(normalizedPattern);
  const matches = regex.test(normalizedPath);
  
  return isNegated ? !matches : matches;
}

/**
 * Check if a file path matches any of the given patterns
 */
export function matchesAnyPattern(filePath: string, patterns: string[]): boolean {
  return patterns.some(pattern => matchesPattern(filePath, pattern));
}

/**
 * Convert a glob pattern to a regular expression
 * Supports: *, **, ?, character classes [abc], and ranges [a-z]
 */
function globToRegex(pattern: string): RegExp {
  let regexPattern = '';
  let i = 0;
  
  while (i < pattern.length) {
    const char = pattern[i];
    
    switch (char) {
      case '*':
        if (pattern[i + 1] === '*') {
          // Handle **
          if (pattern[i + 2] === '/') {
            regexPattern += '(?:.*/)?';
            i += 3;
          } else {
            regexPattern += '.*';
            i += 2;
          }
        } else {
          // Handle single *
          regexPattern += '[^/]*';
          i++;
        }
        break;
        
      case '?':
        regexPattern += '[^/]';
        i++;
        break;
        
      case '[':
        // Handle character classes
        let j = i + 1;
        while (j < pattern.length && pattern[j] !== ']') {
          j++;
        }
        if (j < pattern.length) {
          const charClass = pattern.slice(i, j + 1);
          regexPattern += charClass;
          i = j + 1;
        } else {
          regexPattern += '\\[';
          i++;
        }
        break;
        
      case '.':
      case '+':
      case '^':
      case '$':
      case '(':
      case ')':
      case '{':
      case '}':
      case '|':
      case '\\':
        // Escape regex special characters
        regexPattern += '\\' + char;
        i++;
        break;
        
      default:
        regexPattern += char;
        i++;
        break;
    }
  }
  
  return new RegExp('^' + regexPattern + '$');
}


// src/mapping/workspaceScanner.ts
import * as vscode from 'vscode';

/**
 * Find all context files in a workspace folder
 * Returns files sorted by depth (closer to root first)
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
    
    const allFiles: vscode.Uri[] = [];
    
    for (const pattern of patterns) {
      const globPattern = new vscode.RelativePattern(folder, `**/${pattern}`);
      const files = await vscode.workspace.findFiles(
        globPattern,
        '**/node_modules/**'
      );
      allFiles.push(...files);
    }
    
    // Remove duplicates and sort by depth (closer to root first)
    const uniqueFiles = Array.from(new Set(allFiles.map(f => f.toString())))
      .map(str => vscode.Uri.parse(str));
    
    return uniqueFiles.sort((a, b) => {
      const aDepth = getPathDepth(a, folder);
      const bDepth = getPathDepth(b, folder);
      return aDepth - bDepth;
    });
  } catch (error) {
    console.error('Error finding context files:', error);
    return [];
  }
}

/**
 * Calculate the depth of a file path relative to the workspace folder
 */
function getPathDepth(uri: vscode.Uri, workspaceFolder: vscode.WorkspaceFolder): number {
  const relativePath = vscode.workspace.asRelativePath(uri, false);
  return relativePath.split('/').length - 1;
}
