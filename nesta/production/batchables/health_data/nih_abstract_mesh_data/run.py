from ast import literal_eval
from elasticsearch.exceptions import NotFoundError
import logging
import os
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import NoResultFound

from nesta.production.luigihacks.elasticsearchplus import ElasticsearchPlus
from nesta.packages.health_data.process_mesh import retrieve_mesh_terms
from nesta.packages.health_data.process_mesh import format_mesh_terms
from nesta.packages.health_data.process_mesh import retrieve_duplicate_map
from nesta.packages.health_data.process_mesh import format_duplicate_map
from nesta.production.orms.orm_utils import get_mysql_engine
from nesta.production.orms.orm_utils import load_json_from_pathstub

from nesta.production.orms.nih_orm import Abstracts

def clean_abstract(abstract):
    '''Removes multiple spaces, tabs and newlines.

    Args:
        abstract (str): text to be cleaned

    Returns
        (str): cleaned text
    '''
    abstract = abstract.replace('\t', ' ')
    abstract = abstract.replace('\n', ' ')
    while '  ' in abstract:
        abstract = abstract.replace('  ', ' ')
    abstract.strip()

    return abstract


def run():
    bucket = os.environ["BATCHPAR_s3_bucket"]
    abstract_file = os.environ["BATCHPAR_s3_key"]
    dupe_file = os.environ["BATCHPAR_dupe_file"]
    es_config = literal_eval(os.environ["BATCHPAR_outinfo"])
    db = os.environ["BATCHPAR_db"]
    entity_type = os.environ["BATCHPAR_entity_type"]

    # mysql setup
    engine = get_mysql_engine("BATCHPAR_config", "mysqldb", db)
    Session = sessionmaker(bind=engine)
    session = Session()

    # retrieve a batch of meshed terms
    mesh_terms = retrieve_mesh_terms(bucket, abstract_file)
    mesh_terms = format_mesh_terms(mesh_terms)
    logging.info(f'batch {abstract_file} contains '
                 f'{len(mesh_terms)} meshed abstracts')

    # retrieve duplicate map
    dupes = retrieve_duplicate_map(bucket, dupe_file)
    dupes = format_duplicate_map(dupes)
    
    # Get all dupe IDs
    all_dupes = []
    for _, dupe_ids in dupes.items():
        all_dupes += dupe_ids
    all_dupes = set(all_dupes)

    docs = []
    for doc_id, terms in mesh_terms.items():
        try:
            _filter = Abstracts.application_id == doc_id
            abstract = (session.query(Abstracts)
                        .filter(_filter).one())
        except NoResultFound:
            logging.warning(f'Not found {doc_id} in database')
            raise NoResultFound(doc_id)
        clean_abstract_text = clean_abstract(abstract.abstract_text)
        docs.append({'doc_id': doc_id,
                     'mesh_terms': terms,
                     'abstract_text': clean_abstract_text
                     })
        duped_docs = dupes.get(doc_id, [])
        logging.info(f'Found {len(duped_docs)} duplicates')
        for duped_doc in duped_docs:
            docs.append({'doc_id': duped_doc,
                         'mesh_terms': terms,
                         'abstract_text': clean_abstract_text,
                         'duplicate_abstract': True
                         })

    # output to elasticsearch
    field_null_mapping = load_json_from_pathstub("tier_1/"
                                                 "field_null_mappings/",
                                                 "health_scanner.json")
    strans_kwargs={'filename':'nih.json',
                   'from_key':'tier_0',
                   'to_key':'tier_1',
                   'ignore':['doc_id']}
    es = ElasticsearchPlus(hosts=es_config['host'],
                           port=es_config['port'],
                           use_ssl=True,
                           entity_type=entity_type,
                           strans_kwargs=strans_kwargs,
                           field_null_mapping=field_null_mapping,
                           null_empty_str=True,
                           coordinates_as_floats=True,
                           country_detection=True,
                           listify_terms=True)

    logging.warning(f'Writing {len(docs)} documents to elasticsearch')
    for doc in docs:
        # Deduplicate records
        uid = doc.pop("doc_id")
        if uid in all_dupes:
            logging.debug(f"Deleting: {uid}")
            es.delete(es_config['index'],
                      doc_type=es_config['type'],
                      id=uid)
            continue
        # Extract existing info
        try:
            existing = es.get(es_config['index'], 
                              doc_type=es_config['type'], 
                              id=uid)['_source']
        except NotFoundError:
            logging.warning(f"Missing project for abstract: {uid}")
        else:
            # Merge existing info into new doc
            doc = {**existing, **doc}
            es.index(index=es_config['index'], 
                     doc_type=es_config['type'], id=uid, body=doc)


if __name__ == '__main__':
    log_level = logging.INFO
    if "outinfo" not in os.environ:
        logging.getLogger('boto3').setLevel(logging.CRITICAL)
        logging.getLogger('botocore').setLevel(logging.CRITICAL)
        logging.getLogger('s3transfer').setLevel(logging.CRITICAL)
        logging.getLogger('urllib3').setLevel(logging.CRITICAL)
        log_level = logging.DEBUG
        pars = {"s3_key":("nih_abstracts_processed/22-07-2019/"
                          "nih_abstracts_9638504-9926622.out.txt"),
                "outinfo":("{'host': 'https://search-health-scanner"
                           "-5cs7g52446h7qscocqmiky5dn4.eu-west"
                           "-2.es.amazonaws.com', 'port': '443',"
                           "'index': 'nih_v4', 'type': '_doc', "
                           "'region': 'eu-west-2'}"),
                "dupe_file":("nih_abstracts/24-05-19/"
                             "duplicate_mapping.json"),
                "db":"production",
                "config":(f"{os.environ['HOME']}"
                          "/nesta/nesta/production"
                          "/config/mysqldb.config"),
                "s3_bucket":"innovation-mapping-general",
                "entity_type":"paper"}
        for k, v in pars.items():
            os.environ[f'BATCHPAR_{k}'] = v

    log_stream_handler = logging.StreamHandler()
    logging.basicConfig(handlers=[log_stream_handler, ],
                level=log_level,
                format="%(asctime)s:%(levelname)s:%(message)s")
    run()
