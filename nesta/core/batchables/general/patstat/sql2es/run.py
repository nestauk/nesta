"""
run.py (patstat)
----------------

Transfer pre-collected PATSTAT data from MySQL
to Elasticsearch. Only patents since the year 2000 are considered.
The patents are grouped by patent families.
"""

from ast import literal_eval
import boto3
import json
import logging
import os

from nesta.core.luigihacks.elasticsearchplus import ElasticsearchPlus
from nesta.core.luigihacks.luigi_logging import set_log_level
from nesta.core.orms.orm_utils import db_session, get_mysql_engine
from nesta.core.orms.orm_utils import load_json_from_pathstub
from nesta.core.orms.orm_utils import object_to_dict
from nesta.core.orms.patstat_orm import ApplnFamilyAll
from nesta.core.orms.patstat_2019_05_13 import *
from nesta.packages.geo_utils.lookup import get_eu_countries


def select_text(objs, lang_field, text_field):
    """Select the longest English-language text field from
    a family of PATSTAT applications. In the case where there
    are no English-language objects, the longest other text
    field is returned.

    Args:
        objs (list of dict): Group of PATSTAT objects of the same appl family.
                             Objects may be, for example, application titles
                             or application abstracts objects.
        lang_field (str): Name of the field indicating the written language
                          of each object.
        text_field (str): Name of the field indicating the text data
                          of the objects.
    Returns:
        text_data (str): The selected exemplar of text data
                         for all of these objects.
    """
    if len(objs) == 0:
        return None
    # Filter English language objects
    _objs = [t for t in objs if t[lang_field] == 'en']
    # If no English language objects, use all objects
    if len(_objs) == 0:
        _objs = objs
    # Select the object with the longest passage of text
    obj = sorted(_objs, key=lambda x: len(x[text_field]), reverse=True)[0]
    return obj[text_field]


def select_metadata(orm, session, appln_ids, field_selector=None):
    """Extract the PATSTAT metadata for these application IDs.

    Args:
        orm (SqlAlchemy selectable): Table to extract this metadata from.
        session (SqlAlchemy connectable): Session for querying the database.
        appln_ids (list): List of application IDs to extract metadata for.
        field_selector (SqlAlchemy column field): The ORM's appl ID field.
    Returns:
        objs (list): List of all metadata objects for these application IDs.
    """
    if field_selector is None:
        field_selector = orm.appln_id
    _filter = field_selector.in_(appln_ids)
    return [object_to_dict(_obj) for _obj in
            session.query(orm).filter(_filter).all()]


def extract_nuts_by_lvl(persons):
    nuts_by_lvl = {lvl: [p['nuts'] for p in persons
                         if p['nuts'] is not None
                         and p['nuts_level'] == lvl]
                   for lvl in range(0, 4)}
    # Back-fill any missing nuts levels, noting that these
    # will be deduplicated after
    for lvl in reversed(range(1, 4)):
        nuts_by_lvl[lvl-1] += [nuts[:-1] for nuts in nuts_by_lvl[lvl]]
    # Deduplicate and return as dict ready for ingestion
    return {f'nuts{lvl}': sorted(set(nuts)) 
            for lvl, nuts in nuts_by_level}


def reformat_row(row, _engine):
    """Aggregate and merge a PATSTAT application family with metadata.

    Args:
        row (dict): A single row representing a PATSTAT application family.
        _engine (SqlAlchemy engine): Engine connecting to our local PATSTAT db.
    Returns:
        row (dict): The input, enriched with metadata, and reformatted,
                    ready for ingestion to Elasticsearch.
    """
    eu_countries = get_eu_countries()  # Note: lru_cached

    # Retrieve metadata for this application family
    appln_ids = row.pop('appln_id')  # All application IDs for this patent
    with db_session(_engine) as _session:
        _titles = select_metadata(Tls202ApplnTitle, _session, appln_ids)
        _abstrs = select_metadata(Tls203ApplnAbstr, _session, appln_ids)
        ipcs = select_metadata(Tls209ApplnIpc, _session, appln_ids)
        nace2s = select_metadata(Tls229ApplnNace2, _session, appln_ids)
        techs = select_metadata(Tls230ApplnTechnField, _session, appln_ids)
        # Get persons
        _pers_applns = select_metadata(Tls207PersAppln, _session, appln_ids)
        pers_ids = set(pa['person_id'] for pa in _pers_applns)
        persons = select_metadata(Tls906Person, _session, pers_ids,
                                  field_selector=Tls906Person.person_id)

    # Extract text fields
    title = select_text(_titles, 'appln_title_lg', 'appln_title')
    abstr = select_text(_abstrs, 'appln_abstract_lg', 'appln_abstract')

    # Get names from lookups
    ipcs = sorted(set(i['ipc_class_symbol'].split()[0] for i in ipcs))
    nace2s = sorted(set(n['nace2_code'] for n in nace2s))
    techs = sorted(set(t['techn_field_nr'] for t in techs))
    ctrys = sorted(set(p['person_ctry_code'] for p in persons))
    is_eu = any(c in eu_countries for c in ctrys)
    nuts_by_level = extract_nuts_by_lvl(persons)

    # Index the data
    row = dict(title=title, abstract=abstr, ipc=ipcs, nace2=nace2s,
               tech=techs, ctry=ctrys, is_eu=is_eu, **row, 
               **nuts_by_level)

    return row


def run():
    # Extract arguments from the environment
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

    # Database(s) setup
    logging.info('Retrieving engine connection')
    engine = get_mysql_engine("BATCHPAR_config", "mysqldb",
                              db_name)
    _engine = get_mysql_engine("BATCHPAR_config", "readonly",
                               "patstat_2019_05_13")

    # ES setup
    logging.info('Connecting to ES')
    strans_kwargs = {'filename': 'patstat.json', 'ignore': ['id']}
    es = ElasticsearchPlus(hosts=es_host,
                           port=es_port,
                           aws_auth_region=aws_auth_region,
                           no_commit=("AWSBATCHTEST" in
                                      os.environ),
                           entity_type=entity_type,
                           strans_kwargs=strans_kwargs,
                           auto_translate=True,
                           auto_translate_kwargs={'min_len': 20},
                           null_empty_str=True,
                           coordinates_as_floats=True,
                           do_sort=True,
                           ngram_fields=['textBody_abstract_patent'])

    # Collect file
    logging.info('Retrieving patent family ids')
    nrows = 20 if test else None
    s3 = boto3.resource('s3')
    obj = s3.Object(bucket, batch_file)
    docdb_fam_ids = json.loads(obj.get()['Body']._raw_stream.read())
    logging.info(f"{len(docdb_fam_ids)} patent family IDs "
                 "retrieved from s3")

    # Process rows
    logging.info('Processing rows')
    _filter = ApplnFamilyAll.docdb_family_id.in_(docdb_fam_ids)
    with db_session(engine) as session:
        for obj in session.query(ApplnFamilyAll).filter(_filter).all():
            row = object_to_dict(obj)
            row = reformat_row(row, _engine)
            uid = row.pop('docdb_family_id')
            _row = es.index(index=es_index, doc_type=es_type,
                            id=uid, body=row)
    logging.info("Batch job complete.")


if __name__ == "__main__":
    set_log_level()
    run()
