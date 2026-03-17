# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.


from typing import Dict, List, Optional, Union, TYPE_CHECKING, Callable, Any
import json

from thoughtful_agents.models.enums import EventType, ParticipantType, MentalObjectType
from thoughtful_agents.models.memory import Memory, MemoryStore
from thoughtful_agents.models.thought import Thought, ThoughtReservoir
from thoughtful_agents.models.conversation import Event, Conversation
from thoughtful_agents.utils.text_splitter import SentenceSplitter
from thoughtful_agents.utils.saliency import recalibrate_all_saliency
from thoughtful_agents.models.participant import Mediator
from thoughtful_agents.utils.prompts import *
from thoughtful_agents.utils.moderator_prompt import *
from thoughtful_agents.utils.llm_api import get_completion_sync


class NaiveMediator(Mediator):
    def __init__(
        self,
        name: str,
        model: str,
        id: Optional[str] = None,
       
        proactivity_config: Dict = {},
        **kwargs
    ):
        super().__init__(name=name, type=ParticipantType.AGENT, model = model)
        self.thought_reservoir = ThoughtReservoir()
        self.memory_store = MemoryStore()
        self.proactivity_config = proactivity_config
        self.text_splitter = SentenceSplitter()
        self.model = model
        self.next_utterance = None

    def act(self, conversation:Conversation, event: 'Event'):
        if event.participant_id == self.id:
            return []
        if_intervene, reasoning = self.decide_when(conversation)
        if if_intervene:
            self.next_utterance = self.decide_how(conversation)
    def decide_when(self, conversation_history, overall_context, memories_text):
       
        
        # Get previous thoughts
       
        decide_when_naive_prompt = f"""
        You are a mediator in a negotation. You goal is to help participants to reach agreement. You need to decide whether to step in at this moment.
        Here is the overall context:
        {overall_context}

        Here is the conversation history:
        {conversation_history}

        Here are salient memories:
        {memories_text}

        Based on the current context, do you want to intervene?
        If you decide to intervene, reply True and explain what triggers you to intervene.
        If you decide not to intervent, reply False and explain your decision.

        Respond with a JSON object in the following format:
        {{
        "should_intervene":"True/False,
        "reason: [short explanation]
        }}

        """
                                                 
        response =  get_completion_sync(
            system_prompt="",
            user_prompt=decide_when_naive_prompt,
            temperature=0.8,
            response_format="json_object"
        )
        
        # Parse the response
        response_text = response.get("text", "{}")
        prompt_response = json.loads(response_text)
        should_intervene = prompt_response.get("should_intervene")
        if should_intervene is None:
            # Default to not intervening if the response is not clear
            return False
        else:
            return should_intervene, prompt_response['reason']
    
    def decide_how(self, conversation_history, overall_context, memories_text):
        decide_how_naive_prompt = f"""
        You are a mediator in a negotation. You need to decide what to say at this moment.
        Here is the overall context:
        {overall_context}

        Here is the conversation history:
        {conversation_history}

        Here are salient memories:
        {memories_text}

        Based on the current context, what do you want to say?
        Remember your goal is to help all parties to reach the agreement on main issues. 
        Keep your response in 2-3 sentences.

        Respond with a JSON object in the following format:
        {{
        "speech":your speech
        }}

        """
        response =  get_completion_sync(
            system_prompt="",
            user_prompt=decide_how_naive_prompt,
            temperature=0.8,
            response_format="json_object"
        )
        
        # Parse the response
        response_text = response.get("text", "{}")
        prompt_response = json.loads(response_text)
        speech = prompt_response.get("speech")
        return speech
    
    def decide_when_and_how(self, conversation_history, overall_context, memories_text):
        raise NotImplementedError
    # First generate responses (how) and rate motivation score, if the score is higher than threshold, the agent will reply
    # The 'when' is based on how good/motivated is the response according to the conversation. 


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

