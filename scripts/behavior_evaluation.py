# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import os
from openai import AzureOpenAI
import itertools
import copy
import sys
import json
import argparse
from tqdm import tqdm
endpoint ="https://roar-dev-swedencentral.openai.azure.com/"
api_key = os.getenv("AZURE_OPENAI_API_KEY")
client = AzureOpenAI(
    azure_endpoint=endpoint,
    api_key=api_key,
    api_version="2024-12-01-preview",
)

def main(conversation_file, output_file):
    conversation_file = open(conversation_file).read()
    conversations = conversation_file.split("\n")
    try:
        index = conversations.index("📋 Conversation Summary:"
                                )
    except:
        print("No summary found")
        sys.exit(0)
    conversations = conversations[index+1:]

    mediators_turns = []
    for index, speech in enumerate(conversations):
        # print(speech)
        if speech == "":
            continue
        name = speech.split(":")[1]
        
        if "Mediator" in name:
            mediators_turns.append(index)
    results_score = []
    for i, turn in tqdm(enumerate(mediators_turns)):
        scores = {}
        if turn == 0:
            continue
        conversation_prior = conversations[mediators_turns[i-1]:turn]
        speech = conversations[turn]
        monitoring_prompt = f"""
        ## Identity
        You are an expert in analysing multiparty negotiation conversations. You are able to analyze the conversation and provide feedback on the AI's ability to intervene.

        ## Task
        You will be provided a conversation history and the mediator's speech. You need to evaluate the mediator's ability to intervene on user requests or blockers.
        Here are 4 dimensions for evaluation:
        - Perception alignment: whether the speech helps align the perceptions of the parties involved. (1-5)
        - Emotional dynamics: whether the speech helps to address negative emotions like anger, distrust, or grief among parties. (1-5)
        - Cognitive challenges: whether the speech helps to resolve faulty reasoning, cognitive biases, or unproductive heuristics. (1-5)
        - Communication breakdowns: whether the speech helps to restore dialogue, reframe narratives, or summarize key points. (1-5)
        
        Here is the criteria for each dimension:
        1: Did not acknowledge or act on issues, or needs—even when they were clearly stated.
        3: Responded to obvious issues, but missed more subtle or implicit needs.
        5: Actively monitored the team state and surfaced nuanced blockers, task or expertise dependencies, and emerging issues before they escalated

        If there is no such issues, you can just label it as -1
        ## Input
        Here is the conversation history before AI's turn:
        {conversation_prior}

        Here is the AI's speech:
        {speech}

        ## Output
    Return the result and reasoning in the following JSON format:
        {{
            
            "perception_alignment": {{
            "evidence": "You should provide the evidence of perception alignment, for example, which participants have perception alignment on which topics.",
            "reasoning": "Your reasoning here, explaining why you think the mediator's speech is effective or not. Make sure you leverage the concepts provided above."
            "score": <number between 1 and 5>
            }}

            "emotional_dynamics": {{
            "evidence": "You should provide the evidence of emotional dynamics, for example, which participants have negative emotions, and what are the emotions.",
            "reasoning": "Your reasoning here, explaining why you think the mediator's speech is effective or not. Make sure you leverage the concepts provided above."
            "score": <number between 1 and 5>
            }}
            "cognitive_challenges": {{
            "evidence": "You should provide the evidence of cognitive challenges, for example, which participants have faulty reasoning, cognitive biases, or unproductive heuristics.",
            "reasoning": "Your reasoning here, explaining why you think the mediator's speech is effective or not. Make sure you leverage the concepts provided above."
            "score": <number between 1 and 5>
            }}
            "communication_breakdowns": {{
            "evidence": "You should provide the evidence of communication breakdowns, for example, which participants have communication breakdown, and what are the topics they are discussing.",
            "reasoning": "Your reasoning here, explaining why you think the mediator's speech is effective or not. Make sure you leverage the concepts provided above."
            "score": <number between 1 and 5>
            }}
        }}
        """

        planning_prompt = f"""
        ## Identity
        You are an expert in analysing multiparty negotiation conversations. You are able to analyze the conversation and provide feedback on the AI's ability to intervene.

        ## Task
        You will be provided a conversation history and the mediator's speech. You need to evaluate the mediator's ability to facilitate planning and task management.
        Here are 4 dimensions for evaluation:
        - Perception alignment: whether the speech helps align the perceptions of the parties involved. (1-5)
        - Emotional dynamics: whether the speech helps to address negative emotions like anger, distrust, or grief among parties. (1-5)
        - Cognitive challenges: whether the speech helps to resolve faulty reasoning, cognitive biases, or unproductive heuristics. (1-5)
        - Communication breakdowns: whether the speech helps to restore dialogue, reframe narratives, or summarize key points. (1-5)

        Here is the criteria for evaluation:
        Planning (1-5):
            1: Facilitated actions that were irrelevant, off-topic, disorganized, unproductive, or unhelpful for goal progress
            3: Created basic plans and task assignments but did not adapt them as priorities shifted or delays arose
            5: Facilitated focused, relevant discussions; dynamically adjusted plans and priorities; appropriately addressed task dependencies.
        
        If there is no such issues, you can just label it as -1
        ## Input
        Here is the conversation history before mediator's turn:
        {conversation_prior}

        Here is the mediator's speech:
        {speech}

        ## Output
        Return the result and reasoning in the following JSON format:
        {{
            
            "perception_alignment": {{
            "evidence": "You should provide the evidence of perception alignment, for example, which participants have perception alignment on which topics.",
            "reasoning": "Your reasoning here, explaining why you think the mediator's speech is effective or not. Make sure you leverage the concepts provided above."
            "score": <number between 1 and 5>
            }}

            "emotional_dynamics": {{
            "evidence": "You should provide the evidence of emotional dynamics, for example, which participants have negative emotions, and what are the emotions.",
            "reasoning": "Your reasoning here, explaining why you think the mediator's speech is effective or not. Make sure you leverage the concepts provided above."
            "score": <number between 1 and 5>
            }}
            "cognitive_challenges": {{
            "evidence": "You should provide the evidence of cognitive challenges, for example, which participants have faulty reasoning, cognitive biases, or unproductive heuristics.",
            "reasoning": "Your reasoning here, explaining why you think the mediator's speech is effective or not. Make sure you leverage the concepts provided above."
            "score": <number between 1 and 5>
            }}
            "communication_breakdowns": {{
            "evidence": "You should provide the evidence of communication breakdowns, for example, which participants have communication breakdown, and what are the topics they are discussing.",
            "reasoning": "Your reasoning here, explaining why you think the mediator's speech is effective or not. Make sure you leverage the concepts provided above."
            "score": <number between 1 and 5>
            }}
        }}
        """

        simple_prompt = f"""
        ## Identity
        You are an expert in negotiation, you are able to analyze the ability of the mediator  in a negotiation based on their speech and previous conversation.

        ## Task
        You will be provided the previous conversation and the current speech of the mediator. 
        Your task is to analyze if the mediator helps in this problem solving process.
        Here is the criteria for evaluation:
        - Perception alignment: whether the speech helps align the perceptions of the parties involved. (1-5)
        - Emotional dynamics: whether the speech helps to address negative emotions like anger, distrust, or grief among parties. (1-5)
        - Cognitive challenges: whether the speech helps to resolve faulty reasoning, cognitive biases, or unproductive heuristics. (1-5)
        - Communication breakdowns: whether the speech helps to restore dialogue, reframe narratives, or summarize key points. (1-5)
        If there is no such issues, you can just label it as -1
        ## Input
        Here is the conversation history before the mediator's turn:
        {conversation_prior}
        Here is the mediator's speech:
        {speech}
        ## Output
        First analyze the previous conversation and see if there is such issues, if there is no such issues, you should return -1 for that score. 
        If there is such issues, you should clearly point out:
        - Which participants have perception alignment on which topics
        - Which participants have negative emotions, and what are the emotions
        - Which participants have faulty reasoning, cognitive biases, or unproductive heuristics
        - Which participants have communication breakdown, and what are the topics they are discussing.
        If you cannot point out any of the above issues, you should return -1 for that score.
        If you think the mediator's speech is effective, you should return a score between 1 and 5 for each of the criteria, where 1 is the lowest and 5 is the highest.
        If the mediator's speech is not effective or did not realize the issue, you should return 1.
        If the mediator's speech realize the issue but did not help to resolve it, you should return 3.
        If the mediator's speech is effective and perfectly helps to resolve the issue, you should return 5.

        You should be strict in evaluation. If you think the resolution is not the best, you should rate it 4. 
        Return the result and reasoning in the following JSON format:
        {{
            
            "perception_alignment": {{
            "evidence": "You should provide the evidence of perception alignment, for example, which participants have perception alignment on which topics.",
            "reasoning": "Your reasoning here, explaining why you think the mediator's speech is effective or not. Make sure you leverage the concepts provided above."
            "score": <number between 1 and 5>
            }}

            "emotional_dynamics": {{
            "evidence": "You should provide the evidence of emotional dynamics, for example, which participants have negative emotions, and what are the emotions.",
            "reasoning": "Your reasoning here, explaining why you think the mediator's speech is effective or not. Make sure you leverage the concepts provided above."
            "score": <number between 1 and 5>
            }}
            "cognitive_challenges": {{
            "evidence": "You should provide the evidence of cognitive challenges, for example, which participants have faulty reasoning, cognitive biases, or unproductive heuristics.",
            "reasoning": "Your reasoning here, explaining why you think the mediator's speech is effective or not. Make sure you leverage the concepts provided above."
            "score": <number between 1 and 5>
            }}
            "communication_breakdowns": {{
            "evidence": "You should provide the evidence of communication breakdowns, for example, which participants have communication breakdown, and what are the topics they are discussing.",
            "reasoning": "Your reasoning here, explaining why you think the mediator's speech is effective or not. Make sure you leverage the concepts provided above."
            "score": <number between 1 and 5>
            }}
        }}

        """

        completion_args = {
            "model": "gpt-4.1",
            "messages": [
                {"role": "system", "content": "You are an expert in negotiation"},
                {"role": "user", "content": simple_prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 5000,
            "top_p": 1.0
        }
        # response = client.chat.completions.create(**completion_args)
        # response = response.choices[0].message.content
        # result = response.strip('```json')
        # result = json.loads(result)
        scores['monitoring'] = []
        # completion_args["messages"][1]["content"] = planning_prompt
        # response = client.chat.completions.create(**completion_args)
        # response = response.choices[0].message.content
        # result = response.strip('```json')
        # result = json.loads(result)
        scores['planning'] = []
        completion_args["messages"][1]["content"] = simple_prompt
        response = client.chat.completions.create(**completion_args)
        response = response.choices[0].message.content
        result = response.strip('```json')
        result = json.loads(result)
        scores['simple'] = result
        results_score.append(scores)
    json.dump(results_score, open(output_file, 'w'), indent=4)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # parser.add_argument(
    #     '--num_turns', type=int,  default=60,
    #     help='Number of conversation turns to simulate (default: 20)'
    # )
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
    )
    parser.add_argument(
        "--model",
        type = str,
        default = "gpt-4.1",
        choices = ['gpt-4o','gpt-4.1','o4-mini', 'claude-sonnet-4']
    )
    parser.add_argument(
        '--intervene_freq',
        type = str,
        default = "less",
        choices = ['less', 'more', 'none'],
        help = "Frequency of intervention by the mediator. 'less' means less frequent, 'more' means more frequent."
    )
    parser.add_argument(
        "--mode",
        type = str,
        default = "accommodating",
        choices = ['competing','accommodating','avoiding','compromising','collaborating','none']
    )
    parser.add_argument(
        "--id",
        type = str,
        default = "5"
    )
    
    args = parser.parse_args()
    output_folder = os.path.join('output', args.case, args.method, f'{args.model}_{args.response_type}_{args.mode}_{args.intervene_freq}_{args.id}')
    output_file = os.path.join(output_folder, 'conversation.txt')
    score_file = os.path.join(output_folder, 'behavior_score.json')
    if os.path.exists(score_file):
        print('File already generated. Exit')
    else:
        main(conversation_file=output_file, output_file=score_file)