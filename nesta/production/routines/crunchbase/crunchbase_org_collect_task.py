"""
Crunchbase data collection and processing
==================================

Luigi routine to collect Crunchbase data exports and load the data into MySQL.
"""

import luigi
import logging
import os

from nesta.packages.crunchbase.crunchbase_collect import get_files_from_tar, process_orgs, rename_uuid_columns
from nesta.production.luigihacks.misctools import get_config
from nesta.production.luigihacks.mysqldb import MySqlTarget
from nesta.production.orms.crunchbase_orm import Base, CategoryGroup, Organization, OrganizationCategory
from nesta.production.orms.orm_utils import get_mysql_engine, try_until_allowed, insert_data, db_session


class OrgCollectTask(luigi.Task):
    """Download tar file of Organization csvs and load them into the MySQL server.

    Args:
        _routine_id (str): String used to label the AWS task
        db_config_path: (str) The output database configuration
    """
    date = luigi.DateParameter()
    _routine_id = luigi.Parameter()
    db_config_env = luigi.Parameter()
    test = luigi.BoolParameter(default=True)
    database = 'production' if not test else 'dev'
    insert_batch_size = luigi.IntParameter(default=1000)

    @staticmethod
    def _total_records(data_dict, append_to=None):
        """Calculates totals for a dictionary of records and appends a grand total.

        Args:
            data_dict (dict): data with description as the key, and list of dicts as the
                value
            append_to (dict): a previously returned dict from this function, will add
                the values for batch operation

        Returns:
            (dict): labels as per the provided data_dict, with totals as the values.
                `total` is appended with a sum of all values, plus `batch_total` if
                append_to is provided
        """
        totals = {}
        total = 0
        for k, v in data_dict.items():
            length = len(v)
            totals[k] = length
            total += length
        totals['total'] = total

        if append_to is not None:
            for k, v in totals.items():
                totals[k] += append_to[k]
        totals['batch_total'] = total

        return totals

    @staticmethod
    def _split_batches(data, batch_size):
        """Breaks batches down into chunks consumable by the database.

        Args:
            data (:obj:`list` of :obj:`dict`): list of rows of data
            batch_size (int): number of rows per batch

        Returns:
            (:obj:`list` of :obj:`dict`): yields a batch at a time
        """
        if len(data) <= batch_size:
            yield data
        else:
            batch = []
            for row in data:
                batch.append(row)
                if len(batch) == batch_size:
                    yield batch
                    batch.clear()
            if len(batch) > 0:
                yield batch

    def _insert_data(self, table, data, batch_size=1000):
        """Writes out a dataframe to MySQL and checks totals are equal, or raises error.

        Args:
            table (:obj:`sqlalchemy.mapping`): table where the data should be written
            data (:obj:`list` of :obj:`dict`): data to be written
            batch_size (int): size of bulk inserts into the db
        """
        total_rows_in = len(data)
        logging.info(f"Inserting {total_rows_in} rows of data into {table.__tablename__}")

        totals = None
        for batch in self._split_batches(data, batch_size):
            returned = {}
            returned['inserted'], returned['existing'], returned['failed'] = insert_data(
                                                            self.db_config_env, 'mysqldb',
                                                            self.database,
                                                            Base, table, batch,
                                                            return_non_inserted=True)
            totals = self._total_records(returned, totals)
            for k, v in totals.items():
                logging.info(f"{k} rows: {v}")
            logging.info("--------------")
            if totals['batch_total'] != len(batch):
                raise ValueError(f"Inserted {table} data is not equal to original: {len(batch)}")

        if totals['total'] != total_rows_in:
            raise ValueError(f"Inserted {table} data is not equal to original: {total_rows_in}")

    def output(self):
        """Points to the output database engine"""
        self.db_config_path = os.environ[self.db_config_env]
        db_config = get_config(self.db_config_path, "mysqldb")
        db_config["database"] = self.database
        db_config["table"] = "Crunchbase <dummy>"  # Note, not a real table
        update_id = "CrunchbaseCollectOrgData_{}".format(self.date)
        return MySqlTarget(update_id=update_id, **db_config)

    def run(self):
        """Collect and process organizations, categories and long descriptions."""

        # database setup
        self.engine = get_mysql_engine(self.db_config_env, 'mysqldb', self.database)
        try_until_allowed(Base.metadata.create_all, self.engine)

        # collect files
        cat_groups, orgs, org_descriptions = get_files_from_tar(['category_groups',
                                                                 'organizations',
                                                                 'organization_descriptions'
                                                                 ],
                                                                test=self.test)
        # process category_groups
        cat_groups = rename_uuid_columns(cat_groups)
        cat_groups_rows = cat_groups.to_dict(orient='records')
        self._insert_data(CategoryGroup, cat_groups_rows)

        # process organizations and categories
        processed_orgs, org_cats, missing_cat_groups = process_orgs(orgs, cat_groups, org_descriptions)
        self._insert_data(CategoryGroup, missing_cat_groups)
        self._insert_data(Organization, processed_orgs, self.insert_batch_size)

        # link table needs to be inserted via non-bulk method to enforce relationship
        org_cats = [OrganizationCategory(**org_cat) for org_cat in org_cats]
        with db_session(self.engine) as session:
            session.add_all(org_cats)

        # mark as done
        self.output().touch()
