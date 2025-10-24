#!/bin/bash
#SBATCH --job-name=repo_check
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --partition=sixhour
#SBATCH --chdir=/home/k506c250/work/kuhpcc.info
#SBATCH --mem=1000
#SBATCH --time=10
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=kjcrawford@ku.edu

REPO_DIR="/home/k506c250/work/kuhpcc.info"

cd "$REPO_DIR" || exit 1

last_commit_time=$(git log -1 --format=%ct)
current_time=$(date +%s)
diff_hours=$(( (current_time - last_commit_time) / 3600 ))

if [ "$diff_hours" -gt 24 ]; then
    echo "Repo $REPO_DIR has not been updated for over 24 hours. Last commit was $diff_hours hours ago."
    exit 1
else
    echo "Repo updated within the last 24 hours. No email alert will be sent."
    exit 0  # stop here so Slurm doesn't email you
fi
