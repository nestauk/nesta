"""
arXiv vectors
==============

Tasks for converting arXiv abstracts to vectors via BERT in batches.
"""

from nesta.core.luigihacks.luigi_logging import set_log_level
from nesta.core.luigihacks.sql2batchtask import Sql2BatchTask
from nesta.core.luigihacks.misctools import f3p
from nesta.core.luigihacks.misctools import load_batch_config
from nesta.core.luigihacks.mysqldb import make_mysql_target
from nesta.core.orms.arxiv_orm import Article

import luigi
from datetime import datetime as dt


class ArxivVectorTask(luigi.Task):
    process_batch_size = luigi.IntParameter(default=5000)
    production = luigi.BoolParameter(default=False)
    date = luigi.DateParameter(default=dt.now())

    def output(self):
        return make_mysql_target(self)

    def requires(self):
        set_log_level(not self.production)
        kwargs = load_batch_config(self)
        return Sql2BatchTask(id_field=Article.id,
                             batchable=f3p('batchables/nlp/bert_vectorize'),
                             process_batch_size=self.process_batch_size,
                             **kwargs)

    def run(self):
        self.output().touch()
