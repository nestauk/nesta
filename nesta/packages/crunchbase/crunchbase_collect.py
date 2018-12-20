from contextlib import contextmanager
import logging
import pandas as pd
import re
import requests
import tarfile
from tempfile import NamedTemporaryFile

from nesta.production.luigihacks import misctools
from nesta.production.orms.orm_utils import insert_data
from nesta.packages.geo_utils.country_iso_code import country_iso_code_to_name
from nesta.packages.geo_utils.geocode import generate_composite_key


@contextmanager
def crunchbase_tar():
    """Downloads the tar archive of Crunchbase data.

    Returns:
        :code:`tarfile.Tarfile`: opened tar archive
    """
    crunchbase_config = misctools.get_config('crunchbase.config', 'crunchbase')
    user_key = crunchbase_config['user_key']
    url = 'https://api.crunchbase.com/v3.1/csv_export/csv_export.tar.gz?user_key='
    with NamedTemporaryFile() as tmp_file:
        r = requests.get(''.join([url, user_key]))
        tmp_file.write(r.content)
        try:
            tmp_tar = tarfile.open(tmp_file.name)
            yield tmp_tar
        finally:
            tmp_tar.close()


def get_csv_list():
    """Gets a list of csv files within the Crunchbase tar archive.

    Returns:
        list: all .csv files int the archive
    """
    csvs = []
    csv_pattern = re.compile(r'^(.*)\.csv$')
    with crunchbase_tar() as tar:
        names = tar.getnames()
    for name in names:
        tablename = csv_pattern.match(name)
        if tablename is not None:
            csvs.append(tablename.group(1))
    return csvs


def get_files_from_tar(files, test=False):
    """Converts csv files in the crunchbase tar into dataframes and returns them.

    Args:
        files (list): names of the files to extract (without .csv suffix)
        test (bool): flag to reduce the number of records retrieved, for testing

    Returns:
        (:obj:`list` of :obj:`pandas.Dataframe`): the extracted files as dataframes
    """
    if type(files) != list:
        raise TypeError("Files must be provided as a list")

    nrows = 1000 if test else None
    dfs = []
    with crunchbase_tar() as tar:
        for filename in files:
            dfs.append(pd.read_csv(tar.extractfile(''.join([filename, '.csv'])),
                                   low_memory=False, nrows=nrows))
            logging.warning(f"Collected {filename} from crunchbase tarfile")
    return dfs


def rename_uuid_columns(data):
    """Renames any columns called or containing `uuid`, to the convention of `id`.

    Args:
        data (:obj:`pandas.Dataframe`): dataframe with column names to amend

    Returns:
        (:obj:`pandas.Dataframe`): the original dataframe with amended column names
    """
    renames = {col: col.replace('uuid', 'id') for col in data}
    return data.rename(columns=renames)


def bool_convert(value):
    """Converter from string representations of bool to python bools.

    Args:
        value (str): t or f

    Returns:
        (bool): boolean representation of the field, or None on failure
    """
    lookup = {'t': True, 'f': False}
    try:
        return lookup[value]
    except KeyError:
        logging.info(f"Not able to convert to a boolean: {value}")


def _generate_composite_key(**kwargs):
    """Wrapper around generate_composite_key to treat errors and therefore allow it to
    be used with pd.apply

    Returns:
        (str): composite key if able to generate, otherwise None
    """
    try:
        return generate_composite_key(**kwargs)
    except ValueError:
        return None


def total_records(data_dict, append_to=None):
    """Calculates totals for a dictionary of records and appends a grand total.

    Args:
        data_dict (dict): data with description as the key, and list of dicts as the
                value
        append_to (dict): a previously returned dict from this function, will add
                the values for batch operation

    Returns:
        (dict): labels as per the provided data_dict, with totals as the values.
                `total` is appended with a sum of all values, plus `batch_total` if
                append_to is provided
    """
    totals = {}
    total = 0
    for k, v in data_dict.items():
        length = len(v)
        totals[k] = length
        total += length
    totals['total'] = total

    if append_to is not None:
        for k, v in totals.items():
            totals[k] += append_to[k]
    totals['batch_total'] = total

    return totals


def split_batches(data, batch_size):
    """Breaks batches down into chunks consumable by the database.

    Args:
        data (:obj:`list` of :obj:`dict`): list of rows of data
        batch_size (int): number of rows per batch

    Returns:
        (:obj:`list` of :obj:`dict`): yields a batch at a time
    """
    if len(data) <= batch_size:
        yield data
    else:
        batch = []
        for row in data:
            batch.append(row)
            if len(batch) == batch_size:
                yield batch
                batch.clear()
        if len(batch) > 0:
            yield batch


def _insert_data(config, section, database, base, table, data, batch_size=500):
    """Writes out a dataframe to MySQL and checks totals are equal, or raises error.

    Args:
        table (:obj:`sqlalchemy.mapping`): table where the data should be written
        data (:obj:`list` of :obj:`dict`): data to be written
        batch_size (int): size of bulk inserts into the db
    """
    total_rows_in = len(data)
    logging.warning(f"Inserting {total_rows_in} rows of data into {table.__tablename__}")

    totals = None
    for batch in split_batches(data, batch_size):
        returned = {}
        returned['inserted'], returned['existing'], returned['failed'] = insert_data(
                                                        config, section, database,
                                                        base, table, batch,
                                                        return_non_inserted=True)

        totals = total_records(returned, totals)
        for k, v in totals.items():
            logging.debug(f"{k} rows: {v}")
        logging.debug("--------------")
        if totals['batch_total'] != len(batch):
            raise ValueError(f"Inserted {table} data is not equal to original: {len(batch)}")

    if totals['total'] != total_rows_in:
        raise ValueError(f"Inserted {table} data is not equal to original: {total_rows_in}")


def process_orgs(orgs, existing_orgs, cat_groups, org_descriptions):
    """Processes the organizations data.

    Args:
        orgs (:obj:`pandas.Dataframe`): organizations data
        existing_orgs (set): ids of orgs already in the database
        cat_groups (:obj:`pandas.Dataframe`): category groups data
        org_descriptions (:obj:`pandas.Dataframe`): long organization descriptions

    Returns:
        (:obj:`list` of :obj:`dict`): processed organization data
        (:obj:`list` of :obj:`dict`): generated organization_category data
        (:obj:`list` of :obj:`dict`): names of missing categories from category_groups
    """
    # fix uuid column names
    orgs = rename_uuid_columns(orgs)

    # change NaNs to None
    orgs = orgs.where(orgs.notnull(), None)
    org_descriptions = org_descriptions.where(org_descriptions.notnull(), None)

    # lookup country name and add as a column
    orgs['country'] = orgs['country_code'].apply(country_iso_code_to_name)
    orgs = orgs.drop('country_code', axis=1)  # now redundant with country_alpha_3 appended

    orgs['long_description'] = None
    org_cats = []
    cat_groups = cat_groups.set_index(['category_name'])
    missing_cat_groups = set()
    org_descriptions = org_descriptions.set_index(['uuid'])

    # generate composite key for location lookup
    logging.info("Generating composite keys for location")
    orgs['location_id'] = orgs[['city', 'country']].apply(lambda row: _generate_composite_key(**row), axis=1)

    for idx, row in orgs.iterrows():
        # generate link table data for organization categories
        try:
            for cat in row.category_list.split(','):
                org_cats.append({'organization_id': row.id,
                                 'category_name': cat.lower()})
        except AttributeError:
            # ignore NaNs
            pass

        # append long descriptions to organization
        try:
            orgs.at[idx, 'long_description'] = org_descriptions.loc[row.id].description
        except KeyError:
            # many of these are missing
            pass

        if not (idx + 1) % 10000:
            logging.info(f"Processed {idx + 1} organizations")
    logging.info(f"Processed {idx + 1} organizations")

    # identify missing category_groups
    for row in org_cats:
        category_name = row['category_name']
        try:
            cat_groups.loc[category_name]
        except KeyError:
            logging.debug(f"Category '{category_name}' not found in categories table")
            missing_cat_groups.add(category_name)
    logging.info(f"{len(missing_cat_groups)} missing category groups to add")
    missing_cat_groups = [{'category_name': cat} for cat in missing_cat_groups]

    # remove redundant category columns
    orgs = orgs.drop(['category_list', 'category_group_list'], axis=1)

    # remove existing orgs
    drop_mask = orgs['id'].apply(lambda x: x in existing_orgs)
    orgs = orgs.loc[~drop_mask]
    orgs = orgs.to_dict(orient='records')

    return orgs, org_cats, missing_cat_groups


def process_non_orgs(df, existing, pks):
    """Processes any crunchbase table, other than organizations, which are already
    handled by the process_orgs function.

    Args:
        df (:obj: `pd.DataFrame`): data from one table
        existing (:obj: `set` of :obj: `tuple`): tuples of primary keys that are already in the database
        pks (list): names of primary key columns in the dataframe

    Returns:
        (:obj:`list` of :obj:`dict`): processed table with existing records removed
    """
    # fix uuid column names
    df = rename_uuid_columns(df)

    # drop any rows already existing in the database
    total_records = len(df)
    drop_mask = df[pks].apply(lambda row: tuple(row[pks]) in existing, axis=1)
    df = df.loc[~drop_mask]
    logging.warning(f"Dropped {total_records - len(df)} rows already existing in database")

    # change NaNs to None
    df = df.where(df.notnull(), None)

    # convert country name and add composite key if locations in table
    if {'city', 'country_code'}.issubset(df.columns):
        logging.warning("Locations found in table. Generating composite keys.")
        df['country'] = df['country_code'].apply(country_iso_code_to_name)
        df = df.drop('country_code', axis=1)  # now redundant with country_alpha_3 appended
        df['location_id'] = df[['city', 'country']].apply(lambda row: _generate_composite_key(**row), axis=1)

    # convert any boolean columns to correct values
    for column in (col for col in df.columns if re.match(r'^is_.+', col)):
        logging.warning(f"Converting boolean field {column}")
        df[column] = df[column].apply(bool_convert)

    df = df.to_dict(orient='records')
    return df


if __name__ == '__main__':
    log_stream_handler = logging.StreamHandler()
    log_file_handler = logging.FileHandler('logs.log')
    logging.basicConfig(handlers=(log_stream_handler, log_file_handler),
                        level=logging.INFO,
                        format="%(asctime)s:%(levelname)s:%(message)s")

    # orgs = get_files_from_tar(['organizations'], test=True)
    # with crunchbase_tar() as tar:
    #     names = tar.getnames()
    # print(names)
    # assert 'category_groups.csv' in names

    # with crunchbase_tar() as tar:
    #     cg_df = pd.read_csv(tar.extractfile('category_groups.csv'))
    # print(cg_df.columns)
