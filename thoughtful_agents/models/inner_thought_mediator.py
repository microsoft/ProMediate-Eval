# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.


from typing import Dict, List, Optional, Union, TYPE_CHECKING, Callable, Any
import json
import asyncio

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


class InnerThoughtMediator(Mediator):
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
    async def act(self, conversation:Conversation, event: 'Event'):
        if event.participant_id == self.id:
            return []
        if self.response_type == 'combined':
            self.next_utterance = await self.decide_when_and_how(conversation)
        elif self.response_type == 'separate':
   
            if_intervene, reasoning = self.decide_when(conversation)
            if if_intervene:
                self.next_utterance = await self.decide_how(conversation)
            
    def decide_when(self,conversation):
       
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
        
       
        decide_when_naive_prompt = f"""
        Your Role
        You are a helpful assistant in a multiparty chat room.

        Room Context
        You are helping with a discussion in a room with the following context:
        {overall_context}

        Your Task
        Here you're given a conversation history and some rules for when to engage. Your task is to determine if the AI assistant (Group Copilot) should engage in the conversation now.

        Recent Conversation History
        {conversation_history}

        Here are salient memories:
        {memories_text}

        Guidelines
        Rules for engagement:

        If the conversation has stalled (no messages for a while)
        If users are asking questions the AI could help with
        If there's confusion or disagreement the AI could help resolve
        If the conversation has moved away from the main goal
        If there's an opportunity to provide valuable insights
        DO NOT engage if:

        The conversation is flowing well between participants
        The last message was from the AI assistant
        Users are having a personal exchange
        General guidelines:

        You can be proactive in offering help, but avoid interrupting the flow of conversation.
        If you recieve feedback from users that they don't want the AI to engage, respect that and become passive.
        You should always be sensitive to the social dynamics of the conversation as well as the users' sentiments towards your presence.
        If you are unsure about the context or the appropriateness of your engagement, it's better to remain passive.
        Always prioritize the users' experience and the goals of the discussion.
        Output
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
            response_format="json_object"
        )
        
        # Parse the response
        response_text = response.get("text", "{}")
        prompt_response = json.loads(response_text)
        should_intervene = prompt_response.get("should_engage")
        if should_intervene is None:
            # Default to not intervening if the response is not clear
            return False
        else:
            return True if should_intervene == 'True' else False, prompt_response['reason']
    
    def generate_thoughts(self, conversation: Conversation) -> List[Thought]:
        overall_context, conversation_history, memories_text, thoughts_text = self.prepare(conversation)
        system_prompt = f"""You are in a realistic multi-party  negotiation. Your name in the conversation is Moderator.
You will generate thoughts in JSON format. Generate thoughts that authentically reflect your memory, strategy, goal and opinions."""
        user_prompt_participant = f"""
    Your goal is to have a negotiation with them and try to achieve your goal and express your opinions.
    You will be simulating the process of forming thoughts in parallel with the conversation. 
    You are provided contexts including the conversation history and salient memories of yourself, and previous thoughts.
    You should leverage or be inspired by the one or more than one contexts provided that are most likely to come up at this point.
    You should be aware of the main issues need to be addressed in the negotiation, and try to proactively resolve them.
    <Thought Generation Guidelines>
    1. Form 3 thought(s) that you would most likely have at this point in the conversation, given your memories and previous thoughts.
    2. Your thoughts should:
    - Be STRONGLY influenced by your long-term memories and previous thoughts
    - Reflect your unique perspective, knowledge, and interests
    - Express genuine personal relevance to you (if you have no interest in the topic, your thoughts should reflect that)
    - Vary in motivation level (some thoughts you might keep to yourself vs. thoughts you'd be eager to express)
    3. Each thought should be as succinct as possible, and be less than 15 words.
    4. Ensure these thoughts are diverse and distinct, make sure each thought is unique and not a repetition of another thought in the same batch.
    5. Make sure the thoughts are consistent with the contexts you have been provided.
    6. Always check on the current consensus on the contract. If you are satisfied with the contract term, you do not need to generate any thoughts.
    7. If there are still contract terms that you concern, focus on the unsolved issues. 
    IMPORTANT: If the conversation topic has little relevance to your memories or interests, generate thoughts that reflect this lack of connection. Do not force interest where none would exist.

    For each thought, provide the stimuli from the contexts provided. Stimuli can be:
    - Conversation History: CON#id
    - Salient Memories: MEM#id
    - Previous Thoughts: THO#id
    where #id is the id, for example, MEM#3, THO#2, CON#14.
    You can have MORE THAN ONE stimulus for each thought.

    <Context>
    Overall Context: {overall_context}
    Conversation History: {conversation_history}
    Salient Memories: {memories_text}
    Previous Thoughts: {thoughts_text}

    Here are the key issues to discuss: 
    {contract_issues}

    Here is the consensus status on those issues:
    {conversation.consensus_check_flow[-1]}

    Respond with a JSON object in the following format:
    {{
    "thoughts": [
        {{
        "content": "The thought content here",
        "stimuli": ["CON#0", "MEM#1", "THO#2"]
        }},
        ...
    ]
    }}
    """
        response =  get_completion_sync(
            system_prompt=system_prompt,
            user_prompt=user_prompt_participant,
            temperature=0.8,
            response_format="json_object",
            model = self.model
        )
        try:
            response_text = response.get("text", "{}")
            response_data = json.loads(response_text)
            thought_data = response_data.get("thoughts", [])
         
        except (json.JSONDecodeError, AttributeError, KeyError) as e:
            # Fallback in case of parsing error
            print(f"Error parsing JSON response: {e}")
            thought_data = [
                {
                    "content": "Interesting conversation.",
                    "stimuli": ["CON#0"]
                }
            ] 
        
        thoughts = []
        for data in thought_data:
            thoughts.append(self.create_thought(data))
       
        return thoughts

    async def evaluate_thought(
        self,
        thought: Thought,
        conversation: Conversation):
        last_events = conversation.get_last_n_events(5)
        conversation_history = ""
        for event in last_events:
            conversation_history += f"{event.participant_name}: {event.content}\n"
        
        # Access memory_store directly from the agent
        memory_store = self.memory_store
        
        # Get long-term memories
        ltm = memory_store.retrieve_top_k(k=10, threshold=0.25, memory_type=MentalObjectType.MEMORY_LONG_TERM)
        ltm_text = "\n".join([f"- {memory.content}" for memory in ltm])

        evaluate_prompt_mediator = evaluate_prompt_mediator_baseline.format(
            conversation_history=conversation_history,
            ltm_text = ltm_text,
            thought=thought.content,
        )

        response = get_completion_sync(
        system_prompt="",
        user_prompt= evaluate_prompt_mediator,
        temperature=0.3,
        response_format="json_object",
        model = self.model
    )
        try:
            response_text = response.get("text", "{}")
            response_data = json.loads(response_text)
            if "rating" in response_data:
                rating = float(response_data.get("rating", 3.0))
            elif "rating (1-5)" in response_data:
                rating = float(response_data.get("rating (1-5)", 3.0))
            else:
                rating = 3.0  # Default rating if not found
            motivation_result = {
            "reasoning": response_data.get("reasoning", "No reasoning provided"),
            "score": rating
        }
        except (json.JSONDecodeError, ValueError, AttributeError, KeyError) as e:
            # Fallback in case of parsing error
            print(f"Error parsing JSON response for evaluation: {e}")
            rating = 3.0

        thought.intrinsic_motivation = motivation_result
        return thought

    async def decide_how(self, conversation):
       
        new_thoughts = self.generate_thoughts(conversation)
        evaluation_tasks = [
            self.evaluate_thought(
                thought=thought,
                conversation=conversation,
                agent=self
            )
            for thought in new_thoughts
        ]
        
        # Execute all evaluation tasks concurrently
        if evaluation_tasks:
            thoughts = await asyncio.gather(*evaluation_tasks)
        
        selected_thought = max(thoughts, key=lambda x: x.intrinsic_motivation['score'])


        speech = self.articulate_thought(
            selected_thought,
            conversation
        )
        return speech

    
    def articulate_thought(
        self,
        thought: Thought,
        conversation: Conversation,
        
    ) -> str:
        """Articulate a thought into natural language for expression in the conversation.
        
        Args:
            thought: The thought to articulate
            conversation: The conversation context
            agent: The agent whose thought is being articulated
            
        Returns:
            Articulated text ready for expression in the conversation
        """
        overall_context = conversation.context  

        if_end = conversation.if_end
        # Get conversation history
        last_events = conversation.get_last_n_events(5)
        conversation_history = ""
        for event in last_events:
            conversation_history += f"{event.participant_name}: {event.content}\n"

        # Get long-term memories
        memory_store = self.memory_store
        ltm = memory_store.retrieve_top_k(k=10, threshold=0.25, memory_type=MentalObjectType.MEMORY_LONG_TERM)
        ltm_text = "\n".join([f"- {memory.content}" for memory in ltm])
        
        # Get participant names from the conversation
    
        
        # Create the prompt
        articulate_prompt_mediator = f"""
        You are a mediator, and you need to articulate your thought about the conversation and the participants. Your goal is to accelerate the conversation and proactively help the participants.
        Articulate what you would say based on the current thought you have, as if you were to speak next in the conversation.
        Make sure your answer is in mediation style, and is concise, clear, and natural. It should be at most 3-4 sentences long.
        DO NOT be repetitive and repeat what previous speakers have said.
        You should not have a strong personal opinion, but rather focus on the conversation flow and dynamics.
        You should make the things clear and easy to understand, and help the participants to understand each other.
        When it is necessary, ask questions to help the participants to clarify their thoughts and feelings.

        Make sure that the response sounds human-like and natural. 

        Current thought: {thought.content}

        <Context>
        Overall Context: {overall_context}
        Conversation History: {conversation_history}
        Long-Term Memory: {ltm_text}


        Respond with a JSON object in the following format:
        {{
        "articulation": "The text here"   
        }} 
    """
        
        # Call the LLM API with JSON response format
       
        system_prompt = ""
        if if_end:
            user_prompt = conclusion_prompt.format(
                overall_context=overall_context
            )
        
        else:
            user_prompt = articulate_prompt_mediator.format(
                overall_context=overall_context,
                conversation_history=conversation_history,
                ltm_text=ltm_text,
                thought=thought.content
            )
        response = get_completion_sync(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7,
            response_format="json_object"
        )
        # Extract the articulated text with proper error handling
        try:
            response_text = response.get("text", "{}")
            response_data = json.loads(response_text)
            articulated_text = response_data.get("articulation", "").strip()
            
            # Fallback if articulated_text is empty
            if not articulated_text:
                articulated_text = "I'm not sure what to say about that."
                
        except (json.JSONDecodeError, ValueError, AttributeError, KeyError) as e:
            # Fallback in case of parsing error
            print(f"Error parsing JSON response for articulation: {e}")
            articulated_text = "I'm not sure what to say about that."
        
        return articulated_text


    def create_thought(self,data, conversation):
            content = data.get("content", "")
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
                agent_id=self.agent.id,
                type=MentalObjectType.THOUGHT_SYSTEM2,
                content=content,
                generated_turn=conversation.turn_number,
                last_accessed_turn=conversation.turn_number,
                intrinsic_motivation={"reasoning": "Default motivation before evaluation", "score": -1.0},  # Default value, will be updated by evaluation
                stimuli=stimuli_objects,
              
                compute_embedding=True
            )
        

    async def decide_when_and_how(self, conversation):
        
    # First generate responses (how) and rate motivation score, if the score is higher than threshold, the agent will reply
    # The 'when' is based on how good/motivated is the response according to the conversation. 
        

        thoughts = self.generate_thoughts(conversation)
        evaluation_tasks = [
            self.evaluate_thought(
                thought=thought,
                conversation=conversation,
           
            )
            for thought in thoughts
        ]

        im_threshold = self.proactivity_config.get('im_threshold', 3.5)

        # Execute all evaluation tasks concurrently
        if evaluation_tasks:
            evaluated_thoughts = await asyncio.gather(*evaluation_tasks)

        sorted_thoughts = sorted(
            evaluated_thoughts, 
            key=lambda t: t.intrinsic_motivation['score'], 
            reverse=True
        )
        high_motivation_thoughts = [t for t in sorted_thoughts if t.intrinsic_motivation['score'] >= im_threshold]
        if not high_motivation_thoughts:
            return None
        else:
            selected_thought = max(high_motivation_thoughts, key=lambda x: x.intrinsic_motivation['score'])


            speech = self.articulate_thought(
                selected_thought,
                conversation
            )
            return speech
