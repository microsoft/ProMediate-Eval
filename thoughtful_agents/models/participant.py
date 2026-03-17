# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from typing import Dict, List, Optional, Union, TYPE_CHECKING, Callable, Any
import random
import asyncio
import uuid
import json
from thoughtful_agents.models.enums import EventType, ParticipantType, MentalObjectType
from thoughtful_agents.models.memory import Memory, MemoryStore
from thoughtful_agents.models.thought import Thought, ThoughtReservoir
from thoughtful_agents.models.conversation import Event, Conversation
from thoughtful_agents.utils.thinking_engine import (
    generate_system1_thought,
    generate_system2_thoughts,
    evaluate_thought,
    articulate_thought
)
from abc import abstractmethod
from thoughtful_agents.utils.llm_api import get_completion
from thoughtful_agents.utils.moderator_prompt import *
from thoughtful_agents.utils.saliency import recalibrate_all_saliency
from thoughtful_agents.utils.text_splitter import SentenceSplitter




class Participant:
    
    def __init__(
        self,
        name: str,
        type: ParticipantType,
        model:str,
        id: Optional[str] = None,
        **kwargs
    ):
        # Use provided ID or generate a UUID
        self.id = id if id is not None else str(uuid.uuid4())
            
        self.name = name
        self.type = type
        self.last_spoken_turn = -1
        self.model = model
    
    async def send_message(self, message: str, conversation: 'Conversation', interpret: bool = True) -> Event:
        """Send a message to the conversation.
        
        This method creates an utterance event, records it in the conversation,
        and immediately interprets it to ensure the interpretation is available
        for all subsequent operations.
        
        Args:
            message: The message content
            conversation: The conversation to send the message to
            interpret: Whether to interpret the message immediately
        """
        
        # Create the event
        event = Event(
            participant_id=self.id,
            type=EventType.UTTERANCE,
            content=message,
            turn_number=conversation.turn_number,
            participant_name=self.name
        )

        # Record the event
        conversation.record_event(event)

        if interpret:
            # Interpret the event
            await conversation.interpret_event(event)
        
        # Update the last spoken turn
        self.last_spoken_turn = conversation.turn_number

        return event


# class Human(Participant):
#     def __init__(self, name: str, id: Optional[str] = None, **kwargs):
#         super().__init__(name=name, type=ParticipantType.HUMAN, id=id, **kwargs)


class Mediator(Participant):
    def __init__(
        self,
        name: str,
        model: str,
        response_type: str = 'separate',  # 'separate' or 'combined'
        id: Optional[str] = None,
        intervene_freq: str = "less",  # "more" or "less"
        proactivity_config: Dict = {},
        **kwargs
    ):
        super().__init__(name=name, type=ParticipantType.AGENT, model = model, response_type=response_type, intervene_freq=intervene_freq)
        self.thought_reservoir = ThoughtReservoir()
        self.memory_store = MemoryStore()
        self.proactivity_config = proactivity_config
        self.text_splitter = SentenceSplitter()
        self.model = model
        self.type = 'mediator'
        self.response_type = response_type
        self.next_utterance = None
        self.intervene_freq = intervene_freq  # Frequency of intervention, can be "more" or "less"

    # async def act(self, conversation:Conversation, event: 'Event'):
    #     if event.participant_id == self.id:
    #         return []
    #     if_intervene, reasoning = self.decide_when(conversation)
    #     if if_intervene:
    #         self.next_utterance = await self.decide_how(conversation)

    def prepare(self, conversation):
        """Prepare the mediator for the conversation.
        
        This can include initializing memory, setting up thought reservoirs, etc.
        """
        # Initialize memory store and thought reservoir
        overall_context = conversation.context
        memory_store = self.memory_store
        last_events = conversation.get_last_n_events(5)
        conversation_history = ""
        for i, event in enumerate(last_events):
            conversation_history += f"CON#{event.id}: {event.participant_name}: {event.content}\n"
        salient_memories = memory_store.retrieve_top_k(k=5, threshold=0.25, memory_type=MentalObjectType.MEMORY_LONG_TERM)
        # update last_accessed_turn of each memory
        for memory in salient_memories:
            memory.last_accessed_turn = conversation.turn_number
        memories_text = ""
        for i, memory in enumerate(salient_memories):
            memories_text += f"MEM#{memory.id}: {memory.content}\n"
        previous_thoughts = self.thought_reservoir.retrieve_top_k(k=3, threshold=0.25, thought_type=MentalObjectType.THOUGHT_SYSTEM2)
    # update last_accessed_turn of each thought
        for thought in previous_thoughts:
            thought.last_accessed_turn = conversation.turn_number
        thoughts_text = ""
        for i, thought in enumerate(previous_thoughts):
            thoughts_text += f"THO#{thought.id}: {thought.content}\n"
        
        return overall_context, conversation_history, memories_text, thoughts_text
       
    def initialize_memory(self, text: str, memory_type: MentalObjectType = MentalObjectType.MEMORY_LONG_TERM, by_paragraphs: bool = False, compute_embedding: bool = True) -> None:
        """Initialize the agent's memory with a text.
        
        This method splits the input text into chunks (sentences or paragraphs),
        creates a memory for each chunk of the specified type, and adds it to the agent's memory store.

        Args:
            text: The text to parse and add as memory
            memory_type: The type of memory to create (default: MEMORY_LONG_TERM)
            by_paragraphs: Whether to split by paragraphs first (default: False)
            compute_embedding: Whether to compute embeddings for the memories (default: True)

        Returns:
            None
        """
        # Clean whitespace from the text
        text = text.strip()

        # Split the text into chunks
        chunks = self.text_splitter.split_text(text, by_paragraphs=by_paragraphs)


        for chunk in chunks:
            # Create a memory for each chunk
            memory = Memory(
                agent_id=self.id,
                type=memory_type,
                content=chunk,
                generated_turn=0,
                last_accessed_turn=0,
                compute_embedding=compute_embedding
            )
            self.memory_store.add(memory)
    def recalibrate_saliency_for_event(self, event: 'Event') -> None:
        """Recalibrate saliency scores of long-term memories and thoughts based on a new event.
        
        Args:
            event: The event to use for recalibration
        """
        # Ensure the event has an embedding
        if event.embedding is None:
            event._compute_embedding_sync()
            
        # Recalibrate long-term memories
        recalibrate_all_saliency(
            items=self.memory_store.long_term_memory,
            utterance=event
        )
        
        # Recalibrate thoughts
        recalibrate_all_saliency(
            items=self.thought_reservoir.thoughts,
            utterance=event
        )

    @abstractmethod
    async def act(self, conversation:Conversation, event: 'Event'):
        pass
    @abstractmethod 
    def decide_when(self,cconversation_history, overall_context, memories_text):
        pass

    @abstractmethod
    async def decide_how(self, conversation_history, overall_context, memories_text):
        pass   

    @abstractmethod
    async def decide_when_and_how(self, conversation_history, overall_context, memories_text):
        pass

class Human(Participant):
    def __init__(
        self,
        name: str,
        model: str,
        id: Optional[str] = None,
       
        proactivity_config: Dict = {},
        **kwargs
    ):
        super().__init__(name=name, type=ParticipantType.HUMAN, model = model)
        self.thought_reservoir = ThoughtReservoir()
        self.memory_store = MemoryStore()
        self.proactivity_config = proactivity_config
        self.text_splitter = SentenceSplitter()
        self.model = model
        self.type = 'human'
              

    async def think(self, conversation: Conversation, event: 'Event') -> None:
        """Process an event, including generating thoughts, evaluating them, and adding them to the thought reservoir.
      
        Args:
            conversation: The conversation context
            event: The event to process
        """
        # 1. Process the event - Skip if this agent is the source of the event
        if event.participant_id == self.id:
            return []  # Don't respond to our own events
            
        # 2. Recalibrate saliency scores based on the new event
        await self.recalibrate_saliency_for_event(event)
        
        # 3. Add event to short-term memory
        self.add_event_to_memory(event)
        
        # if self.name == "Moderator":
        #     should_intervene, reasoning = await self.check_intervene(conversation)
        #     print(reasoning)
        #     if not should_intervene:
        #         return []      
         # 4. Generate thoughts
        # if self.name == "Moderator":
        #     consensus_check = await self.check_consensus(conversation)
        #     self.consensus_check = consensus_check

        # else:
        #     consensus_check = None
        
        new_thoughts = await self.generate_thoughts(conversation)
        # if consensus_check!=[]:
        #     self.add_event_to_memory(consensus_check)
        # 5. Evaluate thoughts
     
        await self.evaluate_thoughts(new_thoughts, conversation)

        # 6. Add thoughts to reservoir
        for thought in new_thoughts:
            self.thought_reservoir.add(thought)
    
        # 7. Select thoughts to articulate
        await self.select_thoughts(new_thoughts, conversation)
    
    async def check_consensus(self, conversation: Conversation):
        """
        Check the current consensus status on all issues
        """
        overall_context = conversation.context
        contract_issues = conversation.main_topic
        last_events = conversation.get_last_n_events(5)
        conversation_history = ""
        for i, event in enumerate(last_events):
            conversation_history += f"CON#{event.id}: {event.participant_name}: {event.content}\n"
        #TODO: print out consensus_check
        # Access memory_store and thought_reservoir directly from the agent
        consensus_check_prompt_full = consensus_check_prompt.format(overall_context = overall_context, contract_issues=contract_issues,
                                                                    conversation_history=conversation_history)
        response = await get_completion(
            system_prompt="",
            user_prompt=consensus_check_prompt_full ,
            temperature=0.5, 
            response_format="json_object",
            model = self.model
        )
        response_text = response.get("text", "{}")
        response_data = json.loads(response_text)
    
        results = []
        for issue in response_data:
            results.append(response_data[issue]['label'])

        if "unresolved" not in results:
            conversation.if_end = True
        return json.dumps(response_data)
    

    async def check_intervene(self, conversation: Conversation) -> bool:
        """Check if the agent should intervene in the conversation.
        
        This method checks if the agent is the moderator and if it has a thought that meets the intervention criteria.
        
        Args:
            conversation: The conversation context
            
        Returns:
            True if the agent should intervene, False otherwise
        """
        
        # Check if there are thoughts that meet intervention criteria
        overall_context = conversation.context
        # Access memory_store and thought_reservoir directly from the agent
        memory_store = self.memory_store
        thought_reservoir = self.thought_reservoir
        
        # Get conversation history
        last_events = conversation.get_last_n_events(5)
        conversation_history = ""
        for i, event in enumerate(last_events):
            conversation_history += f"CON#{event.id}: {event.participant_name}: {event.content}\n"
        
        # Get salient memories
        salient_memories = memory_store.retrieve_top_k(k=5, threshold=0.25, memory_type=MentalObjectType.MEMORY_LONG_TERM)
        # update last_accessed_turn of each memory
        for memory in salient_memories:
            memory.last_accessed_turn = conversation.turn_number
        memories_text = ""
        for i, memory in enumerate(salient_memories):
            memories_text += f"MEM#{memory.id}: {memory.content}\n"
        
        # Get previous thoughts
        previous_thoughts = thought_reservoir.retrieve_top_k(k=3, threshold=0.25, thought_type=MentalObjectType.THOUGHT_SYSTEM2)
        for thought in previous_thoughts:
            thought.last_accessed_turn = conversation.turn_number
        thoughts_text = ""
        for i, thought in enumerate(previous_thoughts):
            thoughts_text += f"THO#{thought.id}: {thought.content}\n"
        user_prompt = evaluation_when_mediator.format(overall_context=overall_context,
                                                      conversation_history=conversation_history,
                                                      memories_text=memories_text,
                                                      thoughts_text=thoughts_text)
        response =  await get_completion(
            system_prompt="",
            user_prompt=user_prompt,
            temperature=0.8,
            response_format="json_object"
        )
        
        # Parse the response
        response_text = response.get("text", "{}")
        prompt_response = json.loads(response_text)
        should_intervene = prompt_response.get("should_intervene")
        if should_intervene is None:
            # Default to not intervening if the response is not clear
            return False, prompt_response['reasoning']
        else:
            return should_intervene, prompt_response['reasoning']
    async def recalibrate_saliency_for_event(self, event: 'Event') -> None:
        """Recalibrate saliency scores of long-term memories and thoughts based on a new event.
        
        Args:
            event: The event to use for recalibration
        """
        # Ensure the event has an embedding
        if event.embedding is None:
            await event.compute_embedding_async()
            
        # Recalibrate long-term memories
        recalibrate_all_saliency(
            items=self.memory_store.long_term_memory,
            utterance=event
        )
        
        # Recalibrate thoughts
        recalibrate_all_saliency(
            items=self.thought_reservoir.thoughts,
            utterance=event
        )

    async def generate_thoughts(self, conversation: Conversation, num_system1: int = 1, num_system2: int = 2) -> List[Thought]:
        """Generate thoughts of both system 1 and system 2 types.
        
        Args:
            conversation: The conversation
            num_system1: Number of system 1 thoughts to generate
            num_system2: Number of system 2 thoughts to generate 
            
        Returns:
            List of generated thoughts
        """
        # Generate System 1 and System 2 thoughts concurrently
        # system1_task = generate_system1_thought(
        #     conversation=conversation,
        #     agent=self
        # )
        
        system2_thoughts = await generate_system2_thoughts(
            conversation=conversation,
            agent=self,
            num_thoughts=num_system2,
    
        )
        
        # Wait for both tasks to complete
        # system1_thought, system2_thoughts = await asyncio.gather(system1_task, system2_task)
            
        # Return all generated thoughts
        # return [system1_thought] + system2_thoughts
        return system2_thoughts
        
    
    async def evaluate_thoughts(self, new_thoughts: List[Thought], conversation: Conversation) -> None:
        """Evaluate newly generated thoughts based on various criteria.
        
        Args:
            new_thoughts: List of new thoughts to evaluate
            conversation: The conversation
        """ 
        # Create evaluation tasks for all thoughts
        evaluation_tasks = [
            evaluate_thought(
                thought=thought,
                conversation=conversation,
                agent=self
            )
            for thought in new_thoughts
        ]
        
        # Execute all evaluation tasks concurrently
        if evaluation_tasks:
            await asyncio.gather(*evaluation_tasks)
            
    
    async def articulate_thought(self, thought: Thought, conversation: Conversation) -> str:
        """Articulate a thought into an utterance string.
        
        Args:
            thought: The thought to articulate
            conversation: The conversation
            
        Returns:
            Articulated text ready for expression in the conversation
        """
        return await articulate_thought(thought, conversation, agent=self)
    

    async def select_thoughts(self, thoughts: List[Thought], conversation: Conversation) -> List[Thought]:
        """Select thoughts that could be potentially articulated based on the proactivity configuration, given a list of thoughts.
        
        This method implements the Iterative Thought Reservoir Decision Process algorithm,
        which selects thoughts for articulation based on turn-taking predictions,
        intrinsic motivation scores, and proactivity configuration.
        
        Args:
            thoughts: List of thoughts to select from (new thoughts)
            conversation: The current conversation
            
        Returns:
            List of selected thoughts to potentially articulate
        """
        # Reset selected status for ALL thoughts in the reservoir, not just the new ones
        for thought in self.thought_reservoir.thoughts:
            thought.selected = False
            
        # Get proactivity configuration thresholds
        im_threshold = self.proactivity_config.get('im_threshold', 3.5)  # Default threshold for intrinsic motivation
        system1_prob = self.proactivity_config.get('system1_prob', 0.3)  # Default probability for system1 thoughts
        interrupt_threshold = self.proactivity_config.get('interrupt_threshold', 4)  # Default threshold for interruption

        if len(thoughts) == 0:
            return []

        # Filter thoughts that have been evaluated (have intrinsic_motivation scores)
        evaluated_thoughts = [t for t in thoughts if isinstance(t.intrinsic_motivation, dict) and 'score' in t.intrinsic_motivation]
        if not evaluated_thoughts:
            return []  # No evaluated thoughts to select from
            
        # Sort thoughts by their intrinsic motivation score
        sorted_thoughts = sorted(
            evaluated_thoughts, 
            key=lambda t: t.intrinsic_motivation['score'], 
            reverse=True
        )
        
        # Step 1: Get the turn allocation type from the current event
        turn_allocation_type = conversation.event_history[-1].pred_next_turn
        
        selected_thoughts = []
        # turn_allocation_type = "anyone"
        # Step 2: Process according to turn-taking type
        if turn_allocation_type == "anyone":
            # Turn is open to anyone (self-selection)
            high_motivation_thoughts = [t for t in sorted_thoughts if t.intrinsic_motivation['score'] >= im_threshold]
            
            if high_motivation_thoughts:
                # Select the highest-rated thought
                    selected_thoughts.append(high_motivation_thoughts[0])
            # else:
            #     # With some probability, select from system-1 thoughts
            #     if random.random() < system1_prob:
            #         system1_thoughts = [t for t in sorted_thoughts if t.type == MentalObjectType.THOUGHT_SYSTEM1]
            #         if system1_thoughts:
            #             selected_thoughts.append(system1_thoughts[0])
                        
        elif turn_allocation_type == self.name:
            # Turn is allocated to this agent
            # Select the highest-rated thought
            if sorted_thoughts:
                selected_thoughts.append(sorted_thoughts[0])
        else:
            # Turn is allocated to someone else
            interrupt_thoughts = [t for t in sorted_thoughts if t.intrinsic_motivation['score'] >= interrupt_threshold]
            
            if interrupt_thoughts:
                # Select the highest-rated thought for interruption
                selected_thoughts.append(interrupt_thoughts[0])

        # Mark the selected thoughts as selected
        for thought in selected_thoughts:
            thought.selected = True
                
        return selected_thoughts
    

    def add_event_to_memory(self, event: 'Event', memory_type: MentalObjectType = MentalObjectType.MEMORY_SHORT_TERM, compute_embedding: bool = True) -> None:
        """Add an event to the agent's memory.
        
        Args:
            event: The event to add to memory
            memory_type: The type of memory to create (default: MEMORY_SHORT_TERM)
            
        Returns:
            None
        """
        # Create a memory from the event
        memory = Memory(
            agent_id=self.id,
            type=memory_type,
            content=event.content,
            generated_turn=event.turn_number,
            last_accessed_turn=event.turn_number,
            compute_embedding=compute_embedding
        )
        
        # Add the memory to the memory store
        self.memory_store.add(memory)
        
    def initialize_memory(self, text: str, memory_type: MentalObjectType = MentalObjectType.MEMORY_LONG_TERM, by_paragraphs: bool = False, compute_embedding: bool = True) -> None:
        """Initialize the agent's memory with a text.
        
        This method splits the input text into chunks (sentences or paragraphs),
        creates a memory for each chunk of the specified type, and adds it to the agent's memory store.

        Args:
            text: The text to parse and add as memory
            memory_type: The type of memory to create (default: MEMORY_LONG_TERM)
            by_paragraphs: Whether to split by paragraphs first (default: False)
            compute_embedding: Whether to compute embeddings for the memories (default: True)

        Returns:
            None
        """
        # Clean whitespace from the text
        text = text.strip()

        # Split the text into chunks
        chunks = self.text_splitter.split_text(text, by_paragraphs=by_paragraphs)


        for chunk in chunks:
            # Create a memory for each chunk
            memory = Memory(
                agent_id=self.id,
                type=memory_type,
                content=chunk,
                generated_turn=0,
                last_accessed_turn=0,
                compute_embedding=compute_embedding
            )
            self.memory_store.add(memory)