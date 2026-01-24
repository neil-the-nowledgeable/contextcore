extensions/vscode/
├── package.json
├── tsconfig.json
├── .eslintrc.json
├── .vscodeignore
├── README.md
└── src/
    └── extension.ts



### tsconfig.json



### .eslintrc.json



### .vscodeignore



### README.md



### Settings Reference

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `contextcore.kubeconfig` | string | `""` | Path to kubeconfig file for Kubernetes integration |
| `contextcore.namespace` | string | `"default"` | Default Kubernetes namespace for operations |
| `contextcore.showInlineHints` | boolean | `true` | Show inline hints and decorations in editor |
| `contextcore.refreshInterval` | number | `30` | Auto-refresh interval in seconds (5-300) |

## Usage

### Getting Started
1. Open a workspace containing a `.contextcore/` directory or `projectcontext.yaml` file
2. The ContextCore icon will appear in the Activity Bar
3. Click to open the ContextCore views
4. Configure Kubernetes connection if needed

### Commands

Access these commands via Command Palette (Ctrl+Shift+P):

- `ContextCore: Refresh Views` - Manually refresh all project data
- `ContextCore: Show Impact Analysis` - Display impact analysis for current context
- `ContextCore: Open Dashboard` - Launch the ContextCore web dashboard  
- `ContextCore: Show Risks` - Focus on risks view with detailed information

### Views

#### Project View
- Displays hierarchical project structure
- Shows component relationships
- Provides quick navigation to project files

#### Requirements View  
- Lists all project requirements
- Shows requirement status and progress
- Links requirements to implementation

#### Risks View
- Monitors project risks and issues
- Provides risk assessment and mitigation strategies
- Tracks risk resolution progress

## Project Structure

ContextCore projects should contain either:

### Option 1: .contextcore directory



### Option 2: projectcontext.yaml file



## Development

### Prerequisites
- Node.js 18+
- VSCode 1.85.0+
- TypeScript 5.3+

### Build Commands



## Requirements

- VSCode 1.85.0 or higher
- Node.js 18+ (for development)
- Optional: Kubernetes cluster access for live data

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable  
5. Submit a pull request

## Support

- 📖 [Documentation](https://github.com/contextcore/contextcore)
- 🐛 [Report Issues](https://github.com/contextcore/contextcore/issues)
- 💬 [Discussions](https://github.com/contextcore/contextcore/discussions)

## License

MIT License - see [LICENSE](LICENSE) file for details.
