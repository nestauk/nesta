"""
run.py (general.nih)
--------------------

Transfer pre-curated NiH data from MySQL
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
from nesta.core.orms.orm_utils import object_to_dict
from nesta.core.orms.general_orm import NihProject as Project


def datetime_to_date(row):
    """Strip null time info from datetime and return as a date
    
    Args:
        row (dict): Row object optionally containing
                    'project_start' and 'project_end' dict keys
    Returns:
        rows (dict): Modified row, with null time info from 
                     datetime and return as a date.
    """
    for key in ['project_start', 'project_end']:
        if row[key] is None:
            continue
        date = dt.strptime(row[key], '%Y-%m-%dT00:00:00')        
        row[key] = dt.strftime(date, '%Y-%m-%d')
    return row


def reformat_row(row):
    """Reformat MySQL data ready for parsing to Elasticsearch"""
    # Apply datetime --> date conversion on row
    row = datetime_to_date(row)
    # Also apply datetime --> date conversion on subfields in yearly_funds
    for _row in row['yearly_funds']:
        _row = datetime_to_date(_row)
    return row


def run():
    """The 'main' function"""
    # Extract env vars for this task
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

    # Database setup
    engine = get_mysql_engine("BATCHPAR_config", "mysqldb", db_name)

    # es setup
    logging.info('Connecting to ES')
    es = ElasticsearchPlus(hosts=es_host,
                           port=es_port,
                           aws_auth_region=aws_auth_region,
                           no_commit=("AWSBATCHTEST" in os.environ),
                           entity_type=entity_type,
                           strans_kwargs={'filename': 'nih.json'},
                           null_empty_str=True,
                           do_sort=False)

    # collect file
    logging.info('Retrieving article ids')
    s3 = boto3.resource('s3')
    obj = s3.Object(bucket, batch_file)
    proj_ids = json.loads(obj.get()['Body']._raw_stream.read())
    logging.info(f"{len(proj_ids)} project IDs retrieved from s3")

    # Iterate over articles
    logging.info('Processing rows')
    with db_session(engine) as sess:
        _filter = Project.application_id.in_(proj_ids)
        query = sess.query(Project).filter(_filter)
        for obj in query.all():
            row = object_to_dict(obj)
            row = reformat_row(row)
            es.index(index=es_index, doc_type=es_type,
                     id=row.pop('application_id'), body=row)
    logging.info("Batch job complete.")


if __name__ == "__main__":
    set_log_level()
    logging.info('Starting...')
    run()
