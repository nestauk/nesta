from contextlib import contextmanager
import logging
import pandas as pd
import re
import requests
import tarfile
from tempfile import NamedTemporaryFile

from nesta.production.luigihacks import misctools
from nesta.packages.geo_utils.country_iso_code import country_iso_code_to_name


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
    nrows = 1000 if test else None
    dfs = []
    with crunchbase_tar() as tar:
        for filename in files:
            dfs.append(pd.read_csv(tar.extractfile(''.join([filename, '.csv'])),
                                   low_memory=False, keep_default_na=False, nrows=nrows))
            logging.info(f"Collected {filename} from crunchbase tarfile")
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


def generate_composite_key(city=None, country=None):
    """Generates a composite key to use as the primary key for the geographic data.

    Args:
        city (str): name of the city
        country (str): name of the country

    Returns:
        (str): composite key
    """
    try:
        city = city.replace(' ', '-').lower()
        country = country.replace(' ', '-').lower()
    except AttributeError:
        raise ValueError(f"Invalid city or country name. City: {city} | Country: {country}")
    return '_'.join([city, country])


def process_orgs(orgs, cat_groups, org_descriptions):
    """Processes the organizations data.

    Args:
        orgs (:obj:`pandas.Dataframe`): organizations data
        cat_groups (:obj:`pandas.Dataframe`): category groups data
        org_descriptions (:obj:`pandas.Dataframe`): long organization descriptions

    Returns:
        (:obj:`list` of :obj:`dict`): processed organization data
        (:obj:`list` of :obj:`dict`): generated organization_category data
        (:obj:`list` of :obj:`dict`): names of missing categories from category_groups
    """
    # fix uuid column names
    orgs = rename_uuid_columns(orgs)

    # lookup country name and add as a column
    orgs['country'] = orgs['country_code'].apply(country_iso_code_to_name)
    orgs = orgs.drop('country_code', axis=1)  # now redundant with country_alpha_3 appended

    orgs['location_id'] = None
    orgs['long_description'] = None
    org_cats = []
    cat_groups = cat_groups.set_index(['category_name'])
    missing_cat_groups = set()
    org_descriptions = org_descriptions.set_index(['uuid'])

    for idx, row in orgs.iterrows():
        # generate composite key for location lookup
        try:
            comp_key = generate_composite_key(row.city, row.country)
        except ValueError:
            pass
        else:
            orgs.at[idx, 'location_id'] = comp_key

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
    orgs = orgs.to_dict(orient='records')

    return orgs, org_cats, missing_cat_groups


if __name__ == '__main__':
    log_stream_handler = logging.StreamHandler()
    log_file_handler = logging.FileHandler('logs.log')
    logging.basicConfig(handlers=(log_stream_handler, log_file_handler),
                        level=logging.INFO,
                        format="%(asctime)s:%(levelname)s:%(message)s")

    # with crunchbase_tar() as tar:
    #     names = tar.getnames()
    # print(names)
    # assert 'category_groups.csv' in names

    # with crunchbase_tar() as tar:
    #     cg_df = pd.read_csv(tar.extractfile('category_groups.csv'))
    # print(cg_df.columns)
