'''
NIH data collection and processing
==================================

Luigi routine to collect NIH World RePORTER data
via the World ExPORTER data dump. The routine
transfers the data into the MySQL database before
processing and indexing the data to ElasticSearch.
'''

import boto3
import datetime
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import NotFoundError
import logging
import luigi
import re

from nesta.production.orms.orm_utils import setup_es
from nesta.production.routines.health_data.nih_data.nih_process_task import ProcessTask
from nesta.production.luigihacks import autobatch, misctools
from nesta.production.luigihacks.mysqldb import MySqlTarget
from nesta.production.luigihacks.misctools import find_filepath_from_pathstub


class AbstractsMeshTask(autobatch.AutoBatchTask):
    ''' Collects and combines Mesh terms from S3, Abstracts from MYSQL 
    and projects in Elasticsearch.

    Args:
        date (str): Date used to label the outputs
        _routine_id (str): String used to label the AWS task
        db_config_path (str): Path to the MySQL database configuration
    '''
    date = luigi.DateParameter()
    _routine_id = luigi.Parameter()
    db_config_path = luigi.Parameter()
    drop_and_recreate = luigi.BoolParameter(default=False)
    ignore_missing = luigi.BoolParameter(default=False)

    def requires(self):
        '''Collects the configurations and executes the previous task.'''
        logging.getLogger().setLevel(logging.INFO)
        yield ProcessTask(date=self.date,
                          drop_and_recreate=self.drop_and_recreate,
                          _routine_id=self._routine_id,
                          db_config_path=self.db_config_path,
                          batchable=find_filepath_from_pathstub("batchables/health_data/nih_process_data"),
                          env_files=[find_filepath_from_pathstub("nesta/nesta/"),
                                     find_filepath_from_pathstub("config/mysqldb.config"),
                                     find_filepath_from_pathstub("config/elasticsearch.config"),
                                     find_filepath_from_pathstub("nih.json")],
                          job_def=self.job_def,
                          job_name="ProcessTask-%s" % self._routine_id,
                          job_queue=self.job_queue,
                          region_name=self.region_name,
                          poll_time=10,
                          test=self.test,
                          memory=2048,
                          max_live_jobs=2)


    def output(self):
        '''Points to the input database target'''
        update_id = "NihAbstractMeshData-%s" % self._routine_id
        db_config = misctools.get_config("mysqldb.config", "mysqldb")
        db_config["database"] = "production" if not self.test else "dev"
        db_config["table"] = "NIH abstracts mesh DUMMY"  # Note, not a real table
        return MySqlTarget(update_id=update_id, **db_config)

    @staticmethod
    def get_abstract_file_keys(bucket, key_prefix):
        '''Retrieves keys to meshed files from s3.

        Args:
            bucket (str): s3 bucket
            key_prefix (str): prefix to identify the files, ie 
                              the folder and start of a filename

        Returns:
            (set of str): keys of the files
        '''
        s3 = boto3.resource('s3')
        s3bucket = s3.Bucket(bucket)
        return {o.key for o in s3bucket.objects.filter(Prefix=key_prefix)}


    def done_check(self, es_client, index, doc_type, key):
        '''
        Checks elasticsearch for mesh terms in the first and last documents in the
        batch.

        Args:
            es_client (object): instantiated elasticsearch client
            index (str): name of the index
            doc_type (str): name of the document type
            key (str): filepath in s3

        Returns:
            (bool): True if both are already existing, otherwise False
        '''
        pattern = r'(\d+)-(\d+)\.txt$'
        match = re.search(pattern, key)
        if match.groups() is None:
            raise ValueError("Could not extract start and end doc_ids from meshed file")

        for idx in match.groups():
            try:
                res = es_client.get(index=index, doc_type=doc_type, id=idx)
            except NotFoundError:
                if self.ignore_missing:
                    return False
                logging.warning(f"{idx} not found")
                raise NotFoundError
            if res['_source'].get('terms_mesh_abstract') is None:
                return False
        return True

    def prepare(self):
        # mysql setup
        db = 'production' if not self.test else 'dev'

        # elasticsearch setup
        es_mode = 'dev' if self.test else 'prod'
        es, es_config = setup_es(es_mode, self.test, self.drop_and_recreate,
                                 dataset='nih',
                                 aliases='health_scanner')

        # s3 setup and file key collection
        bucket = 'innovation-mapping-general'
        key_prefix = 'nih_abstracts_processed/08-11-18/mti'
        keys = self.get_abstract_file_keys(bucket, key_prefix)
        logging.info(f"Found keys: {keys}")

        job_params = []
        for key in keys:
            params = {'s3_key': key,
                      's3_bucket': bucket,
                      'dupe_file': "nih_abstracts/24-05-19/duplicate_mapping.json",
                      'config': "mysqldb.config",
                      'db': db,
                      'outinfo': es_config,
                      'done': self.done_check(es, index=es_config['index'],
                                              doc_type=es_config['type'],
                                              key=key),
                      'entity_type': 'paper'
                      }
            logging.info(params)
            job_params.append(params)
        return job_params

    def combine(self, job_params):
        self.output().touch()


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    date = datetime.date(year=2018, month=12, day=25)
    process = AbstractsMeshTask(test=True, batchable='', job_def='', job_name='',
            job_queue='', region_name='', db_config_path='MYSQLDB', date=date,
            _routine_id='')
    process.prepare()
