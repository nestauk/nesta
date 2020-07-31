"""
run.py (general.crunchbase.sql2es)
==================================

Pipe curated Crunchbase data from MySQL to Elasticsearch.
"""

from nesta.core.luigihacks.elasticsearchplus import ElasticsearchPlus
from nesta.core.orms.orm_utils import db_session, get_mysql_engine
from nesta.core.orms.orm_utils import obj_to_dict
from nesta.core.orms.general_orm import CrunchbaseOrg

from ast import literal_eval
import boto3
import json
import logging
import os


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

    # es setup
    es = ElasticsearchPlus(hosts=es_host,
                           port=es_port,
                           aws_auth_region=aws_auth_region,
                           no_commit=("AWSBATCHTEST" in os.environ),
                           entity_type=entity_type,
                           strans_kwargs={'filename': 'companies.json'})

    # collect file
    s3 = boto3.resource('s3')
    obj = s3.Object(bucket, batch_file)
    org_ids = json.loads(obj.get()['Body']._raw_stream.read())
    org_ids = org_ids[:20 if test else None]
    logging.info(f"{len(org_ids)} organisations retrieved from s3")

    # Pipe orgs to ES
    query = session.query(CrunchbaseOrg).filter(CrunchbaseOrg.id.in_(org_ids))
    with db_session(engine) as session:
        for row in query.all():
            row = obj_to_dict(row)
            _row = es.index(index=es_index, doc_type=es_type,
                            id=row.pop('id'), body=row)
    logging.info("Batch job complete.")


if __name__ == "__main__":
    log_stream_handler = logging.StreamHandler()
    logging.basicConfig(handlers=[log_stream_handler, ],
                        level=logging.INFO,
                        format="%(asctime)s:%(levelname)s:%(message)s")

    if 'BATCHPAR_outinfo' not in os.environ:
        from nesta.core.orms.orm_utils import setup_es
        es, es_config = setup_es(production=False, endpoint='health-scanner',
                                 dataset='companies',
                                 drop_and_recreate=True)

        environ = {"AWSBATCHTEST": "",
                   'BATCHPAR_batch_file': 'crunchbase_to_es-15597291977144725.json', 
                   'BATCHPAR_config': ('/home/ec2-user/nesta/nesta/'
                                       'core/config/mysqldb.config'),
                   'BATCHPAR_db_name': 'production', 
                   'BATCHPAR_bucket': 'nesta-production-intermediate', 
                   'BATCHPAR_done': "False", 
                   'BATCHPAR_outinfo': ('https://search-health-scanner-'
                               '5cs7g52446h7qscocqmiky5dn4.'
                               'eu-west-2.es.amazonaws.com'), 
                   'BATCHPAR_out_port': '443', 
                   'BATCHPAR_out_index': 'companies_v1', 
                   'BATCHPAR_out_type': '_doc', 
                   'BATCHPAR_aws_auth_region': 'eu-west-2', 
                   'BATCHPAR_entity_type': 'company', 
                   'BATCHPAR_test': "False"}
        for k, v in environ.items():
            os.environ[k] = v
    run()
