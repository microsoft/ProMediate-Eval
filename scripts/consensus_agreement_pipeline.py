# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import json
import argparse
from tqdm import tqdm
# from thoughtful_agents.utils.prompts import instruction_prompt
import os
from openai import AzureOpenAI
import itertools
import copy
import sys
endpoint ="https://roar-dev-swedencentral.openai.azure.com/"
api_key = os.getenv("AZURE_OPENAI_API_KEY")
client = AzureOpenAI(
    azure_endpoint=endpoint,
    api_key=api_key,
    api_version="2024-12-01-preview",
)
# topics = [
#     "Market Share Target Tiers",
#     "Discount Pricing Schedule",
#     "Marketing Support",
#     "Formulary Status",
#     "Contract Term"
# ]
def check_attitude(speech, conversation, instruction_prompt, topics, if_initial=False):
    """
    Check the attitude of the speaker towards each topic in the speech.
    
    Args:
        speech (str): The speech to analyze.
        conversation (str): The previous conversation context.
        instruction_prompt (str): The background context for the negotiation.
    
    Returns:
        dict: A dictionary containing the speaker's name and their attitude towards each topic.

    """
    if if_initial:
        check_attitude_prompt = f"""
    ## Identity
    You are an expert in negotiation, you are able to analyze the attitude towards each topic in a negotiation based on their speech and previous conversation.

    ## Task
    Your will be provided a list of opinions, you need to check the attitude of the speaker towards each topic.
    Make use of the previous conversation to understand the context and the speaker's position. For example, if the speaker has previously expressed a preference for a certain topic, you should take that into account when determining their attitude in the current speech.
    If the speaker say "Totally agree", you should check on previous conversation to see what's the previous topic they are referring to, and then return the attitude for that topic.
    If the speak does not mention a topic, you should return "No Mention" for that topic.
    If the speaker use option (a),(b), etc, you should check what are the options and transfer them in an easy form. 
    Only output the attitude of the speaker if they explicitly mention the topic in their speech and have a clear preference. Do not make assumptions about the speaker's attitude if they do not mention the topic or making a clear statement about it.

    ## Input
    Here is the opinion:
    {speech}

    Here are the topics you need to check the attitude for:
    {json.dumps(topics)}

    ## Output
    Return the attitude in the following JSON format:
    {{
        "speaker_name": "Speaker Name",
        "attitude": {{
            "[topic name]": "short description",
            .....
        }}
    }}
"""
    else:
        check_attitude_prompt = f"""
        ## Identity
        You are an expert in negotiation, you are able to analyze the attitude of a speaker towards each topic in a negotiation based on their speech and previous conversation.

        ## Background
        Here is a background context for the negotiation:
        {instruction_prompt}

        ## Task
        Your will be provided a speech and previous conversation from a negotiation, you need to check the attitude of the speaker towards each topic.
        Make use of the previous conversation to understand the context and the speaker's position. For example, if the speaker has previously expressed a preference for a certain topic, you should take that into account when determining their attitude in the current speech.
        If the speaker say "Totally agree", you should check on previous conversation to see what's the previous topic they are referring to, and then return the attitude for that topic.
        If the speak does not mention a topic, you should return "No Mention" for that topic.
        Only output the attitude of the speaker if they explicitly mention the topic in their speech and have a clear preference. Do not make assumptions about the speaker's attitude if they do not mention the topic or making a clear statement about it.

        ## Input
        Here is the previous turns of conversation, it might be empty if this is the first turn of the negotiation:
        {conversation}

        Here is the speech:
        {speech}

        Here are the topics you need to check the attitude for:
        {json.dumps(topics)}

        ## Output
        Return the attitude in the following JSON format:
        {{
            "speaker_name": "Speaker Name",
            "attitude": {{
                "[topic name]": "short description",
                .....
            }}
        }}

        """

    check_attitude_prompt = f"""
    ## Identity
    You are an expert in negotiation, you are able to analyze the attitude of a speaker towards each topic in a negotiation based on the opinions provided and previous conversation.

    ## Task
    Your will be provided a list of opinions, you need to check the attitude of the speaker towards each topic.
    Make use of the previous conversation to understand the context and the speaker's position. For example, if the speaker has previously expressed a preference for a certain topic, you should take that into account when determining their attitude in the current speech.
    If the speaker say "Totally agree", you should check on previous conversation to see what's the previous topic they are referring to, and then return the attitude for that topic.
    If the speak does not mention a topic, you should return "No Mention" for that topic.
    If the speaker use option (a),(b), etc, you should check what are the options and transfer them in an easy form. 
    Only output the attitude of the speaker if they explicitly mention the topic in their speech and have a clear preference. Do not make assumptions about the speaker's attitude if they do not mention the topic or making a clear statement about it.

    ## Input
    {speech}

    Here are the topics you need to check the attitude for:
    {json.dumps(topics)}

    ## Output
    Return the attitude in the following JSON format:
    {{
 
        "attitude": {{
            "[topic name]": "short description",
            .....
        }}
    }}

    """
    
    completion_args = {
        "model": "gpt-4.1",
        "messages": [
            {"role": "system", "content": "You are an expert in negotiation"},
            {"role": "user", "content": check_attitude_prompt}
        ],
        "temperature": 0.8,
        "max_tokens": 5000,
        "top_p": 1.0
    }
    
    response = client.chat.completions.create(**completion_args)
    try:
        result = response.choices[0].message.content
        result = result.strip("```json")
        result = json.loads(result)
    except json.JSONDecodeError:
        result = {
            "speaker_name": "Unknown",
            "attitude": {
                
            }
        }
    return result

def calculate_consensus_score(speaker_1_state, speaker_2_state, speaker_1, speaker_2, current_topic, instruction_prompt):
    # if speaker_1_state == "No Mention" or speaker_2_state == "No Mention":
    #     return 0.0, ''
    
    prompt = f"""
    ## Identity
    You are an expert in negotiation, you are able to analyze the mental states of two participants in a negotiation and calculate the consensus score between them for each topic.

    ## Background
    Here is the background context:
    {instruction_prompt}

    Here is the current topic:
    {current_topic}

    ## Task
    You will be provided a background context for a negotation and current mental states from two participants. Your task is to calculate the consensus score between the two participants for each topic.

    You need to calculate the consensus score between the two participants for each topic. The consensus score is
    calculated based on the mental states of the two participants. The score is between 0 and 1, where 0 means no consensus and 1 means full consensus. 

    Shared Goals: Do both parties express alignment on the overall objective?
    Common understanding: Is there a shared understanding of the problem and its context?
    Agreement on Terms: Are the proposed terms (e.g., timelines, deliverables, responsibilities) mutually accepted or negotiated to a common ground?
    Tone and Willingness: Is there evidence of cooperative tone, openness to compromise, or mutual respect?
    Shared decision making: Do both parties share the similar decision making process, or do they have different decision making process?
    You should first rate for each topic, then return the overall consensus score.
    If one of the mental state is empty, just score everything as 0

    ## Input
    Here is {speaker_1}'s mental state:
    {json.dumps(speaker_1_state)}
    Here is {speaker_2}'s mental state:
    {json.dumps(speaker_2_state)}

    ## Output
    Follow this JSON format, only output float scores for each topic, and a short reasoning for each score, do not output any comment follow the score. Make sure the output can be parsed into JSON format.:
    {{  "reasoning: "short reasoning for the each score",
        'shared_goals': float,
        'common_understanding': float,
        'agreement_on_terms': float,
        'tone_and_willingness': float,
        'shared_decision_making': float,
        'overall_consensus_score': float
    }}
    """
    completion_args = {
        "model": "gpt-4.1",
        "messages": [
            {"role": "system", "content": "You are an expert in negotiation"},
            {"role": "user", "content": prompt }
        ],
        "temperature": 0.5,
        "max_tokens": 1000,
        "top_p": 1.0
    }

    response = client.chat.completions.create(**completion_args)
                
    result = response.choices[0].message.content
    try:
        result = json.loads(result)
    except:
        print(result)
        result = {
            'reasoning': 'Error in parsing the response',
            'overall_consensus_score': 0.0,}

    return result

def load_index_dict(config_file):
    """
    Load the index dictionary for the given names.
    
    Args:
        names (list): List of names to create the index dictionary.
    
    Returns:
        dict: A dictionary mapping each pair of names to their index.
    """
    index_dict = {}
    names = list(config_file.keys())
    names.remove("Mediator")
    count = 0
    for i, name1 in enumerate(names):
        for j, name2 in enumerate(names[i+1:]):
            if name1 != name2:
                index_dict[f"{name1}_{name2}"] = count
                index_dict[f"{name2}_{name1}"] = count # Add reverse pairs
                count += 1
    # Add reverse pairs
    
    return index_dict

def load_initial_opinions( case_info):
    initial_opinions = {}

    for name in case_info['names']:
        if name == "Mediator":
            continue
        else:
            # f = open(os.path.join('thoughtful_agents', 'prompts', f'{case}/names', f'{name}.md'), 'r')
            # prompt_name = f.read()
            prompt_name = case_info['names'][name]
            opinions = prompt_name.split("##")[-2].strip()
            initial_opinions[name] = opinions
    return initial_opinions

def main(conversations, case):
    
    # config_file = os.path.join('cases', f'{case}_negotiation.json')
    # with open(config_file, 'r') as f:
    #     config = json.load(f)
    
    # initial_opinions = load_initial_opinions(config, case)
    # f = open(os.path.join('thoughtful_agents', 'prompts', f'{case}/instruction.md'), 'r')
    # # load topics
    # f = open(os.path.join('thoughtful_agents', 'prompts', "topics.json"), 'r')
    f = open(os.path.join('cases',f'{case}.json'), 'r')
    all_prompts = json.load(f)
    topics = all_prompts['topics']
    initial_opinions = load_initial_opinions(all_prompts)
    instruction_prompt = all_prompts['instruction']
    config = all_prompts['config']
    index_dict = load_index_dict(config)
    # Initialize scores
    print("Initializing scores...")
    all_attitudes_track = []
    all_scores = []
    names = list(initial_opinions.keys())
    combinations = list(itertools.combinations(names, 2))
    initial_attitudes = {}
    for name in initial_opinions:
        attitude = check_attitude(initial_opinions[name], "", instruction_prompt, topics, if_initial=True)
        initial_attitudes[name] = attitude['attitude']
    all_attitudes_track.append(initial_attitudes)
    initial_score = {}
    
    for topic in topics:
        initial_score[topic] = []
        for combination in combinations:
        
            scores = calculate_consensus_score(
                all_attitudes_track[-1][combination[0]][topic],
                all_attitudes_track[-1][combination[1]][topic],
                combination[0], combination[1], topic,
                instruction_prompt
                )
            initial_score[topic].append(scores)
    all_scores.append(initial_score)
    
    for i, conversation in tqdm(enumerate(conversations)):
        conversation = conversation.strip()
        if not conversation:
            continue
        
        # Extract speaker name and speech from the conversation
        try:

            _, speaker_name, speech = conversation.split(": ", 2)
        except ValueError:
            print(f"Skipping malformed conversation: {conversation}")
            continue
        if "Mediator" in speaker_name:
            attitudes_copy = copy.deepcopy(all_attitudes_track[-1])
            scores_copy = copy.deepcopy(all_scores[-1])
            all_attitudes_track.append(attitudes_copy)
            all_scores.append(scores_copy)
            continue
        # Check the attitude of the speaker towards each topic
        attitude = check_attitude(':'.join([speaker_name,speech]), "\n".join(conversations[:i]), instruction_prompt, topics)

        # Update the attitudes track
        attitudes_copy = copy.deepcopy(all_attitudes_track[-1])
        scores_copy = copy.deepcopy(all_scores[-1])
        for topic in topics:
            if attitude['attitude'][topic].lower().strip().strip('.') not in ["no mention", "no explicit mention in this speech", "no explicit mention"]:
                attitudes_copy[speaker_name][topic] = attitude['attitude'][topic]
                rest_names = [name for name in names if name != speaker_name]
                for rest_name in rest_names:
                    scores = calculate_consensus_score(
                        attitudes_copy[speaker_name][topic],
                        attitudes_copy[rest_name][topic],
                        speaker_name, rest_name, topic,
                        instruction_prompt
                    )
                    scores_copy[topic][index_dict[f"{speaker_name}_{rest_name}"]] = scores

        all_attitudes_track.append(attitudes_copy)
        all_scores.append(scores_copy)
    return all_attitudes_track, all_scores
        


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a consensus agreement pipeline.")
 
  
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
    )
    parser.add_argument(
        "--model",
        type = str,
        default = "gpt-4.1",
        choices = ['gpt-4o','gpt-4.1','o4-mini',
                   'claude-sonnet-4']
    )
    parser.add_argument(
        "--mode",
        type = str,
        default = "accommodating",
        choices = ['competing','accommodating','avoiding','compromising','collaborating','none']
    )
    parser.add_argument(
        '--intervene_freq',
        type = str,
        default = "less",
        choices = ['less', 'more', 'none'],
        help = "Frequency of intervention by the mediator. 'less' means less frequent, 'more' means more frequent."
    )
    
    parser.add_argument(
        "--id",
        type = str,
        default = "5"
    )
    args = parser.parse_args()
    output_folder = os.path.join('output', args.case, args.method, f'{args.model}_{args.response_type}_{args.mode}_{args.intervene_freq}_{args.id}')
    os.makedirs(output_folder, exist_ok=True)
    input_file_name = os.path.join(output_folder, 'conversation.txt')
    try: 
           
        f = open(input_file_name, 'r')
        lines = f.readlines()
        f.close()
    except:
        print(f"Error: File {input_file_name} not found.")
        sys.exit(1)
    try:
        index_start = lines.index("📋 Conversation Summary:\n") + 1
    except:
        print("Error: '📋 Conversation Summary:' not found in the file.")
        sys.exit(1)
    attitudes_file = os.path.join(output_folder, 'attitudes.json')
    if os.path.exists(attitudes_file):
        print(f"File {attitudes_file} already exists. Exiting to avoid overwriting.")
        sys.exit(1)
    conversations = lines[index_start:]
    attitudes_track, scores = main(conversations, args.case)
    json.dump(attitudes_track, open(os.path.join(output_folder, 'attitudes.json'), 'w'), indent=4)
    json.dump(scores, open(os.path.join(output_folder, 'agreement_scores.json'), 'w'), indent=4)

