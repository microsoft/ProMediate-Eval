
#!/bin/bash

# get a general metric TODO, provide case folder, and exact number of run
# make all prompts in one folder
# parameters
case=hmo
method=Social
mode=competing
id=3
model=o4-mini
# run negotiation
python multiparty_conversation_negotiate.py --case $case --method $method --mode $mode --id $id --model $model
# run behavior evaluation
python scripts/behavior_evaluation.py --case $case --method $method --mode $mode --id $id --model $model
# run consensus agreement evaluation
python scripts/consensus_agreement_pipeline.py --case $case --method $method --mode $mode --id $id --model $model
# run summary evaluation
python evaluation.py --case $case --method $method --mode $mode --id $id --model $model
# run visualization
python scripts/visualize_agreement.py --case $case --method $method --mode $mode --id $id --model $model