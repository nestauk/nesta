"""
[AutoML] Topic modelling (CorEx)
================================

Automated topic modelling of arXiv articles via the CorEx
algorithm. See :obj:`topic_process_task_chain.json`
for the full processing chain, but in brief:
Vectorization is performed, followed by n-gramming
(a lookup via Wiktionary) and then topics via CorEx.
"""

import luigi
import os
import datetime
import json
import logging

from sqlalchemy import or_
from nesta.core.luigihacks import s3
from nesta.core.orms.arxiv_orm import article_categories as ArtCat
from nesta.core.orms.arxiv_orm import Article
from nesta.core.orms.arxiv_orm import CorExTopic
from nesta.core.orms.arxiv_orm import ArticleTopic
from nesta.core.orms.arxiv_orm import Base
from nesta.core.luigihacks.automl import AutoMLTask
from nesta.core.orms.orm_utils import get_mysql_engine, db_session
from nesta.core.orms.orm_utils import insert_data

from nesta.core.luigihacks import misctools
from nesta.core.luigihacks.mysqldb import MySqlTarget
from nesta.core.luigihacks.parameter import DictParameterPlus
from nesta.core.routines.arxiv.arxiv_grid_task import GridTask

THIS_PATH = os.path.dirname(os.path.realpath(__file__))
CHAIN_PARAMETER_PATH = os.path.join(THIS_PATH,
                                    "topic_process_task_chain.json")

class PrepareArxivS3Data(luigi.Task):
    """Task that pipes SQL text fields to a number of S3 JSON files.
    This is particularly useful for preparing autoML tasks.
    """
    s3_path_out = luigi.Parameter()
    db_conf_env = luigi.Parameter(default="MYSQLDB")
    chunksize = luigi.IntParameter(default=100000)
    test = luigi.BoolParameter(default=True)
    grid_task_kwargs = DictParameterPlus()

    def requires(self):
        return GridTask(**self.grid_task_kwargs)

    def output(self):
        return s3.S3Target(f"{self.s3_path_out}/"
                           f"data.{self.test}.length")

    def write_to_s3(self, data, ichunk):
        f = s3.S3Target(f"{self.s3_path_out}/data."
                        f"{ichunk}-{self.test}.json").open("wb")
        f.write(json.dumps(data).encode('utf-8'))
        f.close()
        return [], ichunk+1

    def run(self):
        database = 'dev' if self.test else 'production'
        engine = get_mysql_engine(self.db_conf_env, 'mysqldb', database)
        with db_session(engine) as session:
            # Make the query
            result = (session
                      .query(Article.id, Article.abstract)
                      .filter(Article.article_source == 'arxiv')
                      .join(ArtCat)
                      .filter(or_(ArtCat.c.category_id.like("cs.%"),
                                  ArtCat.c.category_id == "stat.ML")))
            # Buffer the data in
            data, ichunk = [], 0
            for i, (uid, abstract) in enumerate(result.yield_per(self.chunksize)):
                data.append({'id': uid, 'body': abstract})
                if len(data) == self.chunksize:
                    data, ichunk = self.write_to_s3(data, ichunk)
        # Final flush
        if len(data) > 0:
            self.write_to_s3(data, ichunk)
        # Write the output length as well, for book-keeping
        f = self.output().open("wb")
        f.write(str(i).encode("utf-8"))
        f.close()

class WriteTopicTask(luigi.Task):
    s3_path_prefix = luigi.Parameter()
    raw_s3_path_prefix = luigi.Parameter()
    data_path = luigi.Parameter()
    date = luigi.DateParameter()
    db_config_path = luigi.Parameter('mysqldb.config')
    db_conf_env = luigi.Parameter(default="MYSQLDB")
    test = luigi.BoolParameter()
    insert_batch_size = luigi.IntParameter(default=10000)
    cherry_picked = luigi.Parameter(default=None)
    grid_task_kwargs = DictParameterPlus()

    def output(self):
        '''Points to the output database engine'''
        db_config = misctools.get_config(self.db_config_path,
                                         "mysqldb")
        db_config["database"] = 'dev' if self.test else 'production'
        db_config["table"] = "arXlive topics <dummy>"  # Note, not a real table
        update_id = "ArxivTopicTask_{}_{}".format(self.date, self.test)
        return MySqlTarget(update_id=update_id, **db_config)


    def requires(self):
        return AutoMLTask(s3_path_prefix=self.s3_path_prefix,
                          task_chain_filepath=CHAIN_PARAMETER_PATH,
                          test=self.test,
                          input_task=PrepareArxivS3Data,
                          input_task_kwargs={'s3_path_out':self.data_path,
                                             'test':self.test,
                                             'grid_task_kwargs':self.grid_task_kwargs})


    def run(self):
        # Load the input data (note the input contains the path
        # to the output)
        _filename = self.cherry_picked
        if _filename is None:
            _body = self.input().open("rb")
            _filename = _body.read().decode('utf-8')
        obj = s3.S3Target(f"{self.raw_s3_path_prefix}/"
                          f"{_filename}").open('rb')
        data = json.load(obj)

        # Get DB connections and settings
        database = 'dev' if self.test else 'production'
        engine = get_mysql_engine(self.db_conf_env, 'mysqldb',
                                  database)
        ArticleTopic.__table__.drop(engine)
        CorExTopic.__table__.drop(engine)

        # Insert the topic names data
        topics = [{'id':int(topic_name.split('_')[-1])+1,
                   'terms':terms}
                  for topic_name, terms in
                  data['data']['topic_names'].items()]
        insert_data(self.db_conf_env, 'mysqldb', database,
                    Base, CorExTopic, topics, low_memory=True)
        logging.info(f'Inserted {len(topics)} topics')

        # Insert article topic weight data
        topic_articles = []
        done_ids = set()
        for row in data['data']['rows']:
            article_id = row.pop('id')
            if article_id in done_ids:
                continue
            done_ids.add(article_id)
            topic_articles += [{'topic_id': int(topic_name.split('_')[-1])+1,
                                'topic_weight': weight, 'article_id': article_id}
                               for topic_name, weight in row.items()]
            # Flush
            if len(topic_articles) > self.insert_batch_size:
                insert_data(self.db_conf_env, 'mysqldb', database,
                            Base, ArticleTopic, topic_articles,
                            low_memory=True)
                topic_articles = []

        # Final flush
        if len(topic_articles) > 0:
            insert_data(self.db_conf_env, 'mysqldb', database,
                        Base, ArticleTopic, topic_articles,
                        low_memory=True)

        # Touch the output
        self.output().touch()
