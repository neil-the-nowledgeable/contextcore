# ContextCore Diagrams

This directory contains D2 declarative diagrams for ContextCore documentation.

## Why D2?

We chose [D2 (Declarative Diagramming)](https://d2lang.com/) for several reasons:

| Criteria | D2 | Mermaid | PlantUML |
|----------|-----|---------|----------|
| **Syntax readability** | ✅ YAML-like, clean | ⚠️ Compact but dense | ❌ Verbose |
| **Git diff friendliness** | ✅ Excellent | ⚠️ Okay | ❌ Poor |
| **Auto-layout** | ✅ Excellent | ⚠️ Basic | ⚠️ Manual tuning |
| **Modern aesthetics** | ✅ Production-ready themes | ⚠️ Generic | ⚠️ Dated |
| **Localization** | ✅ Unicode/emoji native | ✅ Good | ⚠️ Encoding issues |
| **License** | MPL 2.0 | MIT | GPL 3.0 |

## Rendering Diagrams

### Option 1: D2 CLI (Recommended)

```bash
# Install D2
# macOS
brew install d2

# Linux
curl -fsSL https://d2lang.com/install.sh | sh

# Render to SVG
d2 contextcore-architecture.d2 contextcore-architecture.svg

# Render with a theme (102 = Grape soda)
d2 -t 102 tasks-as-spans-concept.d2 tasks-as-spans-concept.svg

# Watch mode for live editing
d2 --watch contextcore-architecture.d2 contextcore-architecture.svg
```

### Option 2: VS Code Extension

Install the [D2 extension](https://marketplace.visualstudio.com/items?itemName=Terrastruct.d2) for live preview.

### Option 3: Online Playground

Paste diagram source at [play.d2lang.com](https://play.d2lang.com/)

### Option 4: Kroki (Self-hosted)

If using Kroki for unified diagram rendering:

```bash
curl -X POST https://kroki.io/d2/svg \
  -H 'Content-Type: text/plain' \
  --data-binary @contextcore-architecture.d2 \
  -o contextcore-architecture.svg
```

## Available Diagrams

| File | Purpose | Best For |
|------|---------|----------|
| `contextcore-architecture.d2` | Full system architecture | README, docs home |
| `tasks-as-spans-concept.d2` | Core insight explanation | ADRs, concept docs |

## Theme Reference

D2 includes several production-ready themes:

| ID | Name | Best For |
|----|------|----------|
| 0 | Default | General use |
| 1 | Neutral grey | Technical docs |
| 100 | Origami | Light, friendly |
| 101 | Flagship Terrastruct | Bold, professional |
| 102 | Grape soda | Creative, distinctive |
| 103 | Aubergine | Dark, elegant |
| 200 | Terminal | Hacker aesthetic |
| 300-302 | Cool classics | Conservative |

Preview all themes: `d2 --theme 102 diagram.d2 output.svg`

## Syntax Quick Reference

```d2
# Shapes
server: Backend API
db: Database {
  shape: cylinder
}

# Connections
server -> db: queries

# Nesting
group: My Group {
  child1
  child2
}

# Styling
styled: Styled Box {
  style: {
    fill: "#2D3748"
    stroke: "#ED8936"
    font-color: "#F7FAFC"
    border-radius: 8
  }
}

# Markdown labels
docs: |md
  ## Title
  *Italic* and **bold**
|

# Animations (for SVG)
a -> b: flow {
  style.animated: true
}
```

## Hugo/GitLab Pages Integration

For Hugo sites, use the [D2 shortcode](https://d2lang.com/tour/hugo) or pre-render diagrams in CI:

```yaml
# .gitlab-ci.yml
render-diagrams:
  image: terrastruct/d2
  script:
    - d2 docs/diagrams/*.d2 docs/static/images/
  artifacts:
    paths:
      - docs/static/images/*.svg
```

## Contributing

When adding new diagrams:

1. Use descriptive filenames: `feature-name-concept.d2`
2. Add a title block at the top of the diagram
3. Include render instructions as a comment
4. Update this README with the new diagram
5. Commit both `.d2` source and rendered `.svg`
