# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from enum import Enum

class MentalObjectType(Enum):
    MEMORY_LONG_TERM = "memory_long_term"
    MEMORY_SHORT_TERM = "memory_short_term"
    THOUGHT_SYSTEM1 = "thought_system1"
    THOUGHT_SYSTEM2 = "thought_system2"

class EventType(Enum):
    UTTERANCE = "utterance"
    SILENCE = "silence"

class ParticipantType(Enum):
    HUMAN = "human"
    AGENT = "mediator" 