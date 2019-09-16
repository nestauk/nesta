import pandas as pd
from nesta.packages.misc_utils.camel_to_snake import camel_to_snake
from itertools import chain

TOP_URL = 'http://cordis.europa.eu/data/cordis-{}{}.csv'
ENTITIES = {'fp7': ['projects', 'organizations', 'reports'],
            'h2020': ['projects', 'organizations',
                      'projectPublications',
                      'reports', 'projectDeliverables']}


def fetch_and_clean(fp, entity_name, nrows=None):
    '''Fetch Cordis CSV data by entity name, and remove null columns
    and tidy column names

    Args:
        entity_name (str): Cordis entity name.
    Returns:
        df (pd.DataFrame): Pandas DataFrame of the CSV data.
    '''
    # Fetch data and clean
    df = pd.read_csv(TOP_URL.format(fp, entity_name),
                     nrows=nrows,
                     engine='c',
                     decimal=',', sep=';',
                     error_bad_lines=False,
                     warn_bad_lines=True,
                     encoding='latin')
    df = df.dropna(axis=1, how='all')
    df.columns = [camel_to_snake(col) for col in df.columns]
    return df


def pop_and_split_programmes(df, old_name='programme',
                             new_name='programmes',
                             bonus_static_field='framework_programme'):
    '''Pop and split out programmes from the 'projects' DataFrame.
    This modifies the original DataFrame.

    Args:
        df (pd.DataFrame): 'projects' DataFrame, which will be modified.
        old_name (str): The name of incoming programme field
        new_name (str): Name of the new programme field, after splitting
        bonus_static_field (str): A field assumed to be constant
                                  which will also be popped out.
    Returns:
       _df (pd.DataFrame): New DataFrame containing all programmes.
    '''
    fp = df.pop(bonus_static_field)[0]
    df[new_name] = [items.split(";") for items in df.pop(old_name)]
    unique_items = set(chain.from_iterable(df[new_name]))
    return pd.DataFrame([{'id': item, bonus_static_field: fp}
                         for item in unique_items])


if __name__ == "__main__":
    data = {}
    for fp, entities in ENTITIES.items():
        _data = {}
        print(fp)
        for entity_name in entities:
            print("\t", entity_name)
            df = fetch_and_clean(fp, entity_name)
            if entity_name == 'projects':
                _data['programmes'] = pop_and_split_programmes(df)
            _data[entity_name] = df
            class_name = entity_name[0].upper() + entity_name[1:]
            table_name = f'cordis{fp}_{camel_to_snake(class_name)}'
            print("\t\t", table_name)
        data[fp] = _data
        # _class = get_class_by_tablename(table_name)
        # for row in df: _row = _class(**row); insert_row(engine, _row);
