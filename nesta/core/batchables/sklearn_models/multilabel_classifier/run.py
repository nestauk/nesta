import os
import importlib
from scipy.sparse import csr_matrix
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import boto3
from nesta.core.luigihacks.s3 import parse_s3_path
import json
import pandas as pd

GENERIC_KEYS = set(['outinfo', 'done', 'first_index', 'class_field',
                    'last_index', 's3_path_in', 'model', 'S3FILE_TIMESTAMP'])

def retrieve_model():
    sklearn_module, model = os.environ['BATCHPAR_model'].split('.')
    pkg = importlib.import_module(f'sklearn.{sklearn_module}')
    return getattr(pkg, model)


def numberfy(s):
    if s == 'True' or s == 'true':
        return True
    if s == 'False' or s == 'false':
        return False
    if s == 'None':
        return None
    try:
        v = float(s)
    except ValueError:
        return s
    negint = s.startswith('-') and s[1:].isdigit()
    if s.isdigit() or negint or (v - int(v) == 0):
        return int(v)
    return v

def retrieve_model_kwargs():
    kwargs = {}
    for k, v in os.environ.items():
        if not k.startswith('BATCHPAR'):
            continue
        key = k.split('BATCHPAR_')[1]
        if key in GENERIC_KEYS:
            continue
        kwargs[key] = numberfy(v)
    return kwargs


def term_counts_to_sparse(term_counts):
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
    # Load and shape the data
    s3_path_in = os.environ['BATCHPAR_s3_path_in']
    class_field = os.environ['BATCHPAR_class_field']

    # 
    s3 = boto3.resource('s3')
    s3_obj_in = s3.Object(*parse_s3_path(s3_path_in))
    data = json.load(s3_obj_in.get()['Body'])
    term_counts = [row['term_counts'] for row in data]
    classes = [row[class_field] for row in data]
    ids = [row['id'] for row in data]

    # Prepare the data for processing
    le = LabelEncoder()
    X, vocab = term_counts_to_sparse(term_counts)
    y = le.fit_transform(classes)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.1)

    #
    kwargs = retrieve_model_kwargs()
    Model = retrieve_model()
    model = Model(**kwargs)
    model.fit(X_train, y_train)
    y_test_pred = model.predict(X_test)
    score = f1_score(y_test, y_test_pred, average='weighted')

    y_pred = model.predict(X)
    class_probs = model.predict_proba(X)
    out_data = pd.DataFrame(index=ids, columns=le.inverse_transform(model.classes_), 
                            data=class_probs)
    out_data = out_data.to_dict(orient='records')

    # Curate the output
    output = {'loss': score,
              'data': {'class_probabilities': out_data,
                       'rows': data}}

    # Mark the task as done and save the data
    if "BATCHPAR_outinfo" in os.environ:
        s3_path_out = os.environ["BATCHPAR_outinfo"]
        s3 = boto3.resource('s3')
        s3_obj = s3.Object(*parse_s3_path(s3_path_out))
        s3_obj.put(Body=json.dumps(output))


if __name__ == "__main__":
    if "BATCHPAR_outinfo" not in os.environ:
        kwargs = {}
        S3PATH = 's3://nesta-glass-ai/sic-classifer/automl/2020-07-16/'
        SUFFIX = 'VECTORIZER.binary_False.min_df_0-001.max_df_0-9.NGRAM.TEST_True'
        kwargs['outinfo'] = (f'{S3PATH}RANDOM_FOREST.model_ensemble.RandomForestClassifier.'
                             'class_weight_balanced.max_depth_1-0.min_samples_leaf_2-0.'
                             'n_jobs_2.max_samples_0-3.{SUFFIX}-0_618.json')
        kwargs['first_index'] = '0'
        kwargs['last_index'] = '618'
        kwargs['s3_path_in'] = f'{S3PATH}{SUFFIX}.json'
        kwargs['model'] = 'ensemble.RandomForestClassifier'
        kwargs['class_field'] = 'sic'

        kwargs['class_weight'] = 'balanced'
        kwargs['n_jobs'] = '2'
        kwargs['min_samples_leaf'] = '2.0'
        kwargs['max_depth'] = '1.0'
        kwargs['n_estimators'] = '23.0'
        for k, v in kwargs.items():
            os.environ[f'BATCHPAR_{k}'] = v
    run()
