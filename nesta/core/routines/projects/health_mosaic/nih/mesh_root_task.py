import luigi
import datetime
import logging
from nesta.core.luigihacks.misctools import find_filepath_from_pathstub as f3p

from nesta.core.routines.nih.nih_data.mesh_join_task import MeshJoinTask

class RootTask(luigi.WrapperTask):
    '''A dummy root task, which collects the database configurations
    and executes the central task.

    Args:
        date (datetime): Date used to label the outputs
        db_config_env (str): Environment variable that points to the path to 
            the MySQL database configuration
        production (bool): Flag indicating whether running in testing
                           mode (False, default), or production mode (True).
    '''

    date = luigi.DateParameter(default=datetime.date.today())
    db_config_env = luigi.Parameter(default='MYSQLDB')
    production = luigi.BoolParameter(default=False)
    
    def requires(self):
        _routine_id  = f"{self.date}-{self.production}"
        
        logging.getLogger().setLevel(logging.INFO)
        yield MeshJoinTask(date=self.date,
                _routine_id=_routine_id,
                db_config_env=self.db_config_env,
                test=(not self.production),
                )
