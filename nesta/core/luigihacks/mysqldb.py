# Adapted from:

# -*- coding: utf-8 -*-
#
# Copyright 2012-2015 Spotify AB
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

'''
NOTE: overwhelmingly based on this2_, where the following documentation
has been directly lifted. The main difference to the latter, is that
:code:`**cnx_kwargs` in the constructor can accept `port` as a key.

.. _this2: https://luigi.readthedocs.io/en/stable/api/luigi.contrib.mysqldb.html
'''

import logging

import luigi

logger = logging.getLogger('luigi-interface')

try:
    import mysql.connector
    from mysql.connector import errorcode
except ImportError as e:
    logger.warning("Loading MySQL module without the python package mysql-connector-python. \
        This will crash at runtime if MySQL functionality is used.")


def make_mysql_target(luigi_task):
    config = load_yaml_from_pathstub('config/luigi-batch.yaml')
    test = luigi_task.test if 'test' in luigi_task.__dict__ else luigi_task.production
    task_name = type(luigi_task).__name__
    routine_id = f'{task_name}-{luigi_task.date}-{test}'
    config['test'] = test
    config['job_name'] = routine_id
    config['routine_id'] = routine_id
    config['env_files'] += additional_env_files
    config['env_files'] = [f3p(fp) for fp in config['env_files']]
    return config

    
class MySqlTarget(luigi.Target):
    """
    Target for a resource in MySql.
    """

    marker_table = luigi.configuration.get_config().get('mysql', 'marker-table', 'table_updates')

    def __init__(self, host, database, user, password, table, update_id, **cnx_kwargs):
        """
        Initializes a MySqlTarget instance.

        :param host: MySql server address. Possibly a host:port string.
        :type host: str
        :param database: database name.
        :type database: str
        :param user: database user
        :type user: str
        :param password: password for specified user.
        :type password: str
        :param update_id: an identifier for this data set.
        :type update_id: str
        :param cnx_kwargs: optional params for mysql connector constructor.
            See https://dev.mysql.com/doc/connector-python/en/connector-python-connectargs.html.
        """
        if ':' in host:
            self.host, self.port = host.split(':')
            self.port = int(self.port)
        else:
            self.host = host
            self.port = 3306
        self.database = database
        self.user = user
        self.password = password
        self.table = table
        self.update_id = update_id

        # This is Joel's contribution
        if 'port' in cnx_kwargs:
            cnx_kwargs.pop('port')
        self.cnx_kwargs = cnx_kwargs

    def touch(self, connection=None):
        """
        Mark this update as complete.

        IMPORTANT, If the marker table doesn't exist,
        the connection transaction will be aborted and the connection reset.
        Then the marker table will be created.
        """
        self.create_marker_table()

        if connection is None:
            connection = self.connect()
            connection.autocommit = True  # if connection created here, we commit it here

        connection.cursor().execute(
            """INSERT INTO {marker_table} (update_id, target_table)
               VALUES (%s, %s)
               ON DUPLICATE KEY UPDATE
               update_id = VALUES(update_id)
            """.format(marker_table=self.marker_table),
            (self.update_id, self.table)
        )
        # make sure update is properly marked
        assert self.exists(connection)

    def exists(self, connection=None):
        if connection is None:
            connection = self.connect()
            connection.autocommit = True
        cursor = connection.cursor()
        try:
            cursor.execute("""SELECT 1 FROM {marker_table}
                WHERE update_id = %s
                LIMIT 1""".format(marker_table=self.marker_table),
                           (self.update_id,)
                           )
            row = cursor.fetchone()
        except mysql.connector.Error as e:
            if e.errno == errorcode.ER_NO_SUCH_TABLE:
                row = None
            else:
                raise
        return row is not None

    def connect(self, autocommit=False):
        connection = mysql.connector.connect(user=self.user,
                                             password=self.password,
                                             host=self.host,
                                             port=self.port,
                                             database=self.database,
                                             autocommit=autocommit,
                                             **self.cnx_kwargs)
        return connection

    def create_marker_table(self):
        """
        Create marker table if it doesn't exist.

        Using a separate connection since the transaction might have to be reset.
        """
        connection = self.connect(autocommit=True)
        cursor = connection.cursor()
        try:
            cursor.execute(
                """ CREATE TABLE {marker_table} (
                        id            BIGINT(20)    NOT NULL AUTO_INCREMENT,
                        update_id     VARCHAR(128)  NOT NULL,
                        target_table  VARCHAR(128),
                        inserted      TIMESTAMP DEFAULT NOW(),
                        PRIMARY KEY (update_id),
                        KEY id (id)
                    )
                """
                .format(marker_table=self.marker_table)
            )
        except mysql.connector.Error as e:
            if e.errno == errorcode.ER_TABLE_EXISTS_ERROR:
                pass
            else:
                raise
        connection.close()
