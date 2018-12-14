'''
Crunchbase data collection and processing
==================================

Luigi routine to collect Crunchbase data exports and load the data into MySQL.
'''

import luigi
import datetime
import logging

from crunchbase_org_collect_task import OrgCollectTask


class RootTask(luigi.WrapperTask):
    '''A dummy root task, which collects the database configurations
    and executes the central task.

    Args:
        date (datetime): Date used to label the outputs
        db_config_path (str): Path to the MySQL database configuration
        production (bool): Flag indicating whether running in testing
                           mode (False, default), or production mode (True).
    '''
    date = luigi.DateParameter(default=datetime.date.today())
    db_config_env = luigi.Parameter(default="MYSQLDB")
    production = luigi.BoolParameter(default=False)
    insert_batch_size = luigi.IntParameter(default=1000)

    def requires(self):
        '''Collects the database configurations and executes the central task.'''
        _routine_id = "{}-{}".format(self.date, self.production)

        logging.getLogger().setLevel(logging.INFO)
        yield OrgCollectTask(date=self.date,
                             _routine_id=_routine_id,
                             db_config_env=self.db_config_env,
                             test=(not self.production),
                             insert_batch_size=self.insert_batch_size)
