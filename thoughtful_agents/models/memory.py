# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from typing import List, Optional

from thoughtful_agents.models.mental_object import MentalObject
from thoughtful_agents.models.enums import MentalObjectType

class Memory(MentalObject):
    """Memory class that inherits from MentalObject."""
    
    # Class variable to keep track of the next available Memory ID
    _next_memory_id = 0
    
    def __init__(
        self,
        agent_id: int,
        type: MentalObjectType,
        content: str,
        generated_turn: int,
        last_accessed_turn: int,
        id: Optional[str] = None,
        **kwargs
    ):
        # Generate a Memory-specific ID if not provided
        if id is None:
            id = f"{Memory._next_memory_id}"
            Memory._next_memory_id += 1
            
        super().__init__(
            id=id,
            agent_id=agent_id,
            type=type,
            content=content,
            generated_turn=generated_turn,
            last_accessed_turn=last_accessed_turn,
            **kwargs
        )
        # Additional memory-specific attributes can be added here

class MemoryStore:
    def __init__(self):
        self.long_term_memory: List[Memory] = []
        self.short_term_memory: List[Memory] = []
    
    def add(self, memory: Memory) -> None:
        """Add a memory to the appropriate store."""
        if memory.type == MentalObjectType.MEMORY_LONG_TERM:
            self.long_term_memory.append(memory)
        elif memory.type == MentalObjectType.MEMORY_SHORT_TERM:
            self.short_term_memory.append(memory)
    
    def remove(self, memory: Memory) -> None:
        """Remove a memory from the appropriate store."""
        if memory.type == MentalObjectType.MEMORY_LONG_TERM:
            self.long_term_memory.remove(memory)
        elif memory.type == MentalObjectType.MEMORY_SHORT_TERM:
            self.short_term_memory.remove(memory)
    
    def retrieve_top_k(self, k: int, threshold: float = 0.3, memory_type: MentalObjectType = MentalObjectType.MEMORY_LONG_TERM) -> List[Memory]:
        """Retrieve top k memories based on the saliency score, that are at least above the threshold."""
        if memory_type == MentalObjectType.MEMORY_LONG_TERM:
            memories = self.long_term_memory
        elif memory_type == MentalObjectType.MEMORY_SHORT_TERM:
            memories = self.short_term_memory
        else:
            memories = self.long_term_memory + self.short_term_memory
        memories = sorted(memories, key=lambda x: x.saliency, reverse=True)
        return [memory for memory in memories if memory.saliency >= threshold][:k]
    
    def get_by_id(self, memory_id: str) -> Optional[Memory]:
        """Get a memory by its ID."""
        # Search in long-term memory
        for memory in self.long_term_memory:
            if memory.id == memory_id:
                return memory
                
        # Search in short-term memory
        for memory in self.short_term_memory:
            if memory.id == memory_id:
                return memory
                
        return None