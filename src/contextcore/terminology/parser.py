"""
Terminology Parser

Parse MANIFEST.yaml, _index.yaml, and definition files into structured models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from contextcore.terminology.models import (
    CategoryEntry,
    QuickLookupEntry,
    TermCategory,
    TerminologyDistinction,
    TerminologyIndex,
    TerminologyManifest,
    TerminologyTerm,
    TermNameOrigin,
    TermToAvoid,
)


class TerminologyParser:
    """
    Parse Wayfinder terminology from YAML files.

    Usage:
        parser = TerminologyParser()
        manifest, terms, distinctions, avoid = parser.parse_directory("/path/to/terminology")
    """

    def parse_directory(
        self,
        path: str | Path,
    ) -> Tuple[TerminologyManifest, List[TerminologyTerm], List[TerminologyDistinction], List[TermToAvoid]]:
        """
        Parse a terminology directory.

        Args:
            path: Path to terminology directory (containing MANIFEST.yaml)

        Returns:
            Tuple of (manifest, terms, distinctions, terms_to_avoid)
        """
        path = Path(path)

        # Parse MANIFEST.yaml
        manifest_path = path / "MANIFEST.yaml"
        if not manifest_path.exists():
            raise FileNotFoundError(f"MANIFEST.yaml not found in {path}")

        manifest = self._parse_manifest(manifest_path)
        manifest.source_path = str(path)

        # Parse _index.yaml for distinctions and avoid terms
        index_path = path / "_index.yaml"
        distinctions: List[TerminologyDistinction] = []
        avoid_terms: List[TermToAvoid] = []

        if index_path.exists():
            index = self._parse_index(index_path)
            distinctions = self._extract_distinctions(index)
            avoid_terms = self._extract_avoid_terms(index)

        # Parse all definition files
        terms: List[TerminologyTerm] = []
        definitions_path = path / "definitions"

        if definitions_path.exists():
            for yaml_file in definitions_path.glob("*.yaml"):
                term = self._parse_term(yaml_file, manifest)
                if term:
                    terms.append(term)

        # Calculate total tokens
        manifest.total_tokens = (
            manifest.manifest_tokens
            + manifest.index_tokens
            + sum(t.token_budget for t in terms)
        )

        return manifest, terms, distinctions, avoid_terms

    def _parse_manifest(self, path: Path) -> TerminologyManifest:
        """Parse MANIFEST.yaml into a TerminologyManifest."""
        with open(path) as f:
            data = yaml.safe_load(f)

        # Parse quick_lookup entries
        quick_lookup = {}
        for term_id, entry in data.get("quick_lookup", {}).items():
            quick_lookup[term_id] = QuickLookupEntry(**entry)

        # Parse categories
        categories = {}
        for cat_id, cat_data in data.get("categories", {}).items():
            terms_list = []
            for t in cat_data.get("terms", []):
                # Handle token budget with ~ prefix (YAML loads as string)
                tokens = t.get("tokens")
                if isinstance(tokens, str) and tokens.startswith("~"):
                    tokens = int(tokens[1:])
                terms_list.append(CategoryEntry(
                    id=t["id"],
                    file=t["file"],
                    tokens=tokens
                ))
            categories[cat_id] = TermCategory(
                description=cat_data.get("description", ""),
                terms=terms_list
            )

        return TerminologyManifest(
            terminology_id=data.get("terminology_id", "unknown"),
            schema_version=data.get("schema_version", "1.0.0"),
            last_updated=data.get("last_updated", "unknown"),
            status=data.get("status", "draft"),
            quick_lookup=quick_lookup,
            categories=categories,
            routing=data.get("routing", {}),
            constraints=data.get("constraints", []),
        )

    def _parse_index(self, path: Path) -> TerminologyIndex:
        """Parse _index.yaml into a TerminologyIndex."""
        with open(path) as f:
            data = yaml.safe_load(f)

        return TerminologyIndex(
            terminology_id=data.get("terminology_id", "unknown"),
            index_version=data.get("index_version", "1.0.0"),
            term_types=data.get("term_types", {}),
            distinctions=data.get("distinctions", {}),
            hierarchy=data.get("hierarchy", {}),
            anishinaabe_translations=data.get("anishinaabe_translations", {}),
            avoid=data.get("avoid", {}),
            agent_summary=data.get("agent_summary"),
        )

    def _extract_distinctions(self, index: TerminologyIndex) -> List[TerminologyDistinction]:
        """Extract distinction entries from index."""
        distinctions = []
        for dist_id, dist_data in index.distinctions.items():
            # Extract term IDs from the distinction ID (e.g., contextcore_vs_wayfinder)
            terms_involved = dist_id.replace("_vs_", ",").split(",")
            distinctions.append(TerminologyDistinction(
                id=dist_id,
                question=dist_data.get("question", ""),
                answer=dist_data.get("answer", ""),
                analogy=dist_data.get("analogy"),
                terms_involved=terms_involved,
            ))
        return distinctions

    def _extract_avoid_terms(self, index: TerminologyIndex) -> List[TermToAvoid]:
        """Extract terms to avoid from index."""
        avoid_terms = []
        for term, data in index.avoid.items():
            avoid_terms.append(TermToAvoid(
                term=term,
                reason=data.get("reason", ""),
                alternatives=data.get("alternatives", []),
            ))
        return avoid_terms

    def _parse_term(self, path: Path, manifest: TerminologyManifest) -> Optional[TerminologyTerm]:
        """Parse a term definition file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        if not data:
            return None

        # Handle nested 'term' key or flat structure
        term_data = data.get("term", data)
        if not term_data.get("id"):
            return None

        # Parse name_origin if present
        name_origin = None
        if term_data.get("name_origin"):
            origin_data = term_data["name_origin"]
            name_origin = TermNameOrigin(
                inspiration=origin_data.get("inspiration", ""),
                meaning=origin_data.get("meaning", ""),
                reflects=origin_data.get("reflects", []),
                acknowledgment=origin_data.get("acknowledgment"),
                note=origin_data.get("note"),
            )

        # Get category from manifest
        category = self._find_category(term_data["id"], manifest)

        # Extract persistence queries
        persistence = term_data.get("persistence", {})

        # Get token budget from manifest or estimate
        token_budget = self._get_token_budget(term_data["id"], manifest)

        return TerminologyTerm(
            id=term_data["id"],
            name=term_data.get("name", term_data["id"]),
            type=term_data.get("type", "unknown"),
            version=term_data.get("version", "1.0.0"),
            definition=term_data.get("definition", ""),
            codename=term_data.get("codename"),
            producer=term_data.get("producer"),
            category=category,
            name_origin=name_origin,
            anishinaabe_name=term_data.get("anishinaabe_name"),
            package_name=term_data.get("package_name"),
            purpose=term_data.get("purpose"),
            components=term_data.get("components"),
            is_not=term_data.get("is_not"),
            triggers=term_data.get("triggers", []),
            related_terms=term_data.get("related_terms", []),
            tempo_query=persistence.get("tempo_query"),
            loki_query=persistence.get("loki_query"),
            token_budget=token_budget,
            source_file=str(path),
        )

    def _find_category(self, term_id: str, manifest: TerminologyManifest) -> Optional[str]:
        """Find the category for a term ID."""
        for cat_id, cat_data in manifest.categories.items():
            for term_entry in cat_data.terms:
                if term_entry.id == term_id:
                    return cat_id
        return None

    def _get_token_budget(self, term_id: str, manifest: TerminologyManifest) -> int:
        """Get token budget for a term from manifest."""
        for cat_data in manifest.categories.values():
            for term_entry in cat_data.terms:
                if term_entry.id == term_id and term_entry.tokens:
                    return term_entry.tokens
        return 150  # Default estimate
