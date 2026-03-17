# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import random
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
import asyncio

# Use TYPE_CHECKING to avoid circular imports
if TYPE_CHECKING:
    from thoughtful_agents.models.conversation import Conversation, Event
    from thoughtful_agents.models.participant import Agent

# Import directly to fix the NameError
from thoughtful_agents.models.participant import Participant
from thoughtful_agents.models.conversation import Conversation

from thoughtful_agents.utils.llm_api import get_completion

async def predict_turn_taking_type(conversation: 'Conversation') -> str:
    """Predict turn-taking type based on the last 5 utterances.
    
    This function provides a prediction of the turn-taking type based on the last 5 utterances.
    It returns either:
    1. A specific speaker's name (indicating turn-allocation to that speaker)
    2. "anyone" (indicating open floor/self-selection where any speaker could take the turn)
    
    Args:
        conversation: The conversation to predict the turn-taking type for
        
    Returns:
        Either a specific speaker's name or "anyone" indicating the turn-taking type
    """
    # Get the last 5 utterances
    last_events = conversation.get_last_n_events(5)
    last_5_utterances = ""
    for event in last_events:
        last_5_utterances += f"{event.participant_name}: {event.content}\n"
    
    # Get the participants
    participants = conversation.participants
    num_participants = len(participants)
    participant_list = ", ".join([p.name for p in participants])
    
    # Create the prompt
    system_prompt = f"This is a conversation between {num_participants} speakers. The speakers are: {participant_list}. Predict who the next speaker will be based on the last 5 utterances. Return ONLY the speaker name. If the next speaker is not clearly allocated to a specific speaker and any speaker could take the floor in the next turn, return \"anyone\"."
    user_prompt = f"<Task>Last 5 utterances:\n{last_5_utterances}\nPrediction: "
    
    # Call the OpenAI API
    try:
        response = await get_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7,  # Lower temperature for more deterministic results
            # model="ft:gpt-3.5-turbo-0125:personal::9Vu6HJKH", # Custom fine-tuned model for turn taking prediction
            model="gpt-4o-mini" # for public use
        )
        
        # Extract the turn allocation type from the response
        turn_allocation_type = response.get("text", "").strip()
        
        # Validate the prediction
        valid_speakers = [p.name for p in participants] + ["anyone"]
        if turn_allocation_type not in valid_speakers:
            # If the prediction is not valid, default to "anyone"
            return "anyone"
        
        # Update the last event with the predicted turn allocation
        if last_events:
            last_event = last_events[-1]
            last_event.pred_next_turn = turn_allocation_type
        
        return turn_allocation_type
        
    except Exception as e:
        # Log the error and default to "anyone"
        print(f"Error predicting turn taking: {str(e)}")
        return "anyone"



async def decide_next_speaker_and_utterance(conversation: 'Conversation') -> Tuple[Optional[Participant], str]:
    """Decide the next speaker and their utterance based on current conversation state.
    Get all selected thoughts from all participants, and then select the one with the highest intrinsic motivation score.
    
    Only Agent type participants are considered, as other participant types (like Human) don't have a thought_reservoir.
    The function ensures that the same participant doesn't speak twice in a row.
    """

    # Get the last speaker's ID from conversation history
    last_speaker_id = None
    method = conversation.method
    if conversation.event_history:
        last_speaker_id = conversation.event_history[-1].participant_id
    
    # print("🐞DEBUG: last_speaker_id", last_speaker_id)

    other_agents = [p for p in conversation.get_agents() if p.id != last_speaker_id]

    # print("🐞DEBUG: other_agents", other_agents)
    
    # Get all selected thoughts from Agent participants only
    selected_thoughts = []
    for agent in other_agents:
        selected_thoughts.extend(agent.thought_reservoir.get_selected_thoughts())

    # print("🐞DEBUG: selected_thoughts", selected_thoughts)

    if len(selected_thoughts) == 0:
        for agent in other_agents:
            selected_thoughts.extend(agent.thought_reservoir.retrieve_top_k(1, 0))
        # return None, None
    
    #if the selected thought includes moderator, then always select the moderator as the next speaker
    
    selected_thought = None
    #TODO change back
    # if method 'SocialAgent':
    for thought in selected_thoughts:
        participant = conversation.get_participant_by_id(thought.agent_id)
        if participant.name == "Moderator":
            selected_thought = thought
            break
    
    if selected_thought is None:
        # Select the thought with the highest intrinsic motivation score
        selected_thought = max(selected_thoughts, key=lambda x: x.intrinsic_motivation['score'])

    # print("🐞DEBUG: selected_thought", selected_thought)
    participant = conversation.get_participant_by_id(selected_thought.agent_id)
    # Articulate the thought
    
    from thoughtful_agents.utils.thinking_engine import articulate_thought, check_attitude
    utterance = await articulate_thought(selected_thought, conversation, participant, conversation.if_end)
    # attitude = await check_attitude(conversation, participant, utterance)
    
    # Return the next speaker and their utterance
    return participant, utterance

    
    
    