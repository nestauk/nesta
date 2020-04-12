"""
run.py (cordis_eu)
----------------------

Transfer pre-collected cordis data from MySQL
to Elasticsearch.
"""

from ast import literal_eval
import boto3
import json
import logging
import os
from datetime import datetime as dt

from nesta.core.luigihacks.elasticsearchplus import ElasticsearchPlus
from nesta.core.luigihacks.luigi_logging import set_log_level
from nesta.core.orms.orm_utils import db_session, get_mysql_engine
from nesta.core.orms.orm_utils import load_json_from_pathstub
from nesta.core.orms.orm_utils import object_to_dict
from nesta.core.orms.cordis_orm import Project

def validate_date(row, label):
    key = f'{label}_date_code'
    year = None
    try:
        year = dt.strptime(row[key], '%Y-%m-%dT00:00:00').year
    except ValueError:
        row[key] = None
    else:
        row[key] = row[key][0:10]
    finally:
        return year

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
    logging.info('Retrieving engine connection')
    engine = get_mysql_engine("BATCHPAR_config", "mysqldb",
                              db_name)
    
    # es setup
    logging.info('Connecting to ES')
    strans_kwargs={'filename':'eurito/cordis-eu.json',
                   'from_key':'tier_0', 'to_key':'tier_1',
                   'ignore':['id']}
    es = ElasticsearchPlus(hosts=es_host,
                           port=es_port,
                           aws_auth_region=aws_auth_region,
                           no_commit=("AWSBATCHTEST" in
                                      os.environ),
                           entity_type=entity_type,
                           strans_kwargs=strans_kwargs,
                           null_empty_str=True,
                           coordinates_as_floats=True,
                           listify_terms=True,
                           do_sort=False,
                           ngram_fields=['textBody_description_project'])

    # collect file
    logging.info('Retrieving project ids')
    nrows = 20 if test else None
    s3 = boto3.resource('s3')
    obj = s3.Object(bucket, batch_file)
    project_ids = json.loads(obj.get()['Body']._raw_stream.read())
    logging.info(f"{len(project_ids)} project IDs "
                 "retrieved from s3")

    #
    logging.info('Processing rows')
    with db_session(engine) as session:
        for count, obj in enumerate((session.query(Project)
                                     .filter(Project.rcn.in_(project_ids))
                                     .all())):
            row = object_to_dict(obj)
            
            # Extract year from date
            start_year = validate_date(row, 'start')
            end_year = validate_date(row, 'end')
            row['year'] = start_year if start_year is not None else end_year
            
            
            _desc = row.pop('project_description')
            _obj = row.pop('objective')
            row['description'] = f'Description:\n{_desc}\n\nObjective:\n{_obj}'
            row['link'] = f'https://cordis.europa.eu/project/id/{row["rcn"]}'

            uid = row.pop('rcn')
            _row = es.index(index=es_index, doc_type=es_type,
                            id=uid, body=row)
            if not count % 1000:
                logging.info(f"{count} rows loaded to "
                             "elasticsearch")

    logging.warning("Batch job complete.")


if __name__ == "__main__":
    set_log_level()
    if 'BATCHPAR_outinfo' not in os.environ:
        from nesta.core.orms.orm_utils import setup_es
        es, es_config = setup_es('dev', True, True,
                                 dataset='cordis-eu')
        environ = {'config': ('/home/ec2-user/nesta-cordis2es/nesta/'
                              'core/config/mysqldb.config'),
                   'batch_file' : ('cordis-eu_EURITO-ElasticsearchTask-2020-04-10-True-15865345336407135.json'),
                   'db_name': 'dev',
                   'bucket': 'nesta-production-intermediate',
                   'done': "False",
                   'outinfo': ('https://search-eurito-dev-'
                               'vq22tw6otqjpdh47u75bh2g7ba.'
                               'eu-west-2.es.amazonaws.com'),
                   'out_port': '443',
                   'out_index': 'cordis_dev',
                   'out_type': '_doc',
                   'aws_auth_region': 'eu-west-2',
                   'entity_type': 'project',
                   'test': "True"}
        for k, v in environ.items():
            os.environ[f'BATCHPAR_{k}'] = v

    logging.info('Starting...')
    run()
