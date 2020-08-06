"""
[AutoML] run.py (ngrammer)
--------------------------

Find and replace ngrams in a body of text, based on
Wiktionary N-Grams. Whilst at it, the ngrammer
also tokenizes and removes stop words (unless they
occur within an n-gram)
"""

import os
import boto3
from nesta.packages.nlp_utils.ngrammer import Ngrammer
from nesta.core.luigihacks.s3 import parse_s3_path
import json


def run():
    # Extract environmental variables
    s3_path_in = os.environ['BATCHPAR_s3_path_in']
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
    if "BATCHPAR_outinfo" in os.environ:
        s3_path_out = os.environ["BATCHPAR_outinfo"]
        s3 = boto3.resource('s3')
        s3_obj = s3.Object(*parse_s3_path(s3_path_out))
        s3_obj.put(Body=json.dumps(processed))


if __name__ == "__main__":
    # Local testing
    if "BATCHPAR_outinfo" not in os.environ:
        os.environ["BATCHPAR_s3_path_in"] = ("s3://nesta-arxlive/"
                                             "raw-inputs/2019-06-18/"
                                             "data.0-True.json")
        os.environ["BATCHPAR_last_index"] = "-1"
        os.environ["BATCHPAR_first_index"] = "0"
        os.environ["BATCHPAR_S3FILE_TIMESTAMP"] = ("run-1560876797"
                                                   "721923813.zip")
        os.environ['BATCHPAR_s3_path_in'] = ("s3://clio-data/gtr/"
                                             "VECTORIZER.binary_True."
                                             "min_df_0-001.NGRAM.TEST_"
                                             "True-0_2000.json")
    run()
