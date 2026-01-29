"""
ContextCore Terminology Module

Emit and query Wayfinder terminology definitions as OTel spans.

Enables TraceQL queries like:
    { term.id = "wayfinder" }
    { term.type = "implementation" }
    { distinction.question =~ ".*ContextCore.*" }
"""

from contextcore.terminology.models import (
    TermType,
    TerminologyManifest,
    TerminologyTerm,
    TerminologyDistinction,
    QuickLookupEntry,
)
from contextcore.terminology.parser import TerminologyParser
from contextcore.terminology.emitter import TerminologyEmitter

__all__ = [
    "TermType",
    "TerminologyManifest",
    "TerminologyTerm",
    "TerminologyDistinction",
    "QuickLookupEntry",
    "TerminologyParser",
    "TerminologyEmitter",
]
