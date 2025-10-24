#!/bin/bash

#SBATCH --job-name=get.data
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --partition=sixhour
#SBATCH --chdir=/home/k506c250/work/kuhpcc.info
#SBATCH --mem=1000
#SBATCH --time=10

# this script runs every hour on the 45 minute mark using cron
# crontab -e:
# 45 * * * * flock -n /tmp/kuhpcc.lock sbatch /home/k506c250/work/kuhpcc.info/getusage.sh

# make sure git process isn't causing a failure
cd /home/k506c250/work/kuhpcc.info || exit 1
find .git -type f -name "*.lock" -delete

# remove previous slurm file(s)
ls -1t slurm-* 2>/dev/null | tail -n +2 | xargs -r rm --

# get the usage file
cp /kuhpc/work/bi/usage.txt .

# create a cleaned usage file with summary information
{
  # introductory information
  echo BI work storage use per user
  echo
  head -n1 usage.txt
  echo

  # disk free information
  df -h /kuhpc/work/bi | awk 'NR==1 {print $2 "\t" $3 "\t" $4 "\t" $5} NR==2 {print $2 "\t" $3 "\t" $4 "\t" $5}'
  echo

  # equal distribution per user
  total_tb=40 # hardcoded
  total_gb=$(( total_tb * 1024 ))
  read c1 c10 c100 c1000 < <(tail -n +3 usage.txt | tr ',' '\t' | awk '
    function to_gb(val, unit) {
      if (unit == "KB") return val / (1024 * 1024)
      if (unit == "MB") return val / 1024
      if (unit == "GB") return val
      if (unit == "TB") return val * 1024
      if (unit == "B")  return val / (1024 * 1024 * 1024)
      return 0
    }
    {
      match($2, /^([0-9.]+)([KMGTP]?B)$/, m)
      val = m[1]
      unit = m[2]
      gb = to_gb(val + 0, unit)
      if (gb >= 1) c1++
      if (gb >= 10) c10++
      if (gb >= 100) c100++
      if (gb >= 1000) c1000++
    }
    END {
      print c1+0, c10+0, c100+0, c1000+0
    }
  ')
  echo "Equal sharing user allotment"
  echo -e "per current # users >=\t1GB\t10GB\t100GB\t1000GB"
  alloc1=$(( c1 > 0 ? total_gb / c1 : 0 ))
  alloc10=$(( c10 > 0 ? total_gb / c10 : 0 ))
  alloc100=$(( c100 > 0 ? total_gb / c100 : 0 ))
  alloc1000=$(( c1000 > 0 ? total_gb / c1000 : 0 ))
  echo -e "allotment =\t\t\t${alloc1}GB\t${alloc10}GB\t${alloc100}GB\t${alloc1000}GB"
  echo

  # current usage
  echo -e "RANK\tUSERNAME\tDISK USED\tFILES USED"
  tail -n +3 usage.txt | tr ',' '\t' | awk '
    function to_gb(val, unit) {
      if (unit == "KB") return val / (1024 * 1024)
      if (unit == "MB") return val / 1024
      if (unit == "GB") return val
      if (unit == "TB") return val * 1024
      if (unit == "B")  return val / (1024 * 1024 * 1024)
      return 0
    }
    {
      match($2, /^([0-9.]+)([KMGTP]?B)$/, m)
      val = m[1]
      unit = m[2]
      gb = to_gb(val + 0, unit)
      $2 = sprintf("%.2fGB", gb)
      print
    }
  ' OFS='\t' | sort -k2 -r -g | awk 'BEGIN{num=1} {print num++, $0}' OFS='\t'
} > clean_usage.txt

# push to github
cd /home/k506c250/work/kuhpcc.info
git add clean_usage.txt
git add usage.txt
git commit -m "Auto update: $(date '+%Y-%m-%d %H:%M')"
git push origin main

# github repo: https://github.com/katherinecrawford/kuhpcc.info
# file: https://github.com/katherinecrawford/kuhpcc.info/blob/main/clean_usage.txt
