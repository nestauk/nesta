from nesta.core.luigihacks.elasticsearchplus import ElasticsearchPlus

from ast import literal_eval
import boto3
import json
import logging
import os
import pandas as pd
import requests
from collections import defaultdict

from nesta.packages.crunchbase.utils import parse_investor_names

from nesta.core.orms.orm_utils import db_session, get_mysql_engine
from nesta.core.orms.orm_utils import load_json_from_pathstub
from nesta.core.orms.crunchbase_orm import Organization
from nesta.core.orms.crunchbase_orm import OrganizationCategory
from nesta.core.orms.crunchbase_orm import CategoryGroup
from nesta.core.orms.crunchbase_orm import FundingRound
from nesta.core.orms.geographic_orm import Geographic
from nesta.packages.geo_utils.lookup import get_eu_countries


def run():
    test = literal_eval(os.environ["BATCHPAR_test"])
    bucket = os.environ['BATCHPAR_bucket']
    batch_file = os.environ['BATCHPAR_batch_file']

    db_name = os.environ["BATCHPAR_db_name"]
    es_host = os.environ['BATCHPAR_outinfo']
    es_port = int(os.environ['BATCHPAR_out_port'])
    es_index = os.environ['BATCHPAR_out_index']
    es_type = os.environ['BATCHPAR_out_type']
    entity_type = os.environ["BATCHPAR_entity_type"]
    aws_auth_region = os.environ["BATCHPAR_aws_auth_region"]

    # database setup
    engine = get_mysql_engine("BATCHPAR_config", "mysqldb", db_name)
    static_engine = get_mysql_engine("BATCHPAR_config", "mysqldb", "static_data")
    states_lookup = {row['state_code']: row['state_name']
                     for _, row in  pd.read_sql_table('us_states_lookup',
                                                      static_engine).iterrows()}
    states_lookup["AE"] = "Armed Forces (Canada, Europe, Middle East)"
    states_lookup["AA"] = "Armed Forces (Americas)"
    states_lookup["AP"] = "Armed Forces (Pacific)"
    states_lookup[None] = None  # default lookup for non-US countries

    # Get continent lookup
    url = "https://nesta-open-data.s3.eu-west-2.amazonaws.com/rwjf-viz/continent_codes_names.json"
    continent_lookup = {row["Code"]: row["Name"] for row in requests.get(url).json()}
    continent_lookup[None] = None

    eu_countries = get_eu_countries()

    # es setup
    strans_kwargs={'filename':'eurito/crunchbase-eu.json',
                   'from_key':'tier_0',
                   'to_key':'tier_1',
                   'ignore':['id']}
    es = ElasticsearchPlus(hosts=es_host,
                           port=es_port,
                           aws_auth_region=aws_auth_region,
                           no_commit=("AWSBATCHTEST" in os.environ),
                           entity_type=entity_type,
                           strans_kwargs=strans_kwargs,
                           null_empty_str=True,
                           coordinates_as_floats=True,
                           country_detection=True,
                           listify_terms=True,
                           terms_delimiters=("|",),
                           null_pairs={"currency_of_funding": "cost_of_funding"},
                           ngram_fields=['textBody_summary_organisation',
                                         'textBody_descriptive_organisation'])

    # collect file
    nrows = 20 if test else None

    s3 = boto3.resource('s3')
    obj = s3.Object(bucket, batch_file)
    org_ids = json.loads(obj.get()['Body']._raw_stream.read())
    logging.info(f"{len(org_ids)} organisations retrieved from s3")

    org_fields = set(c.name for c in Organization.__table__.columns)

    geo_fields = ['country_alpha_2', 'country_alpha_3', 'country_numeric',
                  'continent', 'latitude', 'longitude']

    # First get all funders
    investor_names = defaultdict(list)
    with db_session(engine) as session:
        rows = (session
                .query(Organization, FundingRound)
                .join(FundingRound, Organization.id==FundingRound.company_id)
                .filter(Organization.id.in_(org_ids))
                .all())
        for row in rows:
            _id = row.Organization.id
            _investor_names = row.FundingRound.investor_names
            investor_names[_id] += parse_investor_names(_investor_names)

    # Pipe orgs to ES
    with db_session(engine) as session:
        rows = (session
                .query(Organization, Geographic)
                .join(Geographic, Organization.location_id==Geographic.id)
                .filter(Organization.id.in_(org_ids))
                .limit(nrows)
                .all())
        for count, row in enumerate(rows, 1):
            # convert sqlalchemy to dictionary
            row_combined = {k: v for k, v in row.Organization.__dict__.items()
                            if k in org_fields}
            row_combined['currency_of_funding'] = 'USD'  # all values are from 'funding_total_usd'
            row_combined.update({k: v for k, v in row.Geographic.__dict__.items()
                                 if k in geo_fields})
            row_combined['investor_names'] = list(set(investor_names[row_combined['id']]))
            row_combined['is_eu'] = row_combined['country_alpha_2'] in eu_countries

            # reformat coordinates
            row_combined['coordinates'] = {'lat': row_combined.pop('latitude'),
                                           'lon': row_combined.pop('longitude')}

            # iterate through categories and groups
            row_combined['category_list'] = []
            row_combined['category_group_list'] = []
            for category in (session.query(CategoryGroup)
                             .select_from(OrganizationCategory)
                             .join(CategoryGroup)
                             .filter(OrganizationCategory.organization_id==row.Organization.id)
                             .all()):
                row_combined['category_list'].append(category.category_name)
                row_combined['category_group_list'] += [group for group
                                                        in str(category.category_group_list).split('|')
                                                        if group is not 'None']

            # Add a field for US state name
            state_code = row_combined['state_code']
            row_combined['placeName_state_organisation'] = states_lookup[state_code]
            continent_code = row_combined['continent']
            row_combined['placeName_continent_organisation'] = continent_lookup[continent_code]
            row_combined['updated_at'] = row_combined['updated_at'].strftime('%Y-%m-%d')
            
            uid = row_combined.pop('id')
            _row = es.index(index=es_index, doc_type=es_type,
                            id=uid, body=row_combined)
            if not count % 1000:
                logging.info(f"{count} rows loaded to elasticsearch")
    
    logging.warning("Batch job complete.")


if __name__ == "__main__":
    log_stream_handler = logging.StreamHandler()
    logging.basicConfig(handlers=[log_stream_handler, ],
                        level=logging.INFO,
                        format="%(asctime)s:%(levelname)s:%(message)s")
    run()
