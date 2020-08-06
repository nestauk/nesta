"""
[AutoML*] run.py (corex_topic_model) 
====================================

Generate topics based on the CorEx algorithm. Loss is calculated from the total correlation explained.
"""

import pandas as pd
import json
from scipy.sparse import csr_matrix
from corextopic import corextopic as ct
from nesta.core.luigihacks.s3 import parse_s3_path
import os
import boto3
from ast import literal_eval

WEIGHT_THRESHOLD = 1e-2

def term_count_to_sparse(term_counts):
    # Pack the data into a sparse matrix                  
    indptr = [0]  # Number of non-null entries per row    
    indices = []  # Positions of non-null entries per row 
    counts = []  # Term counts/weights per position       
    vocab = {}  # {Term: position} lookup                 
    for row in term_counts:
        for term, count in row.items():
            idx = vocab.setdefault(term, len(vocab))
            indices.append(idx)
            counts.append(count)
        indptr.append(len(indices))
    X = csr_matrix((counts, indices, indptr), dtype=int)

    # {Position: term} lookup                             
    _vocab = {v:k for k, v in vocab.items()}
    return X, _vocab


def run():
    s3_path_in = os.environ['BATCHPAR_s3_path_in']
    n_hidden = int(literal_eval(os.environ['BATCHPAR_n_hidden']))

    # Load and shape the data
    s3 = boto3.resource('s3')
    s3_obj_in = s3.Object(*parse_s3_path(s3_path_in))
    data = json.load(s3_obj_in.get()['Body'])    
    term_counts = data['term_counts']
    ids = data['id']
    X, _vocab = term_counts_to_sparse(term_counts)

    # Fit the model
    topic_model = ct.Corex(n_hidden=n_hidden)
    topic_model.fit(X)
    topics = topic_model.get_topics()

    # Generate topic names
    topic_names = {f'topic_{itop}': [_vocab[idx]
                                     for idx, weight in topic]
                   for itop, topic in enumerate(topics)}

    # Calculate topic weights as sum(bool(term in doc)*{term_weight})
    rows = [{f'topic_{itop}': sum(row.getcol(idx).toarray()[0][0]*weight
                                  for idx, weight in topic)
             for itop, topic in enumerate(topics)}
            for row in X]
    # Zip the row indexes back in, and ignore small weights
    rows = [dict(id=id, **{k: v for k, v in row.items()
                           if v > WEIGHT_THRESHOLD})
            for id, row in zip(ids, rows)]

    # Curate the output
    output = {'loss': topic_model.tc,
              'data': {'topic_names': topic_names,
                       'rows': rows}}

    # Mark the task as done and save the data
    if "BATCHPAR_outinfo" in os.environ:
        s3_path_out = os.environ["BATCHPAR_outinfo"]
        s3 = boto3.resource('s3')
        s3_obj = s3.Object(*parse_s3_path(s3_path_out))
        s3_obj.put(Body=json.dumps(output))

if __name__ == "__main__":
    if "BATCHPAR_outinfo" not in os.environ:
        os.environ["BATCHPAR_s3_path_in"] = 's3://nesta-arxlive/automl/2019-07-04/VECTORIZER.binary_True.min_df_0.001.NGRAM.TEST_True-0_5164.json'
        os.environ["BATCHPAR_n_hidden"] = '39'
    run()
