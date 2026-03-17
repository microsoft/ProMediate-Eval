# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.



import asyncio
import sys
import os
from typing import Optional
from thoughtful_agents.utils.prompts import *
from thoughtful_agents.models import (
    Human, 
    Conversation,
    Mediator,
    NaiveMediator,
    GenericMediator,
    InnerThoughtMediator,
    SocialMediator
)
import json
import argparse
import random
from thoughtful_agents.utils.turn_taking_engine import decide_next_speaker_and_utterance, predict_turn_taking_type
from thoughtful_agents.utils.llm_api import DEFAULT_EMBEDDING_MODEL
from tqdm import tqdm
sys.stderr = open("error_output.txt","w")
classes = {
    'Naive': NaiveMediator,
    'Social': SocialMediator,
    'Baseline1': InnerThoughtMediator,
    'Baseline2': GenericMediator
}
model_deployment = {
    "gpt-4o":"gpt-4o-0806",
    "gpt-4o-mini":"gpt-4o-mini",
    "gpt-4.1":"gpt-4.1",
    "o4-mini":"o4-mini",
    "claude-sonnet-4":"claude-sonnet-4-20250514"
}

def load_prompts(case_info: dict) -> dict:
    """
    Load prompts for the specified case.
    
    Args:
        case_info (dict): The case information.
    
    Returns:
        dict: A dictionary containing the prompts for the specified case.
    """
    case_prompt = {}
    prompt_instruction = case_info['instruction']
    prompt_issues = case_info['issues']
    prompt_options = case_info['options']
    # case_info['names']['Mediator'] 
    mediator_prompt = case_info['names'].get('Mediator', '').format(issues=prompt_issues)

    prompt_instruction = prompt_instruction.format(
        issues=prompt_issues,
        options=prompt_options
    )
    case_prompt['instruction_prompt'] = prompt_instruction
    case_prompt['main_topic'] = prompt_issues
    case_prompt['names'] = case_info['names']
    case_prompt['names']['Mediator'] = mediator_prompt

    return case_prompt

def printing(text,outputFile):
    print(text)
    if outputFile:
        outputFile.write(str(text))
async def run_conversation(case, outfile_name, mode, response_type, method, model, intervene_freq, verbose: bool = True):
   
    # Load configuration from the specified JSON file
    case_info = json.load(open(os.path.join('cases', f'{case}.json'),'r'))
    config = case_info['config']
  
    # Create a conversation with a simple context
    prompts = load_prompts(case_info)
    outfile = open(outfile_name,'w')

    issues = case_info['topics']
    conversation = Conversation(context=prompts['instruction_prompt'], main_topic=prompts['main_topic'], mode=mode, method=method, issues = issues)
    participants = {}
    for name in config:
        if name == "Mediator" and method != "NoAgent":
            mediator = classes[method]
            participants[name] = mediator(name=name, proactivity_config=config[name], model = model_deployment[model], response_type=response_type, intervene_freq=intervene_freq)
        else:
            participants[name] = Human(name=name, proactivity_config=config[name], model = "claude-sonnet-4-20250514")
    num_turns = 4*(len(participants)-1)*len(issues[case])
     # Default number of turns is 4 times the number of participants times the numbers of issues
    # Initialize long-term memories for each agent 
    # Add memories to the agents (splitting by paragraphs)
    for name in prompts['names']:
        participants[name].initialize_memory(prompts['names'][name]+mode_prompt[mode], by_paragraphs=True)
    if method == "NoAgent":
        participants.pop('Mediator')
    # Add agents to the conversation
    for name in participants:
        conversation.add_participant(participants[name])
    
    printing("\n==== 🚀 Starting Multi-Party Conversation 🚀 ====\n",outfile)
 
    start_message = "Welcome everyone! Let's discuss!"
    if method == "NoAgent":
        names = list(participants.keys())
        random_participant = random.choice(names) 
        new_event = await participants[random_participant].send_message(start_message, conversation)
        printing(f"👤 {random_participant}: {start_message}\n",outfile)
    
    else:
        new_event = await participants['Mediator'].send_message(start_message, conversation)
        printing(f"👤 Mediator: {start_message}\n",outfile)
    
    # Predict the next speaker before broadcasting the event
    turn_allocation_type = await predict_turn_taking_type(conversation)
    # Use the turn-taking engine to predict who should speak next (this is just a prediction)
    if verbose:
        printing(f"🎯 Turn-taking engine predicts that the turn is allocated to {turn_allocation_type}\n",outfile) 
    
    # Broadcast the event to let all agents think
    await conversation.broadcast_event(new_event)
    
    # Run the conversation for the specified number of turns
    for turn in tqdm(range(num_turns)):
        printing(f"\n---- Turn {turn + 1} ----",outfile)
        
        # Mediator always think first, then others
        if method != 'NoAgent':

            utterance = participants['Mediator'].next_utterance
            printing(f"🧠 Mediator's thoughts:\n", outfile)
            for thought in participants['Mediator'].thought_reservoir.thoughts:
                if thought.generated_turn == conversation.turn_number:
                    printing(f"  💭 {thought.content} (Intrinsic Motivation: {thought.intrinsic_motivation['score']})\n (Reasoning:{thought.intrinsic_motivation['reasoning']})\n", outfile)
            ## TODO change for generic mediator later
            if utterance:
                new_event = await participants['Mediator'].send_message(participants['Mediator'].next_utterance, conversation)
              
                printing(f"👤 Mediator: {utterance}\n",outfile)
                turn_allocation_type = await predict_turn_taking_type(conversation)
                if verbose:
                    printing(f"🎯 Turn-taking engine predicts that the turn is allocated to {turn_allocation_type}\n",outfile)
                
                # Broadcast the event to let all agents think
                await conversation.broadcast_event(new_event)
                continue

        # Show each agent's thoughts and their intrinsic motivation scores if verbose
        if verbose:
            for participant in conversation.get_agents():
                printing(f"🧠 {participant.name}'s thoughts:\n", outfile)
                for thought in participant.thought_reservoir.thoughts:
                    if thought.generated_turn == conversation.turn_number:
                        printing(f"  💭 {thought.content} (Intrinsic Motivation: {thought.intrinsic_motivation['score']})\n (Reasoning:{thought.intrinsic_motivation['reasoning']})\n", outfile)
                
        # Determine the actual next speaker based on intrinsic motivation

        next_speaker, utterance = await decide_next_speaker_and_utterance(conversation)
        # attitudes.append({"name":next_speaker.name, "attitude": attitude})
        if next_speaker:
            # Send the message
            new_event = await next_speaker.send_message(utterance, conversation)
            printing(f"👤 {next_speaker.name}: {utterance}\n",outfile)
            # printing(f"👤 {attitudes}\n",outfile)
            
            # After each turn, check for consensus
            conversation.consensus_upgrade()
            printing(f"The consensus check for previous conversation: {conversation.consensus_check_flow[-1]}\n", outfile)
            # Predict the next speaker before broadcasting the event
            turn_allocation_type = await predict_turn_taking_type(conversation)
            if verbose:
                printing(f"🎯 Turn-taking engine predicts that the turn is allocated to {turn_allocation_type}\n",outfile)
            
            # Broadcast the event to let all agents think
            await conversation.broadcast_event(new_event)
        else:
            printing("❌ No agent has thoughts to articulate.",outfile)
            break
        # if conversation.if_end:
        #     break
    
    printing("\n==== 🏁 End of Conversation 🏁 ====\n",outfile)
    
    # Summary
    printing("📋 Conversation Summary:\n",outfile)
    for i, event in enumerate(conversation.event_history):
        participant_name = event.participant_name
        content = event.content
        printing(f"🔄 Turn {i+1}: {participant_name}: \"{content}\"\n",outfile)
    
    consensus_flow = conversation.consensus_check_flow
    file_name = outfile_name.replace('txt','json')
    f = open(file_name,'w')
    json.dump(consensus_flow,f,indent=2)
   

async def main():
    
    parser = argparse.ArgumentParser(description="Run a multiparty conversation simulation.")
  
    parser.add_argument(
        '--verbose', type=str, nargs='?', default='True',
        help='Whether to print detailed thought processes and turn-taking predictions (default: True)'
    )   
    parser.add_argument(
        '--case', type=str, default='hmo',
        help='scenario'
    )
    parser.add_argument(
        '--method',
        type=str,
        default = "Social",
        choices=['Naive','Baseline1','Baseline2','NoAgent','Social'],
        help = "Baseline1 is inner thought, baseline 2 is generic prompt"
    )
    parser.add_argument(
        '--response_type',
        type=str,
        default = "separate",
        choices = ['separate', 'combined'],
        help = "separate means 'when' and 'how' are predicted separately, combined means 'when' and 'how' are predicted together(Inner thought)"
    ) # could be deprecated later, the default is separate

    parser.add_argument(
        '--intervene_freq',
        type = str,
        default = "less",
        choices = ['less', 'more', 'none'],
        help = "Frequency of intervention by the mediator. 'less' means less frequent, 'more' means more frequent."
    )
    # By default, no agent setting is 'None'  and baseline 2 (generic) is "more", only social mediator could have two options. 

    parser.add_argument(
        "--model",
        type = str,
        default = "gpt-4.1",
        choices = ['gpt-4o','gpt-4.1','o4-mini','claude-sonnet-4','gpt-4o-mini']
    )
    parser.add_argument(
        "--mode",
        type = str,
        default = "accommodating",
        choices = ['competing','accommodating','avoiding','compromising','collaborating', 'none']
    )
    parser.add_argument(
        "--id",
        type = str,
        default = "5"
    )
    
    args = parser.parse_args()
    output_folder = os.path.join('output', args.case, args.method, f'{args.model}_{args.response_type}_{args.mode}_{args.intervene_freq}_{args.id}')
    output_file = os.path.join(output_folder, 'conversation.txt')
    # Create output directory if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    ## check if it exists
    if os.path.exists(output_file):
        f = open(output_file, 'r')
        content = f.read()
        conversation = content.split('\n')
        try:
            index = conversation.index("📋 Conversation Summary:")
            if len(conversation[index:]) < 40:
                print(f"Output file {output_file} is incomplete. Regenerate it.")
            else:
                print(f"Output file {output_file} already exists. Please choose a different name or delete the existing file.")
                return       
        except:
            print("The output file is not a valid conversation output file. Regenerate it.")
        
       
       
    else:
        print("New experiment, output file will be created.")

    
    verbose = True  # Default verbose setting
    
    await run_conversation(args.case, output_file, args.mode, args.response_type, args.method, args.model, args.intervene_freq,  verbose)

if __name__ == "__main__":
    
    asyncio.run(main()) 