# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import numpy as np  # type: ignore
from typing import List, Optional, Union
from numpy.typing import NDArray

from thoughtful_agents.models.enums import MentalObjectType
from thoughtful_agents.utils.llm_api import get_embedding_sync, get_embedding_async

class MentalObject:
    def __init__(
        self,
        id: str,
        agent_id: int,
        type: MentalObjectType,
        content: str,
        generated_turn: int,
        last_accessed_turn: int,
        retrieval_count: int = 0,
        weight: float = 1.0,
        saliency: float = 0.0,
        embedding: Optional[Union[NDArray[np.float32], List[float]]] = None,
        compute_embedding: bool = True,
        end_the_conversation: bool = False

    ):
        # Simple attributes that don't need validation
        self.id = id
        self.agent_id = agent_id
        self.type = type
        self.content = content
        self.generated_turn = generated_turn
        self.last_accessed_turn = last_accessed_turn
        self.retrieval_count = retrieval_count
        self.weight = weight
        self.saliency = saliency
     
        
        # Handle embedding computation
        if embedding is not None:
            # Convert list to numpy array if needed
            if isinstance(embedding, list):
                self.embedding = np.array(embedding, dtype=np.float32)
            else:
                self.embedding = embedding
        elif compute_embedding:
            # Compute embedding synchronously
            self.embedding = self._compute_embedding_sync(content)
        else:
            # Defer embedding computation
            self.embedding = None
    
    def _compute_embedding_sync(self, text: str) -> NDArray[np.float32]:
        """Compute embedding synchronously (blocking call).
        
        This is a helper method for the constructor. For async code,
        use compute_embedding_async instead.
        """
        # Use the synchronous version of get_embedding
        embedding_list = get_embedding_sync(text)
        return np.array(embedding_list, dtype=np.float32)
    
    async def compute_embedding_async(self) -> None:
        """Compute embedding asynchronously if it wasn't computed in the constructor."""
        if self.embedding is None:
            embedding_list = await get_embedding_async(self.content)
            self.embedding = np.array(embedding_list, dtype=np.float32) 