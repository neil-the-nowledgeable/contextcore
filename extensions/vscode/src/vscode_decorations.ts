// src/ui/decorations/decorationProvider.ts
import * as vscode from 'vscode';
import { ContextMapper } from '../../core/contextMapper';
import { findHttpHandlers, findDatabaseQueries, findExternalCalls, buildSloDecoration } from './sloDecorations';
import { isFileInRiskScope, buildRiskDecoration } from './riskDecorations';

/**
 * Manages editor decorations for inline SLO hints and risk indicators
 */
export class DecorationProvider implements vscode.Disposable {
    private readonly sloDecorationType: vscode.TextEditorDecorationType;
    private readonly riskDecorationType: vscode.TextEditorDecorationType;
    private readonly disposables: vscode.Disposable[] = [];
    private updateTimeout: NodeJS.Timeout | undefined;

    constructor(private readonly contextMapper: ContextMapper) {
        this.sloDecorationType = vscode.window.createTextEditorDecorationType({
            after: {
                color: new vscode.ThemeColor('editorCodeLens.foreground'),
                fontStyle: 'italic',
                margin: '0 0 0 2em'
            }
        });

        this.riskDecorationType = vscode.window.createTextEditorDecorationType({});

        this.registerEventListeners();
        this.updateActiveEditor();
    }

    /**
     * Updates decorations for the given editor
     */
    public async updateDecorations(editor: vscode.TextEditor): Promise<void> {
        if (!this.isInlineHintsEnabled()) {
            this.clearDecorations(editor);
            return;
        }

        try {
            const document = editor.document;
            if (!this.isSupportedLanguage(document.languageId)) {
                this.clearDecorations(editor);
                return;
            }

            // Find relevant code patterns
            const httpHandlers = findHttpHandlers(document);
            const dbQueries = findDatabaseQueries(document);
            const externalCalls = findExternalCalls(document);

            // Get SLO requirements from context mapper
            const filePath = document.uri.fsPath;
            const requirements = await this.contextMapper.getRequirements(filePath);

            // Build and apply SLO decorations
            const sloDecorations = buildSloDecoration([...httpHandlers, ...dbQueries, ...externalCalls], requirements);
            editor.setDecorations(this.sloDecorationType, sloDecorations);

            // Check for risk scope and apply risk decorations
            const risks = await this.contextMapper.getRisks();
            const fileRisk = isFileInRiskScope(filePath, risks);
            const riskDecorations = fileRisk ? buildRiskDecoration(fileRisk) : [];
            editor.setDecorations(this.riskDecorationType, riskDecorations);

        } catch (error) {
            console.error('Error updating decorations:', error);
            this.clearDecorations(editor);
        }
    }

    public dispose(): void {
        if (this.updateTimeout) {
            clearTimeout(this.updateTimeout);
        }
        this.sloDecorationType.dispose();
        this.riskDecorationType.dispose();
        this.disposables.forEach(d => d.dispose());
    }

    private registerEventListeners(): void {
        this.disposables.push(
            vscode.window.onDidChangeActiveTextEditor(editor => {
                if (editor) {
                    this.scheduleUpdate(editor);
                }
            }),
            vscode.workspace.onDidChangeTextDocument(event => {
                const editor = vscode.window.activeTextEditor;
                if (editor && editor.document === event.document) {
                    this.scheduleUpdate(editor);
                }
            }),
            vscode.workspace.onDidChangeConfiguration(event => {
                if (event.affectsConfiguration('contextcore.showInlineHints')) {
                    this.updateAllVisibleEditors();
                }
            })
        );
    }

    private scheduleUpdate(editor: vscode.TextEditor): void {
        if (this.updateTimeout) {
            clearTimeout(this.updateTimeout);
        }
        this.updateTimeout = setTimeout(() => {
            this.updateDecorations(editor);
        }, 300); // Debounce updates
    }

    private updateActiveEditor(): void {
        const editor = vscode.window.activeTextEditor;
        if (editor) {
            this.updateDecorations(editor);
        }
    }

    private updateAllVisibleEditors(): void {
        vscode.window.visibleTextEditors.forEach(editor => {
            this.updateDecorations(editor);
        });
    }

    private isInlineHintsEnabled(): boolean {
        const config = vscode.workspace.getConfiguration('contextcore');
        return config.get<boolean>('showInlineHints', true);
    }

    private isSupportedLanguage(languageId: string): boolean {
        return ['python', 'typescript', 'javascript', 'go'].includes(languageId);
    }

    private clearDecorations(editor: vscode.TextEditor): void {
        editor.setDecorations(this.sloDecorationType, []);
        editor.setDecorations(this.riskDecorationType, []);
    }
}

// src/ui/decorations/sloDecorations.ts
import * as vscode from 'vscode';

export interface CodePattern {
    range: vscode.Range;
    type: 'http' | 'database' | 'external';
    method?: string;
    endpoint?: string;
}

export interface Requirements {
    latencyP99: number;
    latencyP95: number;
    errorRate: number;
    availability: number;
}

/**
 * Finds HTTP handler patterns in the document
 */
export function findHttpHandlers(document: vscode.TextDocument): CodePattern[] {
    const patterns: CodePattern[] = [];
    const text = document.getText();
    const languageId = document.languageId;

    try {
        switch (languageId) {
            case 'python':
                patterns.push(...findPythonHttpHandlers(document, text));
                break;
            case 'typescript':
            case 'javascript':
                patterns.push(...findTypeScriptHttpHandlers(document, text));
                break;
            case 'go':
                patterns.push(...findGoHttpHandlers(document, text));
                break;
        }
    } catch (error) {
        console.error('Error finding HTTP handlers:', error);
    }

    return patterns;
}

/**
 * Finds database query patterns in the document
 */
export function findDatabaseQueries(document: vscode.TextDocument): CodePattern[] {
    const patterns: CodePattern[] = [];
    const text = document.getText();

    try {
        // Generic SQL query patterns
        const sqlRegex = /(?:SELECT|INSERT|UPDATE|DELETE|CREATE|DROP)\s+.*?(?:FROM|INTO|TABLE)\s+\w+/gi;
        const matches = text.matchAll(sqlRegex);

        for (const match of matches) {
            if (match.index !== undefined) {
                const start = document.positionAt(match.index);
                const end = document.positionAt(match.index + match[0].length);
                patterns.push({
                    range: new vscode.Range(start, end),
                    type: 'database'
                });
            }
        }
    } catch (error) {
        console.error('Error finding database queries:', error);
    }

    return patterns;
}

/**
 * Finds external API call patterns in the document
 */
export function findExternalCalls(document: vscode.TextDocument): CodePattern[] {
    const patterns: CodePattern[] = [];
    const text = document.getText();

    try {
        // Common HTTP client patterns
        const httpRegex = /(?:fetch|axios|requests\.(?:get|post|put|delete)|http\.(?:get|post))\s*\(/gi;
        const matches = text.matchAll(httpRegex);

        for (const match of matches) {
            if (match.index !== undefined) {
                const start = document.positionAt(match.index);
                const end = document.positionAt(match.index + match[0].length);
                patterns.push({
                    range: new vscode.Range(start, end),
                    type: 'external'
                });
            }
        }
    } catch (error) {
        console.error('Error finding external calls:', error);
    }

    return patterns;
}

/**
 * Builds decoration options for SLO requirements
 */
export function buildSloDecoration(patterns: CodePattern[], requirements?: Requirements): vscode.DecorationOptions[] {
    if (!requirements || patterns.length === 0) {
        return [];
    }

    return patterns.map(pattern => {
        const sloText = formatSloText(pattern.type, requirements);
        return {
            range: new vscode.Range(pattern.range.end, pattern.range.end),
            renderOptions: {
                after: {
                    contentText: sloText
                }
            }
        };
    });
}

// Private helper functions
function findPythonHttpHandlers(document: vscode.TextDocument, text: string): CodePattern[] {
    const patterns: CodePattern[] = [];
    
    // Flask/FastAPI patterns
    const flaskRegex = /@app\.route\s*\(\s*['"]([^'"]+)['"]/g;
    const fastApiRegex = /@app\.(get|post|put|delete)\s*\(\s*['"]([^'"]+)['"]/g;
    const defRegex = /def\s+(get_|post_|put_|delete_)\w*/g;

    [flaskRegex, fastApiRegex, defRegex].forEach(regex => {
        const matches = text.matchAll(regex);
        for (const match of matches) {
            if (match.index !== undefined) {
                const start = document.positionAt(match.index);
                const end = document.positionAt(match.index + match[0].length);
                patterns.push({
                    range: new vscode.Range(start, end),
                    type: 'http',
                    method: match[1] || 'unknown',
                    endpoint: match[2] || ''
                });
            }
        }
    });

    return patterns;
}

function findTypeScriptHttpHandlers(document: vscode.TextDocument, text: string): CodePattern[] {
    const patterns: CodePattern[] = [];
    
    // Express.js patterns
    const expressRegex = /(?:app|router)\.(get|post|put|delete)\s*\(\s*['"]([^'"]+)['"]/g;
    const matches = text.matchAll(expressRegex);

    for (const match of matches) {
        if (match.index !== undefined) {
            const start = document.positionAt(match.index);
            const end = document.positionAt(match.index + match[0].length);
            patterns.push({
                range: new vscode.Range(start, end),
                type: 'http',
                method: match[1],
                endpoint: match[2]
            });
        }
    }

    return patterns;
}

function findGoHttpHandlers(document: vscode.TextDocument, text: string): CodePattern[] {
    const patterns: CodePattern[] = [];
    
    // Go HTTP patterns
    const handlerRegex = /func\s+\w*[Hh]andler?\w*\s*\(/g;
    const handleFuncRegex = /http\.HandleFunc\s*\(/g;

    [handlerRegex, handleFuncRegex].forEach(regex => {
        const matches = text.matchAll(regex);
        for (const match of matches) {
            if (match.index !== undefined) {
                const start = document.positionAt(match.index);
                const end = document.positionAt(match.index + match[0].length);
                patterns.push({
                    range: new vscode.Range(start, end),
                    type: 'http'
                });
            }
        }
    });

    return patterns;
}

function formatSloText(type: string, requirements: Requirements): string {
    switch (type) {
        case 'http':
            return ` // SLO: P99 < ${requirements.latencyP99}ms, Errors < ${requirements.errorRate}%`;
        case 'database':
            return ` // SLO: P95 < ${requirements.latencyP95}ms`;
        case 'external':
            return ` // SLO: P99 < ${requirements.latencyP99}ms, Availability > ${requirements.availability}%`;
        default:
            return ` // SLO: P99 < ${requirements.latencyP99}ms`;
    }
}

// src/ui/decorations/riskDecorations.ts
import * as vscode from 'vscode';
import * as path from 'path';

export interface Risk {
    id: string;
    priority: 'P1' | 'P2' | 'P3';
    title: string;
    description: string;
    files: string[];
    impact: string;
}

/**
 * Checks if a file is in the scope of any risk
 */
export function isFileInRiskScope(filePath: string, risks: Risk[]): Risk | undefined {
    const normalizedPath = path.normalize(filePath);
    
    return risks.find(risk => 
        risk.files.some(riskFile => {
            const normalizedRiskFile = path.normalize(riskFile);
            return normalizedPath.includes(normalizedRiskFile) || 
                   normalizedRiskFile.includes(normalizedPath);
        })
    );
}

/**
 * Builds risk decoration for gutter display
 */
export function buildRiskDecoration(risk: Risk): vscode.DecorationOptions[] {
    const iconUri = getRiskIconUri(risk.priority);
    const hoverMessage = new vscode.MarkdownString(
        `**${risk.priority} Risk: ${risk.title}**\n\n${risk.description}\n\n*Impact: ${risk.impact}*`
    );

    return [{
        range: new vscode.Range(0, 0, 0, 0),
        hoverMessage,
        renderOptions: {
            gutterIconPath: iconUri,
            gutterIconSize: 'contain'
        }
    }];
}

/**
 * Gets the appropriate icon URI for the risk priority
 */
function getRiskIconUri(priority: 'P1' | 'P2' | 'P3'): vscode.Uri {
    const extensionPath = vscode.extensions.getExtension('contextcore')?.extensionPath || '';
    const iconMap = {
        'P1': 'red-circle.svg',
        'P2': 'orange-circle.svg',
        'P3': 'yellow-circle.svg'
    };
    
    return vscode.Uri.file(path.join(extensionPath, 'resources', 'icons', iconMap[priority]));
}
