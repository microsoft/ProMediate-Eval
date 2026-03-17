# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from openai import OpenAI, APIError, AzureOpenAI
import os
import json
import numpy as np
import re
import sys
import argparse


import matplotlib.pyplot as plt



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

def smoothed_out(scores, window_size=3):
    moving_avg = [sum(scores[i:i+window_size]) / window_size for i in range(len(scores) - window_size + 1)]

    x_moving_avg = list(range(window_size - 1, len(scores)))
    return moving_avg

def get_average(scores):
    num = len(scores)
    column_average = [sum(col)/num for col in zip(*scores)]
    return column_average
def get_average(scores, topic):
        pred_score = [item['Overall_score'] for item in scores[topic]]
        return pred_score
  



def visualize_agreement(scores, folder):
    """
    Visualize the agreement scores for each topic and overall.
    """
    topics = list(scores.keys())
    plt.figure(figsize=(12, 6))

    for topic in topics:
        plt.plot(scores[topic], label=topic)

    plt.xlabel('Turn')
    plt.ylabel('Agreement Score')
    plt.title('Agreement Scores by Topic')
    plt.legend()
    plt.grid(True)
    plt.savefig(os.path.join(folder, 'agreement_scores_by_topic.png'))
    plt.close()

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Visualize agreement scores.")

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
        choices = ['gpt-4o','gpt-4.1','o4-mini']
    )
    parser.add_argument(
        "--mode",
        type = str,
        default = "accommodating",
        choices = ['competing','accommodating','avoiding','compromising','collaborating']
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
        default = "5",
    )
    args = parser.parse_args()
    
    output_folder = os.path.join('output', args.case, args.method, f'{args.model}_{args.response_type}_{args.mode}_{args.intervene_freq}_{args.id}')
    os.makedirs(output_folder, exist_ok=True)
    scores_file = os.path.join(output_folder, 'agreement_scores.json')
    scores_dict = json.load(open(scores_file))
    scores_all = process_scores(scores_dict)
    visualize_agreement(scores_all, output_folder)