"""
Cognitive Streams — Specialized latent cognitive processes.

Includes the original 4 streams plus the new InquiryStream (priority 0.8).
"""

from telos.core.streams.base import CognitiveStream
from telos.core.streams.implementations import ReflexStream, PerceptionStream, MemoryStream, PlanningStream
from telos.core.streams.inquiry_stream import InquiryStream

__all__ = [
    "CognitiveStream",
    "ReflexStream", "PerceptionStream", "MemoryStream", "PlanningStream",
    "InquiryStream",
]
