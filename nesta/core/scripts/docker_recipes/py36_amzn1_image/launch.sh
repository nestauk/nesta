#!/bin/bash

df -h
# Install any other python packages which aren't picked up
# in the requirements
# sudo ls /usr/bin/pip*
# sudo /usr/bin/pip-3.6 install awscli --upgrade --user
# sudo /usr/bin/pip-3.6 install pyvirtualdisplay
source activate py36
which pip
which python
pip install awscli --upgrade --user
df -h
pip install lxml
df -h

# Pull the batchable from S3
echo "Getting file" ${BATCHPAR_S3FILE_TIMESTAMP}
aws s3 cp s3://nesta-batch/${BATCHPAR_S3FILE_TIMESTAMP} run.zip
df -h
/usr/bin/unzip run.zip
df -h
rm run.zip  # clear up some space
df -h
cd run
ls

# Print out the caller id
#aws sts get-caller-identity
#aws iam list-roles
#export WORLD_BORDERS="meetup/data/TM_WORLD_BORDERS_SIMPL-0.3.shp"

# You could install anything else here as you wish, 
# but you should really do this in the Dockerfile
# sudo yum -y install wget
# sudo yum -y install findutils

# Install dependencies from the requirements file
#sudo /usr/bin/pip-3.6 install -r requirements.txt
#sudo /usr/bin/pip-3.6 install lxml

sed -i '/tensorflow/d' requirements.txt  # remove TF from reqs since it's huge
pip install -r requirements.txt
pip freeze
df -h

conda clean --all -y
df -h

# Check the file exists and run it
echo "Starting..."
cat run.py &> /dev/null
#time /usr/bin/python3.6 run.py
time python run.py
