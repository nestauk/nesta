"""
ngrammer batchable
------------------

Extracts ngrams on a chunk of data.
"""

import os
import boto3
from nesta.packages.nlp_utils.ngrammer import Ngrammer
from nesta.production.luigihacks.s3 import parse_s3_path
import json

def run():
    # Extract environmental variables
    s3_path_in = os.environ['BATCHPAR_s3_path_in']
    s3_path_out = os.environ["BATCHPAR_outinfo"]
    first_index = int(os.environ['BATCHPAR_first_index'])
    last_index = int(os.environ['BATCHPAR_last_index'])

    # Load the chunk
    s3 = boto3.resource('s3')
    s3_obj_in = s3.Object(*parse_s3_path(s3_path_in))
    data = json.load(s3_obj_in.get()['Body'])

    # Extract ngrams
    ngrammer = Ngrammer(config_filepath="mysqldb.config",
                        database="production")
    processed = []
    for i, row in enumerate(data[first_index: last_index]):
        new_row = {k: ngrammer.process_document(v) 
                   if type(v) is str and len(v) > 50 else v
                   for k, v in row.items()}
        processed.append(new_row)

    # Mark the task as done and save the data
    if s3_path_out != "":
        s3 = boto3.resource('s3')
        s3_obj = s3.Object(*parse_s3_path(s3_path_out))
        s3_obj.put(Body=json.dumps(processed))


if __name__ == "__main__":
    # Local testing
    if "BATCHPAR_outinfo" not in os.environ:
        os.environ['BATCHPAR_s3_path_in'] = "s3://clio-data/gtr/raw_data/gtr_raw_data.json"
        os.environ['BATCHPAR_outinfo'] = "s3://clio-data/gtr/intermediate/gtr/raw_data_to_gtr/processed_data_ngram.0-10.json"
        os.environ['BATCHPAR_first_index'] = '0'
        os.environ["BATCHPAR_last_index"] = '10'
    run()
