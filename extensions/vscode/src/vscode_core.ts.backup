// src/extension.ts
import * as vscode from 'vscode';
import * as logger from './logger';
import * as config from './config';

/**
 * Extension activation entry point.
 * Called when the extension is activated by VSCode.
 */
export function activate(context: vscode.ExtensionContext): void {
    try {
        // Initialize logger first to capture all subsequent operations
        logger.initialize();
        logger.log('ContextCore extension activating...', 'info');

        // Register logger cleanup on deactivation
        context.subscriptions.push({
            dispose: () => logger.dispose()
        });

        // Set up configuration change monitoring
        const configWatcher = config.onConfigChange(() => {
            logger.log('ContextCore configuration changed', 'info');
        });
        context.subscriptions.push(configWatcher);

        // Extension successfully activated
        logger.log('ContextCore extension activated', 'info');
        
    } catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        logger.showError(`Failed to activate ContextCore extension: ${errorMessage}`);
        throw error; // Re-throw to ensure VSCode knows activation failed
    }
}

/**
 * Extension deactivation entry point.
 * Called when the extension is deactivated by VSCode.
 * Cleanup is handled automatically via context.subscriptions.
 */
export function deactivate(): void {
    // All cleanup is handled via context.subscriptions disposables
    // No explicit cleanup needed here
}


// src/types.ts
/**
 * Core project context structure containing metadata and specifications.
 */
export interface ProjectContext {
    /** Project identification and metadata */
    metadata: ProjectMetadata;
    /** Detailed project specifications and requirements */
    spec: ProjectContextSpec;
}

/**
 * Project metadata for identification and ownership.
 */
export interface ProjectMetadata {
    /** Unique project identifier */
    name: string;
    /** Project namespace for organization */
    namespace: string;
}

/**
 * Complete project context specifications.
 */
export interface ProjectContextSpec {
    /** Project description or identifier */
    project: string;
    /** Business context and organizational details */
    business: BusinessContext;
    /** Technical and performance requirements */
    requirements: Requirements;
    /** Project risks and mitigation strategies */
    risks: Risk[];
    /** Deployment and infrastructure targets */
    targets: Target[];
    /** Design documentation and contracts */
    design: Design;
}

/**
 * Business context including organizational details.
 */
export interface BusinessContext {
    /** Business criticality level */
    criticality?: string;
    /** Business value description */
    value?: string;
    /** Project owner or responsible party */
    owner?: string;
    /** Cost center for billing and tracking */
    costCenter?: string;
}

/**
 * Technical and performance requirements.
 */
export interface Requirements {
    /** Required system availability (e.g., "99.9%") */
    availability?: string;
    /** 99th percentile latency requirement */
    latencyP99?: string;
    /** 50th percentile latency requirement */
    latencyP50?: string;
    /** Required throughput capacity */
    throughput?: string;
    /** Acceptable error budget */
    errorBudget?: string;
}

/**
 * Project risk with priority and mitigation details.
 */
export interface Risk {
    /** Type or category of risk */
    type: string;
    /** Risk priority level */
    priority: string;
    /** Detailed risk description */
    description: string;
    /** Scope or area affected by the risk */
    scope?: string;
    /** Mitigation strategy or plan */
    mitigation?: string;
}

/**
 * Deployment or infrastructure target specification.
 */
export interface Target {
    /** Target type or kind (e.g., "deployment", "service") */
    kind: string;
    /** Target name or identifier */
    name: string;
    /** Target namespace for organization */
    namespace?: string;
}

/**
 * Design documentation and API specifications.
 */
export interface Design {
    /** Architecture Decision Record reference */
    adr?: string;
    /** General design documentation reference */
    doc?: string;
    /** API contract or specification reference */
    apiContract?: string;
}


// src/config.ts
import * as vscode from 'vscode';

/**
 * Configuration keys used throughout the ContextCore extension.
 */
export const CONFIG_KEYS = {
    /** Logging level configuration */
    logLevel: 'contextcore.logLevel',
    /** Notification preferences */
    notifications: 'contextcore.notifications'
} as const;

/**
 * Retrieves a configuration value from VSCode settings.
 * 
 * @template T The expected type of the configuration value
 * @param key Configuration key to retrieve
 * @param defaultValue Default value if configuration key is not found
 * @returns The configuration value or default value
 */
export function getConfig<T>(key: string, defaultValue?: T): T {
    const config = vscode.workspace.getConfiguration();
    return config.get<T>(key, defaultValue as T);
}

/**
 * Registers a callback to be executed when configuration changes.
 * 
 * @param callback Function to execute when configuration changes
 * @returns Disposable to unregister the callback
 */
export function onConfigChange(callback: () => void): vscode.Disposable {
    return vscode.workspace.onDidChangeConfiguration(event => {
        // Check if any of our configuration keys were affected
        const affectedKeys = Object.values(CONFIG_KEYS);
        const isAffected = affectedKeys.some(key => event.affectsConfiguration(key));
        
        if (isAffected) {
            callback();
        }
    });
}


// src/logger.ts
import * as vscode from 'vscode';

/**
 * Output channel for extension logging.
 */
let outputChannel: vscode.OutputChannel | undefined;

/**
 * Log levels supported by the logger.
 */
export type LogLevel = 'info' | 'warn' | 'error';

/**
 * Initializes the logger with a VSCode output channel.
 * Must be called before using other logging functions.
 */
export function initialize(): void {
    if (!outputChannel) {
        outputChannel = vscode.window.createOutputChannel('ContextCore');
    }
}

/**
 * Logs a message to the output channel with timestamp and level.
 * 
 * @param message Message to log
 * @param level Log level (defaults to 'info')
 */
export function log(message: string, level: LogLevel = 'info'): void {
    if (!outputChannel) {
        console.warn('Logger not initialized, call initialize() first');
        return;
    }
    
    const timestamp = new Date().toISOString();
    const formattedMessage = `${timestamp} [${level.toUpperCase()}] ${message}`;
    
    outputChannel.appendLine(formattedMessage);
    
    // Also log to console for debugging in development
    if (process.env.NODE_ENV === 'development') {
        console.log(formattedMessage);
    }
}

/**
 * Shows an error message to the user via notification and logs it.
 * 
 * @param message Error message to display and log
 */
export function showError(message: string): void {
    // Log the error first
    log(message, 'error');
    
    // Show user notification
    vscode.window.showErrorMessage(`ContextCore: ${message}`);
}

/**
 * Disposes of the logger resources.
 * Called automatically during extension deactivation.
 */
export function dispose(): void {
    if (outputChannel) {
        outputChannel.dispose();
        outputChannel = undefined;
    }
}
