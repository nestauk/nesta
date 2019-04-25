"""
arXiv data collection and processing
====================================

Luigi routine to query the Microsoft Academic Graph for additional data and append it to
the exiting data in the database.
"""
from datetime import date
import luigi
import logging
import pprint

from arxiv_iterative_date_task import QueryMagTask
from nesta.packages.arxiv.collect_arxiv import BatchWriter, BatchedTitles, update_existing_articles, query_dedupe_sparql, extract_entity_id
from nesta.packages.mag.query_mag import build_expr, query_mag_api, dedupe_entities, update_field_of_study_ids
from nesta.production.orms.arxiv_orm import Base, Article
from nesta.production.orms.mag_orm import FieldOfStudy
from nesta.production.orms.orm_utils import get_mysql_engine, db_session
from nesta.production.luigihacks import misctools
from nesta.production.luigihacks.mysqldb import MySqlTarget


class MagSparqlTask(luigi.Task):
    """Query the MAG for additional data to append to the arxiv articles,
       primarily the fields of study.

    Args:
        date (datetime): Datetime used to label the outputs
        _routine_id (str): String used to label the AWS task
        db_config_env (str): environmental variable pointing to the db config file
        db_config_path (str): The output database configuration
        mag_config_path (str): Microsoft Academic Graph Api key configuration path
        insert_batch_size (int): number of records to insert into the database at once
                                 (not used in this task but passed down to others)
        articles_from_date (str): new and updated articles from this date will be
                                  retrieved. Must be in YYYY-MM-DD format
                                  (not used in this task but passed down to others)
    """
    date = luigi.DateParameter()
    _routine_id = luigi.Parameter()
    test = luigi.BoolParameter(default=True)
    db_config_env = luigi.Parameter()
    db_config_path = luigi.Parameter()
    mag_config_path = luigi.Parameter()
    insert_batch_size = luigi.IntParameter(default=500)
    articles_from_date = luigi.Parameter()

    def output(self):
        '''Points to the output database engine'''
        db_config = misctools.get_config(self.db_config_path, "mysqldb")
        db_config["database"] = 'dev' if self.test else 'production'
        db_config["table"] = "arXlive <dummy>"  # Note, not a real table
        update_id = "ArxivQueryMag_{}".format(self.date)
        return MySqlTarget(update_id=update_id, **db_config)

    def requires(self):
        yield QueryMagTask(date=self.date,
                           _routine_id=self._routine_id,
                           db_config_path=self.db_config_path,
                           db_config_env=self.db_config_env,
                           test=self.test,
                           articles_from_date=self.articles_from_date,
                           insert_batch_size=self.insert_batch_size)

    def run(self):
        # pp = pprint.PrettyPrinter(indent=4, width=100)

        # database setup
        database = 'dev' if self.test else 'production'
        logging.warning(f"Using {database} database")
        self.engine = get_mysql_engine(self.db_config_env, 'mysqldb', database)
        Base.metadata.create_all(self.engine)

        with db_session(self.engine) as session:
            # mag_config = misctools.get_config(self.mag_config_path, 'mag')
            # mag_subscription_key = mag_config['subscription_key']

            field_mapping = {'paper': 'mag_id',
                             'paperTitle': 'title',
                             'fieldsOfStudy': 'fields_of_study',
                             'citationCount': 'citation_count'}

            logging.info("Querying database for articles without fields of study")

            articles_to_process = [dict(id=a.id, doi=a.doi, title=a.title) for a in
                                   (session
                                   .query(Article)
                                   .filter(~Article.fields_of_study.any() & Article.doi.isnot(None))
                                   .all())]
            total_arxiv_ids_to_process = len(articles_to_process)
            logging.info(f"{total_arxiv_ids_to_process} articles to process")

            all_articles_to_update = BatchWriter(self.insert_batch_size,
                                                 update_existing_articles,
                                                 session)

            batch_field_of_study_ids = set()

            for count, row in enumerate(query_dedupe_sparql(articles_to_process),
                                        start=1):

                # renaming and reformatting
                for code, description in field_mapping.items():
                    try:
                        row[description] = row.pop(code)
                    except KeyError:
                        pass

                if row.get('citation_count', None) is not None:
                    row['citation_count_updated'] = date.today()

                # reformat fos_ids out of entity urls
                try:
                    row['fields_of_study'] = {extract_entity_id(f) for f in row.pop('fields_of_study')}
                    fos = row.pop('fields_of_study')
                    row['fields_of_study'] = {extract_entity_id(f) for f in fos.split(',')}
                except KeyError:
                    row['fields_of_study'] = []
                batch_field_of_study_ids.update(row['fields_of_study'])

                # reformat mag_id out of entity url
                row['mag_id'] = extract_entity_id(row['mag_id'])

                # drop unnecessary fields
                for f in ['score', 'title']:
                    del row[f]

                # check fields of study are in database
                logging.debug('Checking fields of study exist in db')
                found_fos_ids = {fos.id for fos in (session
                                                    .query(FieldOfStudy)
                                                    .filter(FieldOfStudy.id.in_(row['fields_of_study']))
                                                    .all())}

                missing_fos_ids = row['fields_of_study'] - found_fos_ids
                if missing_fos_ids:
                    #  query mag for details if not found
                    update_field_of_study_ids(missing_fos_ids)

                # add this row to the queue
                all_articles_to_update.extend(row)

                logging.info(f"Batch {count} done. {total_arxiv_ids_to_process} articles left to process")
                if self.test and count == 2:
                    logging.warning("Exiting after 2 rows in test mode")
                    break

            # pick up any left over in the batch
            if all_articles_to_update:
                all_articles_to_update.write()

        # mark as done
        logging.warning("Task complete")
        self.output().touch()
