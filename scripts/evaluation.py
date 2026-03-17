# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.



## overall consensus change between first 10 turns and last 10 turns
from thoughtful_agents.utils.llm_api import get_completion_sync
from tqdm import tqdm
import argparse
import json
import os
from statistics import mean
import pandas as pd
from sklearn.linear_model import LinearRegression
import numpy as np
from openai import OpenAI

api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(
    api_key=api_key,
    api_version="2024-12-01-preview",
)
def evaluate_consensus_change(scores, num_turns=10):
    if len(scores) < num_turns:
        return None

    first_10_average = sum(scores[:num_turns]) / num_turns
    last_10_average = sum(scores[-num_turns:]) / num_turns

    return last_10_average - first_10_average

def evaluate_frequency(conversations):
    count = 0
    for conversation in conversations:
        _, speaker_name, speech = conversation.split(": ", 2)
        if "Mediator" in speaker_name:
            count += 1

    return (count-1) / len(conversations) if conversations else 0

def evaluate_topic_level_efficiency(conversations, scores, topic):
    nums = 0
    scores_selected = []
    for conversation in tqdm(conversations):

        prompt = f"""
        You are a mediator in a negotiation about {topic}. You need to check if the current speech mentions this topic.
        Only reply with "True" if the topic is mentioned, otherwise reply with "False".
        Current speech: {conversation}

        Your answer should be a boolean value.
        """
       
        completion_args = {
                "model": 'gpt-4.1',
                "messages": [
                    {"role": "system", "content": ""},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 10,
                "top_p": 1.0
            }
        response = client.chat.completions.create(**completion_args)
        result = response.choices[0].message.content
        if result == "True":
            nums += 1
            scores_selected.append(scores[topic][conversations.index(conversation)+1])
    
    turns = nums//5
    first_average = sum(scores_selected[:turns]) / turns if turns > 0 else 0
    last_average = sum(scores_selected[-turns:]) / turns if turns > 0 else 0
    return (last_average-first_average) / nums if nums > 0 else 0

def process_scores(scores):
    topics = list(scores[0].keys())
    scores_aggregated = {}
    scores_aggregated["overall"] = []
    for topic in topics:
        scores_aggregated[topic] = []
    for score in scores:
        one_turn_overall = []
        for topic in topics:
            topic_scores = score[topic]
            topic_aggregated = sum(item['overall_consensus_score'] for item in topic_scores if item['overall_consensus_score']) / len(topic_scores) if topic_scores else 0
            scores_aggregated[topic].append(topic_aggregated)
            one_turn_overall.append(topic_aggregated)
        scores_aggregated["overall"].append(sum(one_turn_overall) / len(one_turn_overall) if one_turn_overall else 0)
    return scores_aggregated

def get_slope(scores):

    x = list(i for i in range(len(scores)))
    X = np.array(x).reshape(-1, 1)
    y = np.array(scores)

    # Create and fit the linear regression model
    model = LinearRegression()
    model.fit(X, y)

    
    a = model.coef_[0]
    # b = model.intercept_

    return a


def calculate_mediator_effect(scores, conversations):
    mediator_turns = []
    for i, conversation in enumerate(conversations):
        if conversation.strip() == "":
            break

        if "Mediator" in conversation.split(':')[1]:
            mediator_turns.append(i+1) #align with the scores, scores including the intial scores
    assert len(conversations)+1 == len(scores['overall'])

    ## get the difference before and after each mediator's step in 
    for topic in scores:
        topic_scores = scores[topic]
        slope_differences = []
        slopes = []
        for index, turn in enumerate(mediator_turns):
            if turn == 1:
                continue
            # Calculate the slope of the scores before and after the mediator's turn
            part_scores = topic_scores[mediator_turns[index-1]:turn]
            slopes.append(get_slope(part_scores))
        part_scores_last = topic_scores[mediator_turns[-1]:]
        slopes.append(get_slope(part_scores_last))
        for index, slope in enumerate(slopes):
            if index == 0:
                continue
            slope_differences.append(slope - slopes[index-1])
        
        average_slope_difference = sum(slope_differences) / len(slope_differences) if slope_differences else 0
        print(f"Average slope difference for topic '{topic}': {average_slope_difference}")

def evaluate_success_rate(scores):
    # if the average of consensus score in the last 10 turns is greater than 0.9, we consider it a success
    # it is for each topic
    total_success = 0
    total_topics = 0
    for topic in scores:
        if topic == "overall":
            continue
        topic_scores = scores[topic]
        if len(topic_scores) < 10:
            continue
        last_10_average = sum(topic_scores[-10:]) / 10
        # print(f"Last 10 average for topic '{topic}': {last_10_average}")
        if last_10_average < 0.9:
            total_topics += 1
            total_success += 0
        else:
            total_topics += 1
            total_success += 1
    return total_success / total_topics if total_topics > 0 else 0

def evaluate_success_rate_max(scores):
    # if the max of consensus score in the last 10 turns is greater than 0.9, we consider it a success
    # it is for each topic
    total_success = 0
    total_topics = 0
    for topic in scores:
        if topic == "overall":
            continue
        topic_scores = scores[topic]
        if len(topic_scores) < 10:
            continue
        last_10_max = max(topic_scores[-10:])
        # print(f"Last 10 average for topic '{topic}': {last_10_average}")
        if last_10_max < 0.9:
            total_topics += 1
            total_success += 0
        else:
            total_topics += 1
            total_success += 1
    return total_success / total_topics if total_topics > 0 else 0
def intervene_yield(aggregated_scores, mediator_turns, conversations, scenario):
    # for each mediator turn, check the consensus slope between the turn before and after
    # consensus slope is defined as (consensus change)/(number of turns)
    # before and after turns is 5 turns
    # it is topic focused, for example, if the conversation is about "price", we only focus on the consensus score of "price"

    differences = []
    topics = list(aggregated_scores.keys())
    topics.remove("overall")
    #load topic options
    with open(f'thoughtful_agents/prompts/{scenario}/options.md', 'r') as f:
        topic_options = f.read()
    for turn in tqdm(mediator_turns):
        if turn <= 5 or turn >= len(conversations)-5:
            differences.append(-1)
            continue
        #identity which topics the mediator try to solve
        speech = conversations[turn]
        prompt = f"""
        You are a mediator in a negotiation. You need to check which topics the current speech is trying to address.
        Only reply with the topics that are mentioned in the speech. If no topics are mentioned, reply with "None".
        Current speech: {speech}
        Here are the topics: {', '.join(topics)}
        Here are some topic options for your references to better understand the context:
        {topic_options}
        Your answer should be a list of topics separated by commas.
        """
        completion_args = {
                "model": 'gpt-4.1',
                "messages": [   
                    {"role": "system", "content": ""},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 50,
                "top_p": 1.0
            }
        response = client.chat.completions.create(**completion_args)
        result = response.choices[0].message.content
        if result == "None":
            differences.append(-1)
            continue
        try:
            addressed_topics = [topic.strip() for topic in result.split(",")]
        except:
            differences.append(-1)
            continue
            
        per_turn_differences=[]
        for topic in addressed_topics:
            if topic not in aggregated_scores:
                continue
            scores = aggregated_scores[topic]
            # calculate the slope before and after the mediator's turn
            before_slope = (scores[turn] - scores[turn-5])/5
            after_slope = (scores[turn+5] - scores[turn])/5

            per_turn_differences.append(after_slope - before_slope)
        differences.append(mean(per_turn_differences))
    print(differences)
    try:
         mean_diff = mean(a for a in differences if a != -1)
    except:
        mean_diff = -1
    return mean_diff, differences

def response_latency(scores, mediator_turns):
    # for each significant decrease in consensus score (>0.2) among 10 turns, check how many turns it takes for the mediator to intervene.
    latencies = []
    for i in range(10, len(scores)):
        if scores[i-10] - scores[i] > 0.1:
            # find the next mediator turn
            for turn in mediator_turns:
                if turn > i:
                    latencies.append(turn - i)
                    break
    return sum(latencies) / len(latencies) if latencies else -1

def main(score_file, conversation_file, method, scenario, skip_topic_evaluation=False):
    # Load scores and conversations from JSON files
    with open(score_file, 'r') as f:
        scores = json.load(f)
    aggregated_scores = process_scores(scores)

    with open(conversation_file, 'r') as f:
        conversations = f.readlines()
        index = conversations.index("📋 Conversation Summary:\n")
        conversations = conversations[index+1:]

    mediator_turns = []
    for i, conversation in enumerate(conversations):
        if i == 0:
            continue
        if conversation.strip() == "":
            break

        if "Mediator" in conversation.split(':')[1]:
            mediator_turns.append(i) #align with the scores, scores including the intial scores
    # Evaluate consensus change
    frequency = evaluate_frequency(conversations)
    print(f"Frequency of Mediator: {frequency}")
    consensus_change = evaluate_consensus_change(aggregated_scores['overall'])
    print(f"Consensus Change: {consensus_change}")

    success_rate = evaluate_success_rate(aggregated_scores)
    print(f"Success Rate: {success_rate}")

    intervention_yield, intervene_per_step = intervene_yield(aggregated_scores, mediator_turns, conversations, scenario)
    print(f"Intervention Yield: {intervention_yield}")
    latency = response_latency(aggregated_scores['overall'], mediator_turns)
    print(f"Response Latency: {latency}") 
    # if method != "NoAgent":
    #     print(f"Mediator efficiency: {calculate_mediator_effect(aggregated_scores, conversations)}")

    # Evaluate topic-level efficiency
    if skip_topic_evaluation:
        return intervention_yield, intervene_per_step, latency, success_rate, consensus_change, frequency, 0, []
    print("Evaluating topic-level efficiency...")

    # max_score = max(aggregated_scores['overall'])
    # min_score = max(0, min(aggregated_scores['overall']))
    # print(f"Max score: {max_score}, Min score: {min_score}")
    # print(f"Score range:", max_score - min_score)
    topic_efficiencies = []
    for topic in aggregated_scores:
        if topic == "overall":
            continue
        
        topic_efficiency = evaluate_topic_level_efficiency(conversations, aggregated_scores, topic)
        topic_efficiencies.append( topic_efficiency)
        print(f"Topic-Level Efficiency for '{topic}': {topic_efficiency}")
    print(f"Average Topic-Level Efficiency: {mean(topic_efficiencies)}")


    return intervention_yield, intervene_per_step, latency, success_rate, consensus_change, frequency, mean(topic_efficiencies), topic_efficiencies

def get_average_behavior_scores(behavior_scores):
    scores = []
    for topic in behavior_scores:
        if behavior_scores[topic]['score']!=-1:
            scores.append(behavior_scores[topic]['score'])
    return sum(scores) / len(scores) if scores else 0

def print_behavior_scores(behavior_scores_file):
    with open(behavior_scores_file, 'r') as f:
        behavior_scores = json.load(f)
    monitoring_scores = []
    planning_scores = []
    simple_scores = []
    print("Behavior Scores:")

    for score in behavior_scores:

        
        monitoring_scores.append(get_average_behavior_scores(score['monitoring']))
        planning_scores.append(get_average_behavior_scores(score['planning']))
        simple_scores.append(get_average_behavior_scores(score['simple']))

    print(f"Monitoring Score: {mean(monitoring_scores)}")
    print(f"Planning Score: {mean(planning_scores)}")
    print(f"Simple Score: {mean(simple_scores)}")
    return mean(monitoring_scores), mean(planning_scores), mean(simple_scores)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate consensus change and topic-level efficiency")
 
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
        choices = ['gpt-4o','gpt-4.1','o4-mini','claude-sonnet-4']
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
        default = "5",
        choices = ['1', '2', '3', '4', '5']
    )

    parser.add_argument(
        '--intervene_freq',
        type = str,
        default = "less",
        choices = ['less', 'more', 'none'],
        help = "Frequency of intervention by the mediator. 'less' means less frequent, 'more' means more frequent."
    )
    

    args = parser.parse_args()
    output_folder = os.path.join('output', args.case, args.method, f'{args.model}_{args.response_type}_{args.mode}_{args.intervene_freq}_{args.id}')
    os.makedirs(output_folder, exist_ok=True)
    conversation_file = os.path.join(output_folder, 'conversation.txt')
    scores_file = os.path.join(output_folder, 'agreement_scores.json')

    behavior_scores_file = os.path.join(output_folder, 'behavior_score.json')
    results_file = os.path.join(output_folder, 'results_summary.csv')

    if os.path.exists(results_file):
      
        print(f"Results file {results_file} already exists.")
        # exit(0)
        df = pd.read_csv(results_file)
        if df["mean_topic_efficiency"][0] == 0:
            print("Need to re-evaluate topic efficiency...")
            skip_topic_evaluation = False
        else:
            skip_topic_evaluation = True
            exit(0)

        intervene_yield, intervene_per_step, latency, success_rate, consensus_change, frequency, mean_topic_efficiency, topic_efficiencies = main(scores_file, conversation_file, args.method, args.case, skip_topic_evaluation)
        success_rate = evaluate_success_rate_max(process_scores(json.load(open(scores_file))))
        df['intervene_yield'] = intervene_yield
        df['intervene_per_step'] = str(intervene_per_step)
        df['mean_topic_efficiency'] = mean_topic_efficiency
        df['topic_efficiencies'] = str(topic_efficiencies)
        df['success_rate_max'] = success_rate
        df.to_csv(results_file, index=False)
        print(f"Results saved to {results_file}")
        exit(0)
       

    intervene_yield, intervene_per_step, latency, success_rate, consensus_change, frequency, mean_topic_efficiency, topic_efficiencies = main(scores_file, conversation_file, args.method, args.case, skip_topic_evaluation=False)
    success_rate_max = evaluate_success_rate_max(process_scores(json.load(open(scores_file))))
    print(f"Success Rate Max: {success_rate_max}")
    if args.method != "NoAgent":
        try:
            monitor, planning, simple = print_behavior_scores(behavior_scores_file)
        except Exception as e:
            print(f"Error occurred while printing behavior scores: {e}" )
            monitor, planning, simple = -1, -1, -1

    #save all the results to a dataframe
    columns = ["intervene_yield", "latency", "success_rate", "success_rate_max", "consensus_change", "frequency", "mean_topic_efficiency", "monitoring_score", "planning_score", "simple_score", "intervene_per_step", "topic_efficiencies"]
    if args.method == "NoAgent":
        data = [[intervene_yield, latency, success_rate, success_rate_max, consensus_change, frequency, mean_topic_efficiency, -1, -1, -1, -1, str(topic_efficiencies)]]
    else:
        data = [[intervene_yield, latency, success_rate, success_rate_max, consensus_change, frequency, mean_topic_efficiency, monitor, planning, simple, str(intervene_per_step), str(topic_efficiencies)]]
    df = pd.DataFrame(data, columns=columns)
    df.to_csv(results_file, index=False)
    print(f"Results saved to {results_file}")