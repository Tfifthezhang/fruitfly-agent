"""Composable information spaces for file memory, local knowledge and live data.

Vendor clients and runtime lifecycle ownership stay outside this package.
Core Context Stage integration lives in this package's adapter module.
"""

from .application import (
    INFORMATION_BLOCK_END,
    INFORMATION_BLOCK_START,
    INFORMATION_CUSTOM_KIND,
    TextInformationApplicator,
)
from .lexical import (
    BudgetedPostProcessor,
    LexicalRetriever,
    create_static_lexical_space,
)
from .hub import InformationHub
from .file_memory import (
    FileMemorySource,
    FileMemoryRetriever,
    create_file_memory_space,
)
from .local_knowledge import (
    LocalKnowledgeSource,
    create_local_knowledge_space,
)
from .live_http import (
    LiveHttpRetriever,
    create_live_http_space,
)
from .models import (
    InformationAccessError,
    InformationArtifact,
    InformationDescriptor,
    InformationEffect,
    InformationHit,
    InformationQuery,
    InformationRef,
    InformationSearchResult,
    InformationSpaceDescriptor,
)
from .pipeline import LatestUserQueryBuilder, InformationPipeline
from .protocols import (
    InformationApplicator,
    InformationArtifactSource,
    InformationPostProcessor,
    InformationQueryBuilder,
    InformationReader,
    InformationRetriever,
)
from .spaces import (
    CallbackInformationReader,
    CallbackInformationRetriever,
    InformationSpace,
    InformationSpaceCatalog,
    StaticInformationReader,
)

__all__ = [
    "INFORMATION_BLOCK_END",
    "INFORMATION_BLOCK_START",
    "INFORMATION_CUSTOM_KIND",
    "InformationAccessError",
    "InformationArtifact",
    "InformationDescriptor",
    "InformationEffect",
    "InformationHit",
    "InformationQuery",
    "InformationRef",
    "InformationSearchResult",
    "InformationSpaceDescriptor",
    "InformationApplicator",
    "InformationArtifactSource",
    "InformationPostProcessor",
    "InformationQueryBuilder",
    "InformationReader",
    "InformationRetriever",
    "InformationSpace",
    "InformationSpaceCatalog",
    "StaticInformationReader",
    "CallbackInformationReader",
    "CallbackInformationRetriever",
    "LexicalRetriever",
    "BudgetedPostProcessor",
    "create_static_lexical_space",
    "TextInformationApplicator",
    "LatestUserQueryBuilder",
    "InformationPipeline",
    "InformationHub",
    "FileMemorySource",
    "FileMemoryRetriever",
    "LocalKnowledgeSource",
    "LiveHttpRetriever",
    "create_file_memory_space",
    "create_local_knowledge_space",
    "create_live_http_space",
]
