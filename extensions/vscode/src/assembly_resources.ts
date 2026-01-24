
### resources/icons/red-circle.svg



### resources/icons/orange-circle.svg



### resources/icons/yellow-circle.svg



### README.md



### From VS Code Marketplace
1. Open VS Code
2. Navigate to Extensions (Ctrl+Shift+X)
3. Search for "ContextCore"
4. Click Install

### Build from Source
See the Development section below for detailed instructions.

## Configuration

Configure ContextCore through VS Code settings (File > Preferences > Settings):

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `contextcore.kubeconfig` | string | `""` | Path to kubeconfig file for Kubernetes integration |
| `contextcore.namespace` | string | `"default"` | Kubernetes namespace to monitor |
| `contextcore.showInlineHints` | boolean | `true` | Show SLO requirements as inline hints |
| `contextcore.refreshInterval` | number | `30` | Context refresh interval in seconds |
| `contextcore.grafanaUrl` | string | `"http://localhost:3000"` | Base URL for Grafana dashboards |
| `contextcore.logLevel` | string | `"info"` | Logging level (error, warn, info, debug) |
| `contextcore.enableGutterIcons` | boolean | `true` | Show risk indicator icons in editor gutter |

## Usage

### Getting Started
1. Open a workspace containing `.contextcore` directory or `projectcontext.yaml` file
2. Click the ContextCore icon in the Activity Bar
3. View project context in the side panel
4. Use Command Palette for additional actions

### Context Panel Features
- **Business Information**: Project criticality, impact, and stakeholder details
- **Active Risks**: Prioritized list with affected components
- **Requirements**: Technical and business requirements tracking
- **Performance Targets**: SLOs, SLIs, and monitoring dashboard links
- **Dependencies**: Service dependencies and integration points

### Available Commands
Access through Command Palette (Ctrl+Shift+P):

- `ContextCore: Refresh Context` - Manually refresh project context
- `ContextCore: Impact Analysis` - Analyze potential impact of current changes
- `ContextCore: Open Grafana Dashboard` - Open monitoring dashboards
- `ContextCore: Show Risks` - Filter and display risk information
- `ContextCore: Toggle Inline Hints` - Toggle SLO hint visibility

### Keyboard Shortcuts
- `Ctrl+Alt+C` - Open ContextCore panel
- `Ctrl+Alt+R` - Refresh context data
- `F12` (in context panel) - Open Grafana dashboard

## Project Context File Format

ContextCore requires a `projectcontext.yaml` or `.contextcore/context.yaml` file:




## Development

### Prerequisites
- Node.js 18.0.0 or higher
- npm 9.0.0 or higher
- Visual Studio Code 1.85.0 or higher

### Setup Development Environment



### Running in Development Mode
1. Open the project in Visual Studio Code
2. Press `F5` to launch Extension Development Host
3. Test the extension in the new window

### Building VSIX Package



### Testing



### Code Quality Standards
- TypeScript strict mode enabled
- ESLint configuration for VS Code extensions
- Prettier for code formatting
- Jest for unit testing
- 100% TypeScript coverage (no `any` types)

## Requirements

### Runtime Requirements
- Visual Studio Code 1.85.0 or higher
- Optional: Kubernetes cluster for live context
- Optional: Grafana instance for dashboard integration

### Development Requirements
- Node.js 18+ and npm 9+
- TypeScript 5.0+
- VS Code Extension Development tools

## Troubleshooting

### Common Issues

**Extension Not Loading**
- Verify `projectcontext.yaml` or `.contextcore/context.yaml` exists
- Check Output panel (View > Output) and select "ContextCore"
- Ensure file format is valid YAML

**Kubernetes Integration Problems**
- Verify kubeconfig path in settings
- Check cluster connectivity and permissions
- Ensure specified namespace exists
- Review authentication credentials

**Performance Issues**
- Increase refresh interval in settings
- Disable inline hints if editor becomes slow
- Set log level to "warn" or "error" to reduce output
- Check for large context files

**Risk Indicators Not Showing**
- Verify `enableGutterIcons` setting is enabled
- Check that risk file paths match actual file structure
- Ensure affected files exist in the workspace

### Debug Mode
Enable debug logging by setting `contextcore.logLevel` to `"debug"` and check the Output panel for detailed information.

## Contributing

We welcome contributions! Please:
1. Read our [Contributing Guidelines](CONTRIBUTING.md)
2. Follow the [Code of Conduct](CODE_OF_CONDUCT.md)
3. Submit pull requests with tests
4. Update documentation as needed

### Development Workflow
1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run `npm run test` and `npm run lint`
5. Submit a pull request

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and release notes.

## License

This extension is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Support

- **GitHub Issues**: [Report bugs or request features](https://github.com/your-org/contextcore-vscode/issues)
- **Documentation**: [Wiki and guides](https://github.com/your-org/contextcore-vscode/wiki)
- **Discussions**: [Community forum](https://github.com/your-org/contextcore-vscode/discussions)

---

**Note**: ContextCore requires project context configuration to function properly. See the Project Context File Format section for setup instructions.
