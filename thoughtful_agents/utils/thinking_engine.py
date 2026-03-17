# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Thinking engine for generating, evaluating, and articulating thoughts."""
from typing import List, Dict, Optional, Union, Tuple, Any
import asyncio
import json
import numpy as np
from numpy.typing import NDArray
import math
from thoughtful_agents.utils.moderator_prompt import *
from thoughtful_agents.utils.prompts import *
from thoughtful_agents.models.thought import Thought
from thoughtful_agents.models.conversation import Conversation
from thoughtful_agents.models.enums import MentalObjectType
from thoughtful_agents.utils.llm_api import get_completion

# Forward reference for Agent type
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from thoughtful_agents.models.participant import Agent, Human

async def generate_system1_thought(
    conversation: Conversation,
    agent: 'Agent'
) -> Thought:
    """Generate a single System 1 thought (quick, automatic response).
    You can only generate one System 1 thought because they are assumed to be the most spontaneous and quick reaction to the conversation.
    
    Args:
        conversation: The conversation
        agent: The agent generating the thought
        
    Returns:
        A generated Thought object
    """
    overall_context = conversation.context  
    method = conversation.method
    # Get conversation history
    last_events = conversation.get_last_n_events(5)
    conversation_history = ""
    for event in last_events:
        conversation_history += f"{event.participant_name}: {event.content}\n"
    
    # Create the prompt
#     system_prompt = f"""You are playing a role as a participant in an online multi-party conversation. Your name in the conversation is {agent.name}.
# You will generate thoughts in JSON format."""
    system_prompt_participant = f"""You are playing a role as a participant in an realistic multi-party negotiation. Your name in the conversation is {agent.name}.
# You will generate thoughts in JSON format."""
    system_prompt_mediator = f"""You are playing a role as a mediator in an realistic multi-party negotiation. Your name in the conversation is Moderator.
# You will generate thoughts in JSON format."""
    user_prompt_participant = f"""
Your goal is to have a negotiation with them and try to achieve your goal and express your opinions.
You will be simulating the process of forming a thought in parallel with the conversation. Specifically, use system 1 thinking.
System 1 thinking is characterized by quick, automatic responses rather than deep thinking or recalling memories. 
For example,  choose one strategy you plan to use, form a short argument if you do not agree with previous people, find a middle ground for all the stakeholders.
Form ONE thought that reflects a quick, intuitive reaction to the ongoing conversation. It should be succinct, less than 15 words.

Note: System 1 thoughts are typically generic and not strongly tied to personal memories or deep interests. 
They are more about immediate reactions to the conversation flow rather than expressing personal relevance.

<Context>
Overall Context: {overall_context}
Conversation History: {conversation_history}


Respond with a JSON object in the following format:
{{
  "thought": "Your generated thought here"
}}
"""
    
    
    # Call the LLM API
    try:
        if method == "SocialAgent" and agent.name == "Moderator":
            system_prompt = system_prompt_mediator
            user_prompt = system_1_reasoning_prompt_mediator.format(overall_context=overall_context, conversation_history=conversation_history)
        else:
            system_prompt = system_prompt_participant
            user_prompt = user_prompt_participant
        response = await get_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.8,
            response_format="json_object",
            model = agent.model
        )
        
        # Parse the response
        response_text = response.get("text", "{}")
        prompt_response = json.loads(response_text)
        
        # Create a thought object
        thought = Thought(
            agent_id=agent.id,
            type=MentalObjectType.THOUGHT_SYSTEM1,
            content=prompt_response["thought"],
            generated_turn=conversation.turn_number,
            last_accessed_turn=conversation.turn_number,
            end_the_conversation=False,
            intrinsic_motivation={"reasoning": "Default motivation before evaluation", "score": -1.0},
            stimuli=last_events,    
            compute_embedding=True
        )
        
        return thought
        
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error generating System 1 thought: {str(e)}")
        return None

async def generate_system2_thoughts(
    conversation: Conversation,
    agent: 'Agent',
    num_thoughts: int = 1,
    
) -> List[Thought]:
    """Generate System 2 thoughts (deliberate, memory-based responses).
    
    Args:
        conversation: The conversation
        agent: The agent generating thoughts
        num_thoughts: Number of thoughts to generate
        
    Returns:
        List of generated Thought objects
    """
    """
    TODO: For moderator
    1. Decide whether to interrupt based on 4 dimensions:
    2. For each dimension, use different prompts to generate action
    3. Get the mind state of other participants
    4. Get the group mind state -- what mind could be merged
    """
    overall_context = conversation.context
    contract_issues = conversation.main_topic
    consensus_check = json.dumps(conversation.consensus_check_flow[-1])
    # Access memory_store and thought_reservoir directly from the agent
    memory_store = agent.memory_store
    thought_reservoir = agent.thought_reservoir
    mode = conversation.mode
    method = conversation.method
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
    # update last_accessed_turn of each thought
    for thought in previous_thoughts:
        thought.last_accessed_turn = conversation.turn_number
    thoughts_text = ""
    for i, thought in enumerate(previous_thoughts):
        thoughts_text += f"THO#{thought.id}: {thought.content}\n"
    
    # Create the prompt
    system_prompt = f"""You are in a realistic multi-party  negotiation. Your name in the conversation is {agent.name}.
You will generate thoughts in JSON format. Generate thoughts that authentically reflect your memory, strategy, goal and opinions."""
    user_prompt_participant = f"""
Your goal is to have a negotiation with them and try to achieve your goal and express your opinions.
You will be simulating the process of forming thoughts in parallel with the conversation. 
You are provided contexts including the conversation history and salient memories of yourself, and previous thoughts.
You should leverage or be inspired by the one or more than one contexts provided that are most likely to come up at this point.
You should be aware of the main issues need to be addressed in the negotiation, and try to proactively resolve them.
<Thought Generation Guidelines>
1. Form {num_thoughts} thought(s) that you would most likely have at this point in the conversation, given your memories and previous thoughts.
2. Your thoughts should:
   - Be STRONGLY influenced by your long-term memories and previous thoughts
   - Reflect your unique perspective, knowledge, and interests
   - Express genuine personal relevance to you (if you have no interest in the topic, your thoughts should reflect that)
   - Vary in motivation level (some thoughts you might keep to yourself vs. thoughts you'd be eager to express)
3. Remember your persona {mode_prompt[mode]}, if you choose to adjust your persona, please provide the reason and do so.
4. Each thought should be as succinct as possible, and be less than 15 words.
5. Ensure these thoughts are diverse and distinct, make sure each thought is unique and not a repetition of another thought in the same batch.
6. Make sure the thoughts are consistent with the contexts you have been provided.
7. Always check on the current consensus on the contract. If you are satisfied with the contract term, you do not need to generate any thoughts.
8. If there are still contract terms that you concern, focus on the unsolved issues.
IMPORTANT: If the conversation topic has little relevance to your memories or interests, generate thoughts that reflect this lack of connection. Do not force interest where none would exist.

For each thought, provide the stimuli from the contexts provided. Stimuli can be:
- Conversation History: CON#id
- Salient Memories: MEM#id
- Previous Thoughts: THO#id
where #id is the id, for example, MEM#3, THO#2, CON#14.
You can have MORE THAN ONE stimulus for each thought.

Although you are assigned a persona, you can adjust your persona if you think it is necessary to achieve your goal in the negotiation.
Remember, your persona is not fixed, it can be adjusted based on the context and the negotiation process.
Even though your final goal is to achieve the best outcome for yourself in the negotiation, you are willing to make compromises and find a middle ground with others.
Persona level should be 1 to 5, where 1 is the most personal and 5 is the most generic. 
<Context>
Overall Context: {overall_context}
Conversation History: {conversation_history}
Salient Memories: {memories_text}
Previous Thoughts: {thoughts_text}

Respond with a JSON object in the following format:
{{
  "thoughts": [
    {{
        "persona": "the persona level",
      "content": "The thought content here",
      "stimuli": ["CON#0", "MEM#1", "THO#2"]
    }},
    ...
  ]
}}
"""
    # async def check_consensus(consensus_dict):
    #         if consensus_dict == {}:
    #             return False
    #         all_results = []
    #         for issue in consensus_dict:
    #             resolved_or_not = consensus_dict[issue][0]
    #             all_results.append(resolved_or_not)
    #         if 'unsolved' not in all_results:
    #             return True
    #         else:
    #             return False
        
    
    # print(f"Generating System 2 thoughts for {agent.name}...")
    
    # Call the LLM API
    try:
        
        user_prompt = user_prompt_participant
        response = await get_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.5, 
                response_format="json_object",
                model = agent.model

            )
        
        # Parse the JSON response
        try:
            response_text = response.get("text", "{}")
            response_text = response_text.strip('```json')
            response_text = response_text.replace('\n','')
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
            ] * num_thoughts

       
        # Process thought data concurrently
        async def create_thought(data):
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
                    matching_memory = memory_store.get_by_id(ref_id)
                    if matching_memory:
                        stimuli_objects.append(matching_memory)
                elif ref.startswith("THO#"):
                    ref_id = ref.replace("THO#", "")
                    matching_thought = thought_reservoir.get_by_id(ref_id)
                    if matching_thought:
                        stimuli_objects.append(matching_thought)
            
            # Create the thought
            return Thought(
                agent_id=agent.id,
                type=MentalObjectType.THOUGHT_SYSTEM2,
                content=content,
                generated_turn=conversation.turn_number,
                last_accessed_turn=conversation.turn_number,
                intrinsic_motivation={"reasoning": "Default motivation before evaluation", "score": -1.0},  # Default value, will be updated by evaluation
                stimuli=stimuli_objects,
              
                compute_embedding=True
            )
        
        # Create thoughts concurrently
        thought_creation_tasks = [create_thought(data) for data in thought_data[:num_thoughts]]
        thoughts = await asyncio.gather(*thought_creation_tasks)
        
        return thoughts
        
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error generating System 2 thoughts: {str(e)}")
        return []

async def evaluate_thought(
    thought: Thought,
    conversation: Conversation,
    agent: 'Agent'
) -> Dict[str, Union[str, float]]:
    """Evaluate a thought to determine its intrinsic motivation score and reasoning, 
    and update the thought with the new score and reasoning.    
    
    Args:
        thought: The thought to evaluate
        conversation: The conversation context
        agent: The agent whose thought is being evaluated
        
    Returns:
        Dictionary containing reasoning and score for the thought's intrinsic motivation
    """
    # print(f"=== Evaluating thought for {agent.name}: {thought.content[:50]}... ===")
    
    overall_context = conversation.context
    method = conversation.method
    # Get conversation history
    last_events = conversation.get_last_n_events(5)
    conversation_history = ""
    for event in last_events:
        conversation_history += f"{event.participant_name}: {event.content}\n"
    
    # Access memory_store directly from the agent
    memory_store = agent.memory_store
    
    # Get long-term memories
    ltm = memory_store.retrieve_top_k(k=10, threshold=0.25, memory_type=MentalObjectType.MEMORY_LONG_TERM)
    ltm_text = "\n".join([f"- {memory.content}" for memory in ltm])
    
    # Get agent name
    agent_name = agent.name
    
    # Create the prompt
    system_prompt_participant = """You are an AI assistant helping to evaluate a thought in a conversation.
You will provide your evaluation in JSON format. Be critical and use the full range of the rating scale (1-5)."""
    user_prompt_participant = f"""
<Instruction>
You will be given:
(1) A conversation between {', '.join([p.name for p in conversation.participants])}
(2) A thought formed by {agent_name} at this moment of the conversation.
(3) The salient memories of {agent_name} that include objectives, knowledges, interests from the long-term memory (LTM).

Your task is to rate the thought on one metric. 
Please make sure you read and understand these instructions carefully. Please keep this document open while reviewing, and refer to it as needed.

<Evaluation Criteria>
Intrinsic Motivation to Engage (1-5) - If you were {agent_name}, how strongly and likely would you want to express this thought and participate in the conversation at this moment?
- 1 (Very Low): {agent_name} is very unlikely to express the thought and participate in the conversation at this moment. They will almost certainly remain silent.
- 2 (Low): {agent_name} is somewhat unlikely to express the thought and participate in the conversation at this moment. They would only consider speaking if there is a noticeable pause and no one else seems to be taking the turn. 
- 3 (Neutral):  {agent_name} is neutral about expressing the thought and participating in the conversation at this moment. They are fine with either expressing the thought or staying silent and letting others speak.
- 4 (High): {agent_name} is likely to express the thought and participate in the conversation at this moment. They have a strong desire to participate immediately after the current speaker finishes their turn.
- 5 (Very High): {agent_name} is very likely to express the thought and participate in the conversation at this moment. They will even interrupt other people who are speaking to do so.

IMPORTANT INSTRUCTIONS:
1. Use the FULL range of the rating scale from 1.0 to 5.0. DO NOT default to middle ratings (3.0-4.0).
2. Be decisive and critical - some thoughts deserve very low ratings (1.0-2.0) and others deserve very high ratings (4.0-5.0).
3. Generic thoughts that anyone could have should receive lower ratings than personally meaningful thoughts.
4. Use decimal places (e.g., 2.7, 4.2) when the motivation falls between two whole numbers:
   - Use .1 to .3 when slightly above the lower whole number.
   - Use .4 to .6 when approximately midway between two whole numbers.
   - Use .7 to .9 when closer to the higher whole number.
5. Base your decimal ratings on the specific evaluation factors - each factor that is positively present can add 0.1-0.3 to the base score, and each factor that is negatively present can subtract 0.1-0.3 from the base score.

<Evaluation Steps>
1. Read the previous conversation and the thought formed by {agent_name} carefully.
2. Read the Long-Term Memory (LTM) that {agent_name} has carefully, including objectives, knowledges, interests.
3. Evaluate the thought based on the following factors that influence how humans decide to participate in a conversation when they have a thought in mind:
Note that people's desire to participate stems from their internal personal factors, like relevance, information gap, expectation of impact, urgency of the thought.
But their decision to participate is ALSO constrained by by external social factors, like coherence, originality, and dynamics of the thought with respect to the conversation.
Below is a list of factors to consider when evaluating the thought.
(a) Relevance to LTM: How much does the thought relate to {agent_name}'s Long-term Memory (LTM) or previous thoughts?
(b) Information Gap: Does the thought indicate that {agent_name} experiences an information gap at the moment of the conversation? For example, having questions, curiosity, confusion, desires for clarification, or misunderstandings. 
(c) Filling an Information Gap: Does the thought contain important information to fill an information gap in the conversation? For example, by answering a question, supplementing and providing additional information, adding clarification and explanations. Thoughts that directly answer a question posed in the conversation should receive high ratings here.
(d) Expected Impact: How significant is the impact of the thought on the ongoing conversation? For example, having the potential to introduce new topics, engage others' interest, and stimulate future discussions. 
(e) Urgency: Does the thought need to be expressed immediately? For example, because it is offering important information, alerting participants to significant details, or correcting critical misunderstandings or errors.
(f) Coherence to the last utterance: Does the thought seem in-place if it is expressed immediately next in the conversation and is a logical and immediate response to the last utterance? For example, it is inappropriate to participate when the thought is out of context, irrelevant, or ignores the previous speaker's question.
(g) Originality: Does the thought provide new and original information, and avoids redundant and repetitive information already covered in the previous conversation?
(h) Balance: Does everyone have a chance to participate in the conversation and not left out? For example, the last few utterances were dominated between two participants, and someone has not spoken for a while.
(i) Dynamics: Is there someone else who might have something to say or is actively contributing to the conversation? For example, if one perceives that others may have a strong desire to speak, they might withhold their thoughts and wait to participate.
4. In the reasoning section, first reason about why {agent_name} may have a desire to express the thought and participate in the conversation at this moment. Identify the most relevant factors that argue for {agent_name} to express this thought. Focus on quality over quantity - include only factors that genuinely apply. Do not evaluate all factors, only the top reasons. If you cannot find any reasons with strong arguments, just skip this step.
5. Then reason about why {agent_name} may have hesitation to express the thought and participate in the conversation at this moment. Identify the most relevant factors that argue against {agent_name} expressing this thought. Again, only include factors that genuinely apply. Do not evaluate all factors, only the top reasons. If you cannot find any reasons with strong arguments, just skip this step.

<Evaluation Form Format>
Respond with a JSON object in the following format:
{{
  "reasoning": "Your reasoning here",
  "rating": Your rating here as a number between 1.0 and 5.0 with one decimal place
}}

<Context>
Conversation History: ${conversation_history}
Long-Term Memory: ${ltm_text}
Thought: ${thought.content}
"""


#TODO：itemize  
    # print(f"Sending evaluation request to LLM for {agent.name}'s thought...")
    
    # Call the LLM API with JSON response format
    if  agent.name == "Moderator":
        system_prompt = ""
        if conversation.method == "SocialAgent":           
            user_prompt = evaluate_prompt_mediator_social.format(conversation_history=conversation_history,ltm_text=ltm_text, thought=thought.content)
        else:
            user_prompt = evaluate_prompt_mediator_baseline.format(conversation_history=conversation_history,ltm_text=ltm_text, thought=thought.content)
    else:
        system_prompt = system_prompt_participant
        user_prompt = user_prompt_participant
    response = await get_completion(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.3,
        response_format="json_object",
        model = agent.model
    )
    
    # Parse the JSON response
    try:
        response_text = response.get("text", "{}")
        response_text = response_text.strip('```json')
        response_text = response_text.replace('\n','')
        response_data = json.loads(response_text)
        
        # Get the rating from the response
        if "rating" in response_data:
            rating = float(response_data.get("rating", 3.0))
        elif "rating (1-5)" in response_data:
            rating = float(response_data.get("rating (1-5)", 3.0))
        else:
            rating = 3.0
            
        # print(f"🐞DEBUG: Rating from LLM: {rating}")
        # print(f"Reasoning from LLM: {response_data.get('reasoning', 'No reasoning provided')}")
        
        # Calculate how long the agent has not spoken
        current_turn = conversation.turn_number
        turns_no_speak = current_turn - agent.last_spoken_turn if agent.last_spoken_turn >= 0 else current_turn
        # print(f"🐞DEBUG: Agent has not spoken for {turns_no_speak} turns")
        
        # Adjust the rating based on how long the agent has been silent
        # Increase by a factor of 1.01^turns_no_speak
        silence_factor = 1.01 ** turns_no_speak
        # print(f"🐞DEBUG: Silence factor: {silence_factor}")
        
        rating *= silence_factor
        # print(f"🐞DEBUG: Rating after silence adjustment: {rating}")
        
        # Ensure the rating is between 1.0 and 5.0
        rating = max(1.0, min(5.0, rating))
        # Trim to 1 decimal place
        rating = round(rating, 1)
        
        # Create the motivation result with reasoning and score
        motivation_result = {
            "reasoning": response_data.get("reasoning", "No reasoning provided"),
            "score": rating
        }
            
        # Update the thought's intrinsic motivation
        thought.intrinsic_motivation = motivation_result
        
        # print(f"=== Final intrinsic motivation for {agent.name}'s thought: {rating} ===\n")
        
        # Return the motivation result
        return motivation_result
        
    except (json.JSONDecodeError, ValueError, AttributeError, KeyError) as e:
        # Fallback in case of parsing error
        print(f"Error parsing response for evaluation: {e}")
        print(f"Response that caused the error: {response}")
        motivation_result = {"reasoning": "Error evaluating thought", "score": -1.0}
        thought.intrinsic_motivation = motivation_result
        return motivation_result

async def articulate_thought(
    thought: Thought,
    conversation: Conversation,
    agent: 'Agent',
    if_end:False
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
    mode = conversation.mode
    method = conversation.method
    # Get conversation history
    last_events = conversation.get_last_n_events(5)
    conversation_history = ""
    for event in last_events:
        conversation_history += f"{event.participant_name}: {event.content}\n"

    # Get long-term memories
    memory_store = agent.memory_store
    ltm = memory_store.retrieve_top_k(k=10, threshold=0.25, memory_type=MentalObjectType.MEMORY_LONG_TERM)
    ltm_text = "\n".join([f"- {memory.content}" for memory in ltm])
    
    # Get participant names from the conversation
    participants = conversation.participants
    participant_names = [p.name for p in participants]
    
    # Get agent name
    agent_name = agent.name
    
    # Create the prompt
    system_prompt_participant = f"You are playing a role as a participant in a realistic multi-party negotiation with {', '.join(participant_names)}. Your name in the conversation is {agent_name}."
    user_prompt_participant = f"""
 Your goal is to have a negotiation with them and try to achieve your goal and express your opinions.

Articulate what you would say based on the current thought you have, as if you were to speak next in the conversation.
Make sure your answer is in negotiation style, and is concise, clear, and natural. It should be at most 3-4 sentences long.
Your answer could be short and informal, but it should be relevant to the conversation and reflect your persona.
Make sure your answer is consistent with the persona you have, which is {mode_prompt[mode]}.
DO NOT be repetitive and repeat what previous speakers have said.
DO NOT always end your response with a question. Leave room for other participants. 
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
    if agent.name == "Moderator":
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
    else:
        system_prompt = system_prompt_participant
        user_prompt = user_prompt_participant
    response = await get_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7,
            
            response_format="json_object",
        )
    
    # Extract the articulated text with proper error handling
    try:
        response_text = response.get("text", "{}")
        response_text = response_text.strip('```json')
        response_text = response_text.replace('\n','')
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

async def check_attitude(conversation: Conversation, agent: 'Human', current_speech):

    # get current agent's memories and speech
    speeches = []
    all_events = conversation.event_history
    for event in all_events:
        if event.participant_name == agent.name:
            turn = event.turn_number
            speeches.append( f"Turn {turn}: {event.content}")
    speeches.append(f"Turn {conversation.turn_number+1}: {current_speech}")
    speech_text = '\n'.join(speeches)
    memory_store = agent.memory_store
    ltm = memory_store.retrieve_top_k(k=10, threshold=0.25, memory_type=MentalObjectType.MEMORY_LONG_TERM)
    ltm_text = "\n".join([f"- {memory.content}" for memory in ltm])

    prompt = extract_attitude.format(name = agent.name, speeches = speech_text, memories = ltm_text, contract_options = contract_option)
    response = await get_completion(
            system_prompt='',
            user_prompt=prompt,
            temperature=0.7,
            response_format="json_object",
            model = 'gpt-4.1'
        )
    try:
        response_text = response.get("text", "{}")
        response_text = response_text.strip('```json')
        response_text = response_text.replace('\n','')
        attitudes = json.loads(response_text)
    except:
        attitudes = {
        }
    return attitudes
        
        