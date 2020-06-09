'''
schema_transform
================

Apply a field name transformation to a data output from the wrapped function,
such that specified field names are transformed and unspecified fields are dropped.
A valid file would be formatted as shown:

{ "tier0_to_tier1":
 { "bad_col": "good_col",
   "another_bad_col": "another_good_col"
 }
}
'''

import pandas
import json

def load_transformer(filename):
    with open(filename) as f:
        _data = json.load(f)
    return _data['tier0_to_tier1']
    return transformer


def schema_transform(filename):
    '''
    Args:
        filename (str): A record-oriented JSON file path mapping field names

    Returns:
        Data in the format it was originally passed to the wrapper in, with 
        specified field names transformed and unspecified fields dropped.
    '''

    transformer = load_transformer(filename)
    def wrapper(func):
        def transformed(*args, **kwargs):
            data = func(*args,**kwargs)
            # Accept DataFrames...
            if type(data) == pandas.DataFrame:
                drop_cols = [c for c in data.columns 
                             if c not in transformer]
                data.drop(drop_cols, axis=1, inplace=True)
                data.rename(columns=transformer, inplace=True)
            # ... OR list of dicts
            elif type(data) == list and all(type(row) == dict for row in data):
                data = [{transformer[k]:v for k, v in row.items()
                         if k in transformer} for row in data]
            # Otherwise throw an error
            else:
                raise ValueError("Schema transform expects EITHER a "
                                 "pandas.DataFrame "
                                 "OR a list of dict from the wrapped "
                                 "function.")
            return data
        return transformed
    return wrapper


def schema_transformer(data, *, filename, ignore=[]):
    '''Function version of the schema_transformer wrapper.
    Args:
        data (dataframe OR list of dicts): the data requiring the schama transformation
        filename (str): the path to the schema json file
        ignore (list): optional list of fields, eg ids or keys which shouldn't be dropped

    Returns:
        supplied data with schema applied
    '''
    # Accept DataFrames...
    transformer = load_transformer(filename)
    if type(data) == pandas.DataFrame:
        drop_cols = [c for c in data.columns
                     if c not in transformer
                     and c not in ignore]
        data.drop(drop_cols, axis=1, inplace=True)
        data.rename(columns=transformer, inplace=True)
        return data
    # ... OR list of dicts
    elif type(data) == list and all(type(row) == dict for row in data):
        transformed_data = []
        for row in data:
            transformed = {transformer[k]: v for k, v in row.items() 
                           if k in transformer}
            ignored = {k: v for k, v in row.items() if k in ignore}
            transformed_data.append({**transformed, **ignored})
        return transformed_data
    # ... OR a single dict
    elif type(data) == dict:
        transformed = {transformer[k]: v for k, v in data.items() if k in transformer}

        ignored = {k: v for k, v in data.items() if k in ignore}
        return {**transformed, **ignored}

    # Otherwise throw an error
    else:
        raise ValueError("Schema transform expects EITHER a "
                         "pandas.DataFrame "
                         "OR a list of dict, "
                         "OR a single dict from the "
                         "wrapped function.")
