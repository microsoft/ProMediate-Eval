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
from thoughtful_agents.utils.moderator_prompt import evaluate_prompt_mediator_baseline
from thoughtful_agents.utils.llm_api import get_completion_sync


class GenericMediator(Mediator):
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
        if self.response_type == 'combined':
            self.next_utterance = self.decide_when_and_how(conversation)
        elif self.response_type == 'separate':
            if_intervene, reasoning = self.decide_when(conversation)
            if if_intervene:
                self.next_utterance = self.decide_how(conversation)

    def decide_when(self, conversation):
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
        
        # Get previous thoughts
       
        decide_when_naive_prompt = f"""
        ## Your Role
        You are a helpful assistant in a multiparty chat room.

        ## Room Context
        You are helping with a discussion in a room with the following context:
        {overall_context}

        ## Your Task
        Here you're given a conversation history and some rules for when to engage. Your task is to determine if the AI assistant (Group Copilot) should engage in the conversation now.

        Recent Conversation History
        {conversation_history}

        Here are salient memories:
        {memories_text}

        ## Guidelines
        Rules for engagement:

        - If the conversation has stalled (no messages for a while)
        - If users are asking questions the AI could help with
        - If there's confusion or disagreement the AI could help resolve
        - If the conversation has moved away from the main goal
        - If there's an opportunity to provide valuable insights

        DO NOT engage if:

        - The conversation is flowing well between participants
        - The last message was from the AI assistant
        - Users are having a personal exchange

        ## General guidelines:

        - You can be proactive in offering help, but avoid interrupting the flow of conversation.
        - If you recieve feedback from users that they don't want the AI to engage, respect that and become passive.
        - You should always be sensitive to the social dynamics of the conversation as well as the users' sentiments towards your presence.
        - If you are unsure about the context or the appropriateness of your engagement, it's better to remain passive.
        - Always prioritize the users' experience and the goals of the discussion.
        
        ## Output
        Based on the conversation history and the rules for engagement, determine if the AI assistant should engage now.
        Your response should be a json object with the following structure:


        {{
        "should_engage": True/False,
        "reason": "A brief explanation of why or why not"
        }}

        """
                                                 
        response =  get_completion_sync(
            system_prompt="",
            user_prompt=decide_when_naive_prompt,
            temperature=0.8,
            response_format="json_object",
            model = 'gpt-4.1'
        )
        
        # Parse the response
        response_text = response.get("text", "{}")
        response_text = response_text.strip('```json')
        response_text = response_text.replace('\n','')
        
        prompt_response = json.loads(response_text)
        should_intervene = prompt_response.get("should_engage")
        thought = self.create_thought(
            data = prompt_response,
            conversation=conversation)
        thought.intrinsic_motivation = {"score":-1, "reasoning": ""}
        self.thought_reservoir.add(thought)
        if should_intervene is None:
            # Default to not intervening if the response is not clear
            return False
        else:
            return should_intervene, prompt_response['reason']
    def create_thought(self,data, conversation):
            if "content" in data:
                content = data.get("content", "")
            else:
                content = json.dumps(data.get("reason", ""))
            stimuli_refs = data.get("stimuli", [])
            
            # Map stimuli references to actual objects
            stimuli_objects = []
            for ref in stimuli_refs:
                ref = ref.strip()
                if ref.startswith("CON#"):
                    ref_id = ref.replace("CON#", "")
                    matching_event = conversation.get_by_id(ref_id)
                    if matching_event:
                        stimuli_objects.append(matching_event)
                elif ref.startswith("MEM#"):
                    ref_id = ref.replace("MEM#", "")
                    matching_memory = self.memory_store.get_by_id(ref_id)
                    if matching_memory:
                        stimuli_objects.append(matching_memory)
                elif ref.startswith("THO#"):
                    ref_id = ref.replace("THO#", "")
                    matching_thought = self.thought_reservoir.get_by_id(ref_id)
                    if matching_thought:
                        stimuli_objects.append(matching_thought)
            return Thought(
                agent_id=self.id,
                type=MentalObjectType.THOUGHT_SYSTEM2,
                content=content,
                generated_turn=conversation.turn_number,
                last_accessed_turn=conversation.turn_number,
                intrinsic_motivation={"reasoning": "Default motivation before evaluation", "score": -1.0},  # Default value, will be updated by evaluation
                stimuli=stimuli_objects,
              
                compute_embedding=True
            )
    def decide_how(self, conversation):
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
    #     previous_thoughts = self.thought_reservoir.retrieve_top_k(k=3, threshold=0.25, thought_type=MentalObjectType.THOUGHT_SYSTEM2)
    # # update last_accessed_turn of each thought
    #     for thought in previous_thoughts:
    #         thought.last_accessed_turn = conversation.turn_number
    #     thoughts_text = ""
    #     for i, thought in enumerate(previous_thoughts):
    #         thoughts_text += f"THO#{thought.id}: {thought.content}\n"

        decide_how_naive_prompt = f"""
        ## Your Role
        You are a helpful assistant in a multiparty chat room.

        ## Room Context
        You are helping with a discussion in a room with the following context:
        {overall_context}

        ## Your Task
        You have decided to engage in the conversation among human users. Your task is to provide a friendly and helpful message to the users in the chat room to assist their requests or to help them move the discussion forward.

        ## Conversation History
        {conversation_history}

        ## Here are salient memories:
        {memories_text}

        ## Guidelines
        Your main task

        You're an observer in the room, be proactive when needed, but avoid interrupting the flow of conversation.
        Your role is to keep the conversation on track and help users achieve their goals.
        Your role is to facilitate productive discussion and help users find common ground. Work to:
        Balance the needs and perspectives of all participants
        Guide the conversation toward consensus when appropriate
        Identify and highlight shared goals and areas of agreement
        Tactfully address points of conflict or misunderstanding
        Summarize progress and action items when helpful
        Respect the pace of human conversation without rushing to conclusions
        When appropriate, provide concrete suggestions or solutions that address the discussion points. These could include:
        Specific action items that could move the group toward their goals
        Alternative approaches when the discussion appears stuck
        Summaries of potential solutions with their pros and cons
        Frameworks or methods to evaluate options being discussed
        Resources or examples that might inform the conversation

        ## Other Tasks
        If you observe a user joining the room, you can start the conversation by welcoming them.

        ## General guidelines:

        Be friendly, helpful, yet conversational and natural.
        Avoid being overly formal or robotic. Respond as if you are a human participant in the conversation.
        Be sensitive to the social dynamics of the conversation as well as the users' sentiments towards your presence, take into account the feedback you receive from users.
        Output
        Please just output the message you would like to send to the users in the chat room. Do not include any additional text or explanations.
        
        Your response should be a json object with the following structure:

        {{
        "message": "your response"
        }}

        """
        response =  get_completion_sync(
            system_prompt="",
            user_prompt=decide_how_naive_prompt,
            temperature=0.8,
            response_format="json_object",
            model = 'gpt-4.1'
        )
        
        # Parse the response
        response_text = response.get("text", "{}")
        response_text = response_text.strip('```json')
        response_text = response_text.replace('\n','')
        prompt_response = json.loads(response_text)
        speech = prompt_response.get("message")
        return speech
    
    def decide_when_and_how(self, conversation: Conversation):
        # First generate responses (how) and rate motivation score, if the score is higher than threshold, the agent will reply
        # The 'when' is based on how good/motivated is the response according to the conversation. 
        overall_context = conversation.context
        method = conversation.method
        # Get conversation history
        last_events = conversation.get_last_n_events(5)
        conversation_history = ""
        for event in last_events:
            conversation_history += f"{event.participant_name}: {event.content}\n"
        
        # Access memory_store directly from the agent
        memory_store = self.memory_store
        
        # Get long-term memories
        ltm = memory_store.retrieve_top_k(k=10, threshold=0.25, memory_type=MentalObjectType.MEMORY_LONG_TERM)
        ltm_text = "\n".join([f"- {memory.content}" for memory in ltm])
        
        speech = self.decide_how(conversation)
        evaluate_mediator_speech_prompt = evaluate_prompt_mediator_baseline.format(
            conversation_history = conversation_history,
            ltm_text = ltm_text,
            thought = speech
        )
        response = get_completion_sync(
            system_prompt="",
            user_prompt=evaluate_mediator_speech_prompt,
            temperature=0.8,
            response_format="json_object",
            model = self.model
        )
        response_text = response.get("text", "{}")
        response_data = json.loads(response_text)
        if "rating" in response_data:
            rating = float(response_data.get("rating", 3.0))
        elif "rating (1-5)" in response_data:
            rating = float(response_data.get("rating (1-5)", 3.0))
        else:
            rating = 3.0
        should_intervene = rating >= self.proactivity_config.get("intervention_threshold", 3.0)
        if should_intervene:
            return speech
        else:
            return None

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

