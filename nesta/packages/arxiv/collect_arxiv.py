import datetime
import json
import logging
import pandas as pd
import requests
import s3fs
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import NoResultFound
import time
import xml.etree.ElementTree as ET


from nesta.production.orms.orm_utils import get_mysql_engine, try_until_allowed
from nesta.production.orms.arxiv_orm import Base, Categories

OAI = "{http://www.openarchives.org/OAI/2.0/}"
ARXIV = "{http://arxiv.org/OAI/arXiv/}"
DELAY = 10  # seconds between requests
API_URL = 'http://export.arxiv.org/oai2'


def load_arxiv_categories(db_config, db, bucket, cat_file):
    target = f's3://{bucket}/{cat_file}'
    categories = pd.read_csv(target)

    # Setup the database connectors
    engine = get_mysql_engine(db_config, "mysqldb", db)
    try_until_allowed(Base.metadata.create_all, engine)
    Session = try_until_allowed(sessionmaker, engine)
    session = try_until_allowed(Session)

    logging.info(f'found {session.query(Categories).count()} existing categories')
    for idx, data in categories.iterrows():
        try:
            session.query(Categories).filter(Categories.id == data['id']).one()
        except NoResultFound:
            session.add(Categories(id=data['id'], description=data['description']))
            logging.info(f"adding {data['id']} to database")
    session.commit()
    session.close()


def _arxiv_request(url, delay=DELAY, **kwargs):
    """Make a request and convert the result to xml elements.

    Args:
        url (str): endpoint of the api
        delay (int): time to wait after request in seconds
        kwargs (dict): any other arguments to pass as paramaters in the request

    Returns:
        (:obj:`xml.etree.ElementTree.Element`): converted response
    """
    params = dict(verb='ListRecords', **kwargs)
    r = requests.get(url, params=params)
    xml = r.text
    time.sleep(delay)
    return ET.fromstring(xml)


def total_articles():
    """Make a request to the API and capture the total number of articles from the
    resumptionToken tag.

    Returns:
        (int): total number of articles
    """
    root = _arxiv_request(API_URL, metadataPrefix='arXiv')
    token = root.find(OAI+'ListRecords').find(OAI+"resumptionToken")
    list_size = token.attrib['completeListSize']
    return int(list_size)


def request_token():
    """Make a request to the API and capture the resumptionToken which will be used to
    page through results. Not efficient as it also returns the first page of data which
    is slow and not required.

    Returns:
        (str): supplied resumtionToken
    """
    root = _arxiv_request(API_URL, metadataPrefix='arXiv')
    token = root.find(OAI+'ListRecords').find(OAI+"resumptionToken")
    resumption_token = token.text.split("|")[0]
    logging.info(f"resumptionToken: {resumption_token}")
    return resumption_token


def xml_to_json(element, tag, prefix=''):
    """Converts a layer of xml to a json string. Handles multiple instances of the
    specified tag and any schema prefix which they may have.

    Args:
        element (:obj:`xml.etree.ElementTree.Element`): xml element containing the data
        tag (str): target tag
        prefix (str): schema prefix on the name of the tag

    Returns:
        (str): json of the original object with the supplied tag as the key and a list of all
               instances of this tag as the value.
    """
    tag = ''.join([prefix, tag])

    all_data = [{field.tag[len(prefix):]: field.text
                for field in fields.getiterator()
                if field.tag != tag}
                for fields in element.getiterator(tag)]
    return json.dumps(all_data)


def arxiv_batch(token, cursor):
    """Retrieves a batch of data from the arXiv api (expect 1000).

    Args:
        token (str): resumptionToken issued from a prevous request
        cursor (int): record to start from

    Returns:
        (:obj:`list` of :obj:`dict`): retrieved records
    """
    resumption_token = '|'.join([token, str(cursor)])
    root = _arxiv_request(API_URL, resumptionToken=resumption_token)
    records = root.find(OAI+'ListRecords')
    output = []

    for record in records.findall(OAI+"record"):
        header = record.find(OAI+'header')
        header_id = header.find(OAI+'identifier').text
        row = dict(datestamp=header.find(OAI+'datestamp').text)
        logging.info(f"article {header_id} datestamp: {row['datestamp']}")

        # collect all fields from the metadata section
        meta = record.find(OAI+'metadata')
        if meta is None:
            logging.warning(f"No metadata for article {header_id}")
            continue
        info = meta.find(ARXIV+'arXiv')
        fields = ['id', 'created', 'updated', 'title', 'categories',
                  'journal-ref', 'doi', 'msc-class', 'abstract']
        for field in fields:
            try:
                row[field.replace('-', '_')] = info.find(ARXIV+field).text
            except AttributeError:
                logging.info(f"{field} not found in article {header_id}")

        for date_field in ['datestamp', 'created', 'updated']:
            try:
                date = row[date_field]
                row[date_field] = datetime.datetime.strptime(date, '%Y-%m-%d').date()
            except ValueError:
                # date is not in the correct format
                del row[date_field]
            except KeyError:
                # field not in this row
                pass

        try:
            row['categories'] = row['categories'].split(' ')
        except KeyError:
                # field not in this row
                pass

        row['title'] = row['title'].strip()
        row['authors'] = xml_to_json(info, 'author', prefix=ARXIV)

        output.append(row)

    # extract cursor for next batch
    token = root.find(OAI+'ListRecords').find(OAI+"resumptionToken")
    if token.text is not None:
        resumption_cursor = int(token.text.split("|")[1])
        logging.info(f"resumptionCursor: {resumption_cursor}")
    else:
        resumption_cursor = None
        logging.info("End of data")

    return output, resumption_cursor


if __name__ == '__main__':

    log_stream_handler = logging.StreamHandler()
    logging.basicConfig(handlers=[log_stream_handler, ],
                        level=logging.INFO,
                        format="%(asctime)s:%(levelname)s:%(message)s")

    token = request_token()
    import pdb; pdb.set_trace()
    pass
    # batch = arxiv_batch(token, 1001)
    # with open('arxiv_batch.json', mode='w') as f:
    #     json.dump(batch, f)

    # bucket = 'innovation-mapping-general'
    # cat_file = 'arxiv_classification/arxiv_subject_classifications.csv'
    # cats = load_arxiv_categories('MYSQLDB', 'dev', bucket, cat_file)
