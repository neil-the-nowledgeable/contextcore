/**
 * Core type definitions for the ContextCore VSCode extension.
 * These types match the ProjectContext CRD schema exactly.
 */

/**
 * Project criticality levels
 */
export type Criticality = 'critical' | 'high' | 'medium' | 'low';

/**
 * Risk priority levels
 */
export type Priority = 'P1' | 'P2' | 'P3' | 'P4';

/**
 * Project metadata information
 */
export interface ProjectMetadata {
  /** Project name */
  name: string;
  /** Kubernetes namespace */
  namespace: string;
}

/**
 * Basic project information
 */
export interface ProjectInfo {
  /** Unique project identifier */
  id: string;
  /** Associated epic (optional) */
  epic?: string;
  /** Human-readable project name (optional) */
  name?: string;
}

/**
 * Business context for the project
 */
export interface BusinessContext {
  /** Business criticality level */
  criticality?: Criticality;
  /** Business value description */
  value?: string;
  /** Project owner */
  owner?: string;
  /** Cost center identifier */
  costCenter?: string;
}

/**
 * Performance and reliability requirements
 */
export interface Requirements {
  /** Availability requirement (e.g., "99.9%") */
  availability?: string;
  /** 99th percentile latency requirement */
  latencyP99?: string;
  /** 50th percentile latency requirement */
  latencyP50?: string;
  /** Throughput requirement */
  throughput?: string;
  /** Error budget specification */
  errorBudget?: string;
}

/**
 * Project risk definition
 */
export interface Risk {
  /** Risk type/category */
  type: string;
  /** Risk priority level */
  priority: Priority;
  /** Risk description */
  description: string;
  /** Risk scope (optional) */
  scope?: string;
  /** Mitigation strategy (optional) */
  mitigation?: string;
}

/**
 * Deployment or integration target
 */
export interface Target {
  /** Kubernetes resource kind */
  kind: string;
  /** Target name */
  name: string;
  /** Target namespace (optional) */
  namespace?: string;
}

/**
 * Design documentation references
 */
export interface Design {
  /** Architecture Decision Record reference */
  adr?: string;
  /** Design document reference */
  doc?: string;
  /** API contract reference */
  apiContract?: string;
}

/**
 * Project context specification
 */
export interface ProjectContextSpec {
  /** Project information */
  project?: ProjectInfo;
  /** Business context */
  business?: BusinessContext;
  /** Technical requirements */
  requirements?: Requirements;
  /** Associated risks */
  risks?: Risk[];
  /** Deployment targets */
  targets?: Target[];
  /** Design documentation */
  design?: Design;
}

/**
 * Complete project context matching the CRD schema
 */
export interface ProjectContext {
  /** Project metadata */
  metadata: ProjectMetadata;
  /** Project specification */
  spec: ProjectContextSpec;
}

/**
 * Extension configuration interface
 */
export interface ContextCoreConfig {
  /** Cache refresh interval in milliseconds */
  refreshInterval: number;
  /** Kubernetes config file path (optional) */
  kubeconfig?: string;
  /** Default namespace */
  namespace: string;
  /** Show inline hints in editor */
  showInlineHints: boolean;
  /** Grafana dashboard URL */
  grafanaUrl: string;
}


import * as vscode from 'vscode';
import { ContextCoreConfig } from './types';

/**
 * Configuration keys for the ContextCore extension
 */
export const CONFIG_KEYS = {
  refreshInterval: 'contextcore.refreshInterval',
  kubeconfig: 'contextcore.kubeconfig',
  namespace: 'contextcore.namespace',
  showInlineHints: 'contextcore.showInlineHints',
  grafanaUrl: 'contextcore.grafanaUrl'
} as const;

/**
 * Retrieves a configuration value with type safety
 * @param key Configuration key
 * @param defaultValue Default value if configuration is not set
 * @returns Configuration value or default
 */
export function getConfig<T>(key: string, defaultValue?: T): T {
  try {
    const config = vscode.workspace.getConfiguration();
    const value = config.get<T>(key);
    return value !== undefined ? value : (defaultValue as T);
  } catch (error) {
    console.error(`Failed to get config for key ${key}:`, error);
    return defaultValue as T;
  }
}

/**
 * Registers a callback for configuration changes
 * @param callback Function to call when configuration changes
 * @returns Disposable to unregister the listener
 */
export function onConfigChange(callback: () => void): vscode.Disposable {
  return vscode.workspace.onDidChangeConfiguration(event => {
    // Only trigger callback if ContextCore configuration changed
    if (event.affectsConfiguration('contextcore')) {
      try {
        callback();
      } catch (error) {
        console.error('Configuration change callback failed:', error);
      }
    }
  });
}

/**
 * Gets the complete extension configuration
 * @returns Full configuration object with defaults applied
 */
export function getFullConfig(): ContextCoreConfig {
  return {
    refreshInterval: getConfig(CONFIG_KEYS.refreshInterval, 30000),
    kubeconfig: getConfig(CONFIG_KEYS.kubeconfig),
    namespace: getConfig(CONFIG_KEYS.namespace, 'default'),
    showInlineHints: getConfig(CONFIG_KEYS.showInlineHints, true),
    grafanaUrl: getConfig(CONFIG_KEYS.grafanaUrl, '')
  };
}


import * as vscode from 'vscode';

/**
 * Supported log levels
 */
export type LogLevel = 'info' | 'warn' | 'error';

/**
 * Output channel for logging (private to this module)
 */
let outputChannel: vscode.OutputChannel | undefined;

/**
 * Initializes the logger and creates the output channel
 */
export function initialize(): void {
  if (!outputChannel) {
    outputChannel = vscode.window.createOutputChannel('ContextCore');
  }
}

/**
 * Logs a message with timestamp and level
 * @param message Message to log
 * @param level Log level (defaults to 'info')
 */
export function log(message: string, level: LogLevel = 'info'): void {
  // Ensure output channel is initialized
  if (!outputChannel) {
    initialize();
  }

  try {
    const timestamp = new Date().toISOString();
    const logEntry = `[${timestamp}] [${level.toUpperCase()}] ${message}`;
    outputChannel!.appendLine(logEntry);

    // Also log to console for debugging
    console.log(`ContextCore: ${logEntry}`);
  } catch (error) {
    console.error('Failed to write to output channel:', error);
  }
}

/**
 * Shows an error notification to the user and logs the error
 * @param message Error message to display and log
 */
export function showError(message: string): void {
  log(message, 'error');
  
  // Show error notification without blocking
  vscode.window.showErrorMessage(`ContextCore: ${message}`).then(
    undefined, // Success handler not needed
    error => console.error('Failed to show error message:', error)
  );
}

/**
 * Disposes the output channel and cleans up resources
 */
export function dispose(): void {
  if (outputChannel) {
    try {
      outputChannel.dispose();
    } catch (error) {
      console.error('Error disposing output channel:', error);
    } finally {
      outputChannel = undefined;
    }
  }
}


/**
 * Cache entry containing value and expiration time
 */
export interface CacheEntry<T> {
  /** Cached value */
  value: T;
  /** Expiration timestamp (milliseconds since epoch) */
  expiresAt: number;
}

/**
 * Generic cache implementation with TTL support and automatic cleanup
 */
export class Cache<T> {
  private readonly store = new Map<string, CacheEntry<T>>();
  private readonly defaultTtlMs: number;
  private cleanupTimer?: NodeJS.Timeout;

  /**
   * Creates a new cache instance
   * @param defaultTtlMs Default time-to-live in milliseconds
   */
  constructor(defaultTtlMs: number = 300000) { // Default 5 minutes
    this.defaultTtlMs = defaultTtlMs;
    
    // Schedule periodic cleanup every minute
    this.cleanupTimer = setInterval(() => {
      this.cleanup();
    }, 60000);
  }

  /**
   * Retrieves a value from the cache if it exists and hasn't expired
   * @param key Cache key
   * @returns Cached value or undefined if not found/expired
   */
  get(key: string): T | undefined {
    const entry = this.store.get(key);
    
    if (!entry) {
      return undefined;
    }

    const now = Date.now();
    if (entry.expiresAt <= now) {
      // Entry expired, remove it
      this.store.delete(key);
      return undefined;
    }

    return entry.value;
  }

  /**
   * Stores a value in the cache with optional TTL override
   * @param key Cache key
   * @param value Value to cache
   * @param ttlMs Time-to-live in milliseconds (optional, uses default if not provided)
   */
  set(key: string, value: T, ttlMs?: number): void {
    const ttl = ttlMs ?? this.defaultTtlMs;
    const expiresAt = Date.now() + ttl;
    
    this.store.set(key, { value, expiresAt });
  }

  /**
   * Removes a specific entry from the cache
   * @param key Cache key to invalidate
   */
  invalidate(key: string): void {
    this.store.delete(key);
  }

  /**
   * Clears all entries from the cache
   */
  clear(): void {
    this.store.clear();
  }

  /**
   * Returns the current number of entries in the cache
   * @returns Cache size
   */
  size(): number {
    return this.store.size;
  }

  /**
   * Disposes the cache and clears the cleanup timer
   */
  dispose(): void {
    if (this.cleanupTimer) {
      clearInterval(this.cleanupTimer);
      this.cleanupTimer = undefined;
    }
    this.clear();
  }

  /**
   * Removes expired entries from the cache (private cleanup method)
   */
  private cleanup(): void {
    const now = Date.now();
    const keysToDelete: string[] = [];

    // Collect expired keys
    for (const [key, entry] of this.store.entries()) {
      if (entry.expiresAt <= now) {
        keysToDelete.push(key);
      }
    }

    // Remove expired entries
    keysToDelete.forEach(key => this.store.delete(key));

    // Log cleanup activity if significant
    if (keysToDelete.length > 0) {
      console.log(`ContextCore Cache: Cleaned up ${keysToDelete.length} expired entries`);
    }
  }
}
