"""
Markdown-to-Capability Parser.

Parses SKILL.md files into structured capabilities for OTel emission.
Implements the hybrid extraction strategy:
- All H2 sections become capabilities
- Important H3 subsections become separate capabilities

Uses progressive disclosure:
- Summaries (~50 tokens) stored as span attributes
- Full content referenced via Evidence links
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from contextcore.skill.models import (
    Audience,
    CapabilityCategory,
    Evidence,
    EvidenceType,
    SkillType,
)
from contextcore.knowledge.models import (
    KnowledgeCapability,
    KnowledgeCategory,
    KnowledgeManifest,
    Section,
    SUBSECTION_WHITELIST,
    get_knowledge_category,
)


# Stop words to filter from triggers
STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
    "be", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "shall", "can", "this",
    "that", "these", "those", "it", "its", "use", "using", "when", "how",
}


def estimate_tokens(text: str) -> int:
    """Estimate token count (rough: 1 token ≈ 4 chars)."""
    return len(text) // 4


def slugify(text: str) -> str:
    """Convert text to snake_case identifier."""
    # Remove special characters, keep alphanumeric and spaces
    text = re.sub(r"[^\w\s-]", "", text.lower())
    # Replace spaces/hyphens with underscores
    text = re.sub(r"[-\s]+", "_", text)
    # Remove leading/trailing underscores
    return text.strip("_")


def compress_to_summary(content: str, max_sentences: int = 2) -> str:
    """
    Compress content to 1-2 sentence summary.

    Extracts the first meaningful sentences, skipping code blocks.
    """
    lines = content.split("\n")
    sentences = []

    in_code_block = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Skip headings, empty lines, list markers at start
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("|"):
            continue

        # Remove markdown formatting
        cleaned = re.sub(r"\*\*|__|\*|_|`", "", stripped)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)  # [text](url) -> text

        if cleaned and len(cleaned) > 20:
            sentences.append(cleaned)
            if len(sentences) >= max_sentences:
                break

    if not sentences:
        # Fallback: use first non-empty, non-heading line
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped[:200]
        return "No summary available."

    return " ".join(sentences)[:500]


class MarkdownCapabilityParser:
    """
    Parse SKILL.md files into structured capabilities.

    Implements hybrid extraction:
    - All H2 sections become capabilities
    - H3 subsections become capabilities if:
      - In SUBSECTION_WHITELIST
      - Have >50 lines
      - Contain code blocks
      - Contain tables

    Example:
        parser = MarkdownCapabilityParser(Path("~/.claude/skills/dev-tour-guide"))
        manifest, capabilities = parser.parse()
    """

    def __init__(self, skill_path: Path):
        """
        Initialize parser with skill directory or SKILL.md path.

        Args:
            skill_path: Path to skill directory or SKILL.md file
        """
        self.skill_path = Path(skill_path).expanduser()

        if self.skill_path.is_dir():
            self.skill_file = self.skill_path / "SKILL.md"
            self.skill_id = self.skill_path.name
        else:
            self.skill_file = self.skill_path
            self.skill_id = self.skill_path.stem

        if not self.skill_file.exists():
            raise FileNotFoundError(f"SKILL.md not found: {self.skill_file}")

        self.content = self.skill_file.read_text()
        self.lines = self.content.splitlines()

    def parse(self) -> tuple[KnowledgeManifest, list[KnowledgeCapability]]:
        """
        Parse markdown into manifest and capabilities.

        Returns:
            Tuple of (KnowledgeManifest, list of KnowledgeCapability)
        """
        # 1. Extract YAML frontmatter
        frontmatter, content_start = self._extract_frontmatter()

        # 2. Build section tree (H2 -> H3 hierarchy)
        sections = self._build_section_tree(content_start)

        # 3. Extract capabilities using hybrid rules
        capabilities = []
        capability_refs = []

        for section in sections:
            # Major section capability
            cap = self._extract_capability(section)
            capabilities.append(cap)
            capability_refs.append(cap.capability_id)

            # Check subsections
            for subsection in section.subsections:
                if self._should_extract_subsection(subsection):
                    sub_cap = self._extract_capability(
                        subsection,
                        parent_section=section.heading
                    )
                    capabilities.append(sub_cap)
                    capability_refs.append(sub_cap.capability_id)

        # 4. Build manifest
        manifest = self._build_manifest(
            frontmatter=frontmatter,
            capability_refs=capability_refs,
            sections=sections,
        )

        return manifest, capabilities

    def _extract_frontmatter(self) -> tuple[dict, int]:
        """
        Extract YAML frontmatter from document.

        Returns:
            Tuple of (frontmatter dict, line number where content starts)
        """
        if not self.content.startswith("---"):
            return {}, 0

        # Find closing ---
        lines = self.lines
        end_idx = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_idx = i
                break

        if end_idx is None:
            return {}, 0

        # Parse YAML
        yaml_content = "\n".join(lines[1:end_idx])
        try:
            frontmatter = yaml.safe_load(yaml_content) or {}
        except yaml.YAMLError:
            frontmatter = {}

        return frontmatter, end_idx + 1

    def _build_section_tree(self, start_line: int = 0) -> list[Section]:
        """
        Build hierarchical section tree from markdown.

        Returns:
            List of top-level (H2) sections with nested subsections
        """
        sections = []
        current_h2: Optional[Section] = None
        current_h3: Optional[Section] = None

        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$")

        i = start_line
        while i < len(self.lines):
            line = self.lines[i]
            match = heading_pattern.match(line)

            if match:
                level = len(match.group(1))
                heading = match.group(2).strip()

                # Find where this section ends (next heading of same or higher level)
                end_line = self._find_section_end(i, level)
                section_content = "\n".join(self.lines[i:end_line])

                section = Section(
                    heading=heading,
                    level=level,
                    start_line=i + 1,  # 1-indexed for human readability
                    end_line=end_line,
                    content=section_content,
                )

                if level == 2:
                    # Save previous H2 if exists
                    if current_h2 is not None:
                        sections.append(current_h2)
                    current_h2 = section
                    current_h3 = None
                elif level == 3 and current_h2 is not None:
                    current_h2.subsections.append(section)
                    current_h3 = section
                # Level 4+ ignored for now

            i += 1

        # Don't forget last section
        if current_h2 is not None:
            sections.append(current_h2)

        return sections

    def _find_section_end(self, start: int, level: int) -> int:
        """Find line number where section ends."""
        heading_pattern = re.compile(r"^(#{1,6})\s+")

        for i in range(start + 1, len(self.lines)):
            match = heading_pattern.match(self.lines[i])
            if match:
                found_level = len(match.group(1))
                if found_level <= level:
                    return i

        return len(self.lines)

    def _should_extract_subsection(self, section: Section) -> bool:
        """
        Determine if subsection should become separate capability.

        Rules:
        1. In SUBSECTION_WHITELIST
        2. Has >50 lines
        3. Contains code blocks
        4. Contains tables
        """
        # Whitelist check (exact or partial match)
        for whitelist_heading in SUBSECTION_WHITELIST:
            if whitelist_heading.lower() in section.heading.lower():
                return True
            if section.heading.lower() in whitelist_heading.lower():
                return True

        # Size check
        if section.line_count > 50:
            return True

        # Content check
        if section.has_code_blocks and section.code_block_count >= 2:
            return True
        if section.has_tables:
            return True

        return False

    def _extract_capability(
        self,
        section: Section,
        parent_section: Optional[str] = None,
    ) -> KnowledgeCapability:
        """
        Extract capability from a section.

        Args:
            section: The Section to convert
            parent_section: Parent H2 heading if this is a subsection
        """
        # Generate capability ID
        if parent_section:
            # Subsection: combine parent and subsection names
            cap_id = slugify(f"{parent_section}_{section.heading}")[:50]
        else:
            cap_id = slugify(section.heading)[:50]

        # Determine category
        source_section = parent_section or section.heading
        knowledge_cat = get_knowledge_category(source_section)

        # Map to capability category based on knowledge category
        category_map = {
            KnowledgeCategory.INFRASTRUCTURE: CapabilityCategory.QUERY,
            KnowledgeCategory.WORKFLOW: CapabilityCategory.ACTION,
            KnowledgeCategory.SDK: CapabilityCategory.ACTION,
            KnowledgeCategory.REFERENCE: CapabilityCategory.QUERY,
            KnowledgeCategory.SECURITY: CapabilityCategory.ACTION,
            KnowledgeCategory.CONFIGURATION: CapabilityCategory.VALIDATE,
        }
        capability_cat = category_map.get(knowledge_cat, CapabilityCategory.QUERY)

        # Extract triggers
        triggers = self._extract_triggers(section)

        # Generate summary
        summary = compress_to_summary(section.content)

        # Extract references
        tools = self._extract_tools(section.content)
        ports = self._extract_ports(section.content)
        env_vars = self._extract_env_vars(section.content)
        paths = self._extract_paths(section.content)
        related_skills = self._extract_skill_refs(section.content)

        # Build evidence
        evidence = [
            Evidence(
                type=EvidenceType.DOC.value,
                ref=str(self.skill_file),
                description=f"Lines {section.start_line}-{section.end_line}: {section.heading}",
                tokens=estimate_tokens(section.content),
            )
        ]

        # Token budget
        token_budget = estimate_tokens(section.content)
        summary_tokens = estimate_tokens(summary)

        return KnowledgeCapability(
            skill_id=self.skill_id,
            skill_type=SkillType.SPECIALIST,
            capability_id=cap_id,
            capability_name=section.heading,
            category=capability_cat,
            knowledge_category=knowledge_cat,
            summary=summary,
            triggers=triggers,
            source_section=source_section,
            source_subsection=section.heading if parent_section else None,
            line_range=f"{section.start_line}-{section.end_line}",
            has_code=section.has_code_blocks,
            has_tables=section.has_tables,
            code_block_count=section.code_block_count,
            tools=tools,
            ports=ports,
            env_vars=env_vars,
            paths=paths,
            related_skills=related_skills,
            evidence=evidence,
            token_budget=token_budget,
            summary_tokens=summary_tokens,
            confidence=0.9,  # High confidence for curated documentation
            interop_human=4,
            interop_agent=5,
            audience=Audience.BOTH,
        )

    def _extract_triggers(self, section: Section) -> list[str]:
        """Extract routing keywords from section."""
        triggers = set()

        # 1. Words from heading
        heading_words = re.findall(r"\b\w+\b", section.heading.lower())
        for word in heading_words:
            if word not in STOP_WORDS and len(word) > 2:
                triggers.add(word)

        # 2. CLI commands
        cli_pattern = r"(contextcore|startd8|secrets\.sh|kubectl|helm|docker)\s+(\w+)"
        for match in re.finditer(cli_pattern, section.content, re.IGNORECASE):
            triggers.add(match.group(1).lower())
            triggers.add(f"{match.group(1).lower()}_{match.group(2).lower()}")

        # 3. Environment variables (lowercase)
        env_pattern = r"\b([A-Z][A-Z0-9_]{3,})\b"
        for match in re.finditer(env_pattern, section.content):
            var = match.group(1).lower()
            if not var.startswith("http"):  # Skip URLs
                triggers.add(var)

        # 4. Port numbers (as trigger)
        port_pattern = r"(?:localhost|127\.0\.0\.1):(\d{4,5})"
        for match in re.finditer(port_pattern, section.content):
            triggers.add(f"port_{match.group(1)}")

        # 5. Technology keywords
        tech_keywords = [
            "grafana", "prometheus", "loki", "tempo", "mimir", "pyroscope",
            "kubernetes", "k8s", "docker", "helm", "otel", "opentelemetry",
            "traceql", "promql", "logql", "python", "typescript", "swift",
            "api", "cli", "tui", "webhook", "agent", "span", "trace", "metric",
        ]
        content_lower = section.content.lower()
        for kw in tech_keywords:
            if kw in content_lower:
                triggers.add(kw)

        return sorted(list(triggers))[:20]  # Limit to 20 triggers

    def _extract_tools(self, content: str) -> list[str]:
        """Extract CLI tool references."""
        tools = set()
        patterns = [
            r"(contextcore)\s+(\w+)",
            r"(startd8)\s+(\w+)",
            r"(secrets\.sh)\s+(\w+)",
            r"(kubectl)\s+(\w+)",
            r"(helm)\s+(\w+)",
            r"(docker)\s+(\w+)",
            r"(git)\s+(\w+)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                tools.add(f"{match.group(1)} {match.group(2)}")
        return sorted(list(tools))

    def _extract_ports(self, content: str) -> list[str]:
        """Extract network port references."""
        ports = set()
        # localhost:PORT or 127.0.0.1:PORT
        for match in re.finditer(r"(?:localhost|127\.0\.0\.1):(\d{4,5})", content):
            ports.add(match.group(1))
        # port NNNN or PORT NNNN
        for match in re.finditer(r"port\s+(\d{4,5})", content, re.IGNORECASE):
            ports.add(match.group(1))
        return sorted(list(ports))

    def _extract_env_vars(self, content: str) -> list[str]:
        """Extract environment variable references."""
        env_vars = set()
        # UPPER_SNAKE_CASE that looks like env vars
        for match in re.finditer(r"\b([A-Z][A-Z0-9_]{3,}(?:_[A-Z0-9]+)+)\b", content):
            var = match.group(1)
            # Filter out common non-env patterns
            if not any(var.startswith(p) for p in ["HTTP", "URL", "API_V"]):
                env_vars.add(var)
        return sorted(list(env_vars))

    def _extract_paths(self, content: str) -> list[str]:
        """Extract file path references."""
        paths = set()
        # Paths starting with ~/ or / or ./
        path_pattern = r"[~./]+[\w./\-]+\.(sh|py|yaml|yml|json|md|ts|js)"
        for match in re.finditer(path_pattern, content):
            paths.add(match.group(0))
        return sorted(list(paths))

    def _extract_skill_refs(self, content: str) -> list[str]:
        """Extract references to other skills."""
        skills = set()
        # Pattern: "skill" or 'skill' or `skill` skill
        skill_pattern = r"[`'\"](\w+)[`'\"](?:\s+skill)"
        for match in re.finditer(skill_pattern, content, re.IGNORECASE):
            skills.add(match.group(1))
        # Pattern: skill_name skill (e.g., "o11y skill")
        skill_pattern2 = r"(?:Use\s+(?:the\s+)?)?[`']?(\w+)[`']?\s+skill"
        for match in re.finditer(skill_pattern2, content, re.IGNORECASE):
            skill = match.group(1).lower()
            if skill not in ["the", "this", "a", "an"]:
                skills.add(skill)
        return sorted(list(skills))

    def _build_manifest(
        self,
        frontmatter: dict,
        capability_refs: list[str],
        sections: list[Section],
    ) -> KnowledgeManifest:
        """Build manifest from parsed data."""
        # Extract from frontmatter
        name = frontmatter.get("name", self.skill_id)
        description = frontmatter.get("description", f"Knowledge base: {self.skill_id}")

        # Count subsections that became capabilities
        subsection_count = len(capability_refs) - len(sections)

        # Calculate token budgets
        total_tokens = estimate_tokens(self.content)
        manifest_tokens = 150  # Approximate manifest size
        compressed_tokens = sum(50 for _ in capability_refs)  # ~50 tokens per summary

        return KnowledgeManifest(
            skill_id=name,
            skill_type=SkillType.SPECIALIST,
            description=description,
            capability_refs=capability_refs,
            source_path=str(self.skill_path),
            source_file=str(self.skill_file),
            total_lines=len(self.lines),
            section_count=len(sections),
            subsection_count=subsection_count,
            has_frontmatter=bool(frontmatter),
            manifest_tokens=manifest_tokens,
            total_tokens=total_tokens,
            compressed_tokens=compressed_tokens,
        )
