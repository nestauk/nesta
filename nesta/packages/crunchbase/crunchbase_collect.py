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


def get_files_from_tar(files):
    """Converts csv files in the crunchbase tar into dataframes and returns them.

    Args:
        files (list): names of the files to extract (without .csv suffix)

    Returns:
        (:obj:`list` of :obj:`pandas.Dataframe`): the extracted files as dataframes
    """
    dfs = []
    with crunchbase_tar() as tar:
        for filename in files:
            dfs.append(pd.read_csv(tar.extractfile(''.join([filename, '.csv'])),
                                   low_memory=False))
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
        (:obj:`pandas.Dataframe`): processed organization data
        (:obj:`pandas.Dataframe`): generated organization_category data
    """
    # fix uuid column names
    orgs = rename_uuid_columns(orgs)

    # lookup country name and add as a column
    orgs['country'] = orgs['country_code'].apply(country_iso_code_to_name)
    orgs = orgs.drop('country_code', axis=1)  # now redundant with country_alpha_3 appended

    orgs['location_id'] = None
    cat_groups = cat_groups.set_index(['category_name'])
    org_cats = pd.DataFrame(columns=['organization_id', 'category_id'])
    org_descriptions = org_descriptions.set_index(['uuid'])
    orgs['long_description'] = None

    for idx, row in orgs.iterrows():
        # generate composite key for location lookup
        try:
            comp_key = generate_composite_key(row.city, row.country)
        except ValueError:
            pass
        else:
            orgs.at[idx, 'location_id'] = comp_key

        # generate link table data for organization categories
        row_org_cats = []
        for cat in row.category_list.split(','):
            try:
                row_org_cats.append({'organization_id': row.id,
                                     'category_id': cat_groups.loc[cat].id})
            except KeyError:
                logging.warning(f"Category {cat} not found in categories table")
        org_cats = org_cats.append(row_org_cats, ignore_index=True)

        # append long descriptions to organizations
        try:
            orgs.at[idx, 'long_description'] = org_descriptions.loc[row.id].description
        except KeyError:
            logging.warning(f"Long description for {row.id} not found")

    # remove redundant category columns
    orgs = orgs.drop(['category_list', 'category_group_list'], axis=1)

    return orgs, org_cats


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





