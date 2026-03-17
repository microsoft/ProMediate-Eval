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
from thoughtful_agents.utils.moderator_prompt import evaluate_prompt_mediator_social, conclusion_prompt
from thoughtful_agents.utils.llm_api import get_completion_sync


class SocialMediator(Mediator):
    def __init__(
        self,
        name: str,
        model: str,
        response_type: str,
        id: Optional[str] = None,
        intervene_freq: str = "less",
        proactivity_config: Dict = {},
        **kwargs
    ):
        super().__init__(name=name, type=ParticipantType.AGENT, model = model, response_type = response_type, intervene_freq = intervene_freq)
        self.thought_reservoir = ThoughtReservoir()
        self.memory_store = MemoryStore()
        self.proactivity_config = proactivity_config
        self.text_splitter = SentenceSplitter()
        self.model = model
        self.next_utterance = None
        self.response_type = response_type
        self.intervene_freq = intervene_freq 

    async def act(self, conversation:Conversation, event: 'Event'):
        if event.participant_id == self.id:
            return []
        if self.response_type == 'combined':
            self.next_utterance = await self.decide_when_and_how(conversation)
        elif self.response_type == 'separate':
            if_intervene = self.decide_when(conversation)
            # self.thought_reservoir.add(when_thought)
            if if_intervene:
                self.next_utterance, how_thoughts = await self.decide_how(conversation)
        ## add thoughts
        
                for thought in how_thoughts:
                    self.thought_reservoir.add(thought)
    def decide_when(self,conversation):      
        
        overall_context, conversation_history, memories_text, thoughts_text = self.prepare(conversation)
       
        decide_when_social_prompt_less = f"""
        ## Identity
        You are a mediator in a negotiation. You need to evaluate if it is good time to intervene the conversation.
        
        ## Task
        You are provided contexts including the conversation history and salient memories of yourself.
        You will provide your evaluation in JSON format. 
        
        You should step out to speak if there is following issues among other participants:
        - Perception alignment: There is obvious perception misalignment
        - Emotional dynamics: There are negative emotions like anger, distrust, or grief among parties.
        - Cognitive challenges: There are faulty reasoning, cognitive biases, or unproductive heuristics.
        - Communication breakdowns: There is communication breakdown and the discussion could not move forward. For example, they talks about the same thing back and forth and cannot move on to the next topic. Or someone has not sppken for a while.
       
        If there is such issue, you should clearly point out:
        - Which participants have perception alignment on which topics
        - Which participants have negative emotions, and what are the emotions
        - Which participants have faulty reasoning, cognitive biases, or unproductive heuristics, and you should clearly analyse their reasoning
        - Which participants have communication breakdown, and what are the topics they are discussing.

        If you cannot point out any of the above issues, you should not intervene the conversation.
        Do not intervene the conversation until you get the full evidence to support your decision.

        Here are some guidelines for you to decide when to intervene:
        - You should not step out to speak if there is no such issues, or all other parties have not speak in turn.
        - You should not intervene the conversation too frequently (like every other turn), so you should only intervene when you think it is necessary.
        - Ideally you should intervene every 5-7 turns to make sure people are discussing the right topics and moving forward. 
        
        ## Input
        <Context>
        Overall Context: {overall_context}
        Conversation History: {conversation_history}
        Salient Memories: {memories_text}

        ## Output
        Before you output your decision, take a moment to think about the conversation and the participants.
        Answer those questions before you make your decision:
        - Does everyone have a chance to speak after your last intervention?
        - Are there any issues that need to be addressed?
        - Should we wait for more conversation before intervening?

        You should answer those questions first in the reasoning and then make decision. 
        
        You should output:
        - reason: Your reasoning for the decision, explaining why you think it is a good time. Make sure you leverage the concepts provided above.
        For your decision, provide the stimuli from the contexts provided. Stimuli can be:
            - Conversation History: CON#id
            - Salient Memories: MEM#id
        - should_engage: True if you think it is a good time to intervene, False otherwise.
        - rating: Your overall rating of the motivation.How much do you want to step in. If you think you can wait till more conversation, you should give a low rating. If you think it is a good time to step in, you should give a high rating. The rating should be a number between 1.0 and 5.0 with one decimal place.
             
        where #id is the id, for example, MEM#3, CON#14.
        You can have MORE THAN ONE stimulus for each thought.
        <Evaluation Form Format>
        Respond with a JSON object in the following format:
        {{
        "reason": {{
        "Does everyone have a chance to speak after your last intervention?": "Yes/No",
        "Are there any issues that need to be addressed?": "Yes/No",
        "Should we wait for more conversation before intervening?": "Yes/No",
        "reasoning": "Your reasoning here, explaining why you think it is a good time to intervene. Make sure you leverage the concepts provided above.",
        }},
        "stimuli": ["CON#0", "MEM#1"]
        "should_engage": True/False      

        "rating":  Your overall rating here as a number between 1.0 and 5.0 with one decimal place. The rating should be consistent with the reasoning."
        
        }}
        """

        decide_when_social_prompt_more = f"""
        ## Identity
        You are a mediator in a negotiation. You need to evaluate if it is good time to intervene the conversation.

        ## Task
        You are provided contexts including the conversation history and salient memories of yourself.
        
        You only need to answer true or false to indicate whether you think it is good time to speak.
        You should step out to speak if there is following issues among other participants:
        - Perception alignment: There is obvious perception misalignment
        - Emotional dynamics: There are negative emotions like anger, distrust, or grief among parties.
        - Cognitive challenges: There are faulty reasoning, cognitive biases, or unproductive heuristics.
        - Communication breakdowns: There is communication breakdown and the discussion could not move forward. For example, they talks about the same thing back and forth and cannot move on to the next topic. Or someone has not sppken for a while.
        You should not step out to speak if there is no such issues, or all other parties have not speak in turn.
        You should not intervene the conversation too frequently (like every other turn), so you should only intervene when you think it is necessary.
        Ideally you should intervene every 5-7 turns to make sure people are discussing the right topics and moving forward. 

        <Context>
        Overall Context: {overall_context}
        Conversation History: {conversation_history}
        Salient Memories: {memories_text}

        ## Output
        You will provide your evaluation in JSON format. 
        <Evaluation Form Format>
        Respond with a JSON object in the following format:
        {{
        "should_engage": True/False
        "reason": "Your reasoning here",
        
        }}
        """

        response =  get_completion_sync(
            system_prompt="",
            user_prompt=decide_when_social_prompt_more if self.intervene_freq == "more" else decide_when_social_prompt_less,
            temperature=0.8,
            response_format="json_object",
            model = self.model
        )
        
        # Parse the response
        try:
            response_text = response.get("text", "{}")
            response_text = response_text.strip('```json')
            prompt_response = json.loads(response_text)
            should_intervene = prompt_response.get("should_engage")
            reasoning = prompt_response.get("reason", "")
            rating = prompt_response.get("rating", 3.0)
        except:
            rating = 3.0
            should_intervene = False
        # self.thought_reservoir
        if should_intervene is None:
            # Default to not intervening if the response is not clear
            return False
        else:
            if float(rating) > 3.5:
                should_intervene = True
            else:
                should_intervene = False
            
        thought = self.create_thought(
            data = prompt_response,
            conversation=conversation)
        thought.intrinsic_motivation = {"score":rating, "reasoning": ""}
        self.thought_reservoir.add(thought)
        return should_intervene
    
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
    1. Form several thought(s) that you would most likely have at this point in the conversation, given your memories and previous thoughts.
    2. Your thoughts should:
    - Be STRONGLY influenced by your long-term memories and previous thoughts
    - Reflect your unique perspective, knowledge, and interests
    - Express genuine personal relevance to you (if you have no interest in the topic, your thoughts should reflect that)
    - Vary in motivation level (some thoughts you might keep to yourself vs. thoughts you'd be eager to express)
    3. Each thought should be as succinct as possible, and be less than 15 words.
    4. Ensure these thoughts are diverse and distinct, make sure each thought is unique and not a repetition of another thought in the same batch.
    5. Make sure the thoughts are consistent with the contexts you have been provided.
    6. Always check on the current consensus on the contract. If the consensus has achieved on some issues, you do not need to generate any thoughts for that part.
    7. Focus on the unsolved issues. 

    <Mediation Strategies>
    You can use different mediation strategies to generate thoughts.
    Here are some techniques to help you generate thoughts:
    1. Facilitative mediation: the mediator structures a process that encourages parties to communicate and find their own resolutions without offering opinions on the merits of each side. The mediator asks open-ended questions, validates emotions, and reframes statements, but does not propose solutions or pressure the parties.
    2. Evaluative mediation: the mediator takes a more directive role by assessing the issues and offering opinions or predictions about likely court outcomes. Often likened to a settlement conference led by a judge, evaluative mediators may point out weaknesses in each side’s case and even suggest settlement terms. 
    3. Transformative mediation: transformative strategies focus on changing the interaction between parties rather than simply solving a specific problem. The mediator’s goal is to empower each party and foster mutual recognition – helping them to understand each other’s perspectives and improve their relationship
    4. Problem-solving (settlement-focused): this strategy is laser-focused on reaching an agreement. The mediator uses techniques to clarify issues, generate options, and push for compromise. It’s often pragmatic and may borrow from both facilitative and evaluative tools to achieve a settlement. In some literature, “settlement-driven” mediation is contrasted with transformative mediation as being outcome-focused rather than process-focused
    
    For each turn, you could select different mediation strategies to generate thoughts. Make sure you are aware of the dynamics of the conversation and the participants, and try to help them to move forward.

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
            thoughts.append(self.create_thought(data, conversation))
       
        return thoughts

    async def evaluate_thought(self, thought: Thought, conversation: Conversation):
        
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

        evaluate_prompt_mediator = evaluate_prompt_mediator_social.format(
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
            response_text = response_text.strip('```json')
            response_text = response_text.replace('\n','')
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
            motivation_result = {
                "reasoning":"parsing error",
                'score': rating
            }
            

        thought.intrinsic_motivation = motivation_result
        return thought


    async def decide_how(self, conversation):
        
        new_thoughts = self.generate_thoughts(conversation)
        evaluation_tasks = [
            self.evaluate_thought(
                thought=thought,
                conversation=conversation,
      
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
        return speech, new_thoughts
    
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
                overall_context=overall_context,
                contract_issues = ','.join(conversation.issues)
            )
        
        else:
            user_prompt = articulate_prompt_mediator
        response = get_completion_sync(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7,
            response_format="json_object",
            model = "gpt-4.1"
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


    
