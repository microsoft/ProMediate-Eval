# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from typing import List, Union, Optional, Dict, TYPE_CHECKING
import uuid

from thoughtful_agents.models.enums import MentalObjectType
from thoughtful_agents.models.mental_object import MentalObject

# Use TYPE_CHECKING to avoid circular imports
if TYPE_CHECKING:
    from thoughtful_agents.models.conversation import Event

class Thought(MentalObject):
    # _next_thought_id class variable removed as we're switching to UUID
    
    def __init__(
        self,
        agent_id: int,
        type: MentalObjectType,
        content: str,
        generated_turn: int,
        last_accessed_turn: int,
      
        intrinsic_motivation: Dict[str, Union[str, float]],
        stimuli: List[Union[MentalObject, 'Event']],
        **kwargs
    ):
        # Always generate a UUID
        id = str(uuid.uuid4())
            
        super().__init__(
            id=id,
            agent_id=agent_id,
            type=type,
            content=content,
            generated_turn=generated_turn,
            last_accessed_turn=last_accessed_turn,
          
            **kwargs
        )
        self.intrinsic_motivation = intrinsic_motivation
        self.stimuli = stimuli
       
        self.selected = False  # Track whether this thought has been selected for articulation

class ThoughtReservoir:
    def __init__(self):
        self.thoughts: List[Thought] = []
    
    def add(self, thought: Thought) -> None:
        """Add a thought to the reservoir."""
        self.thoughts.append(thought)
    
    def remove(self, thought: Thought) -> None:
        """Remove a thought from the reservoir."""
        self.thoughts.remove(thought)
    
    def retrieve_top_k(self, k: int, threshold: float = 0.3, thought_type: MentalObjectType = MentalObjectType.THOUGHT_SYSTEM2) -> List[Thought]:
        """Retrieve top k thoughts based on the saliency score, that are at least above the threshold."""
        if thought_type == MentalObjectType.THOUGHT_SYSTEM2:
            thoughts = [thought for thought in self.thoughts if thought.type == thought_type]
        elif thought_type == MentalObjectType.THOUGHT_SYSTEM1:
            thoughts = [thought for thought in self.thoughts if thought.type == thought_type]
        else:
            thoughts = self.thoughts
        thoughts = sorted(thoughts, key=lambda x: x.saliency, reverse=True)
        return [thought for thought in thoughts if thought.saliency >= threshold][:k]
    
    def get_selected_thoughts(self) -> List[Thought]:
        """Get all thoughts that have been selected for articulation."""
        return [thought for thought in self.thoughts if thought.selected]
    
    def get_by_id(self, thought_id: str) -> Optional[Thought]:
        """Get a thought by its ID."""
        for thought in self.thoughts:
            if thought.id == thought_id:
                return thought
        return None
    
