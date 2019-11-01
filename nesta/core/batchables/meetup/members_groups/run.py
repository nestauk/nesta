"""
run.py (members_groups)
=======================

Batchable for expanding from members to groups.
"""

import logging
from nesta.packages.meetup.members_groups import get_member_details
from nesta.packages.meetup.members_groups import get_member_groups
from nesta.core.orms.orm_utils import insert_data
from nesta.core.orms.meetup_orm import Base
from nesta.core.orms.meetup_orm import GroupMember
from sqlalchemy import and_
from sqlalchemy.orm import sessionmaker
import boto3
from urllib.parse import urlsplit
import os
from ast import literal_eval
from sqlalchemy.exc import IntegrityError
from nesta.core.luigihacks.s3 import parse_s3_path


def run():
    logging.getLogger().setLevel(logging.INFO)

    # Fetch the input parameters
    member_ids = literal_eval(os.environ["BATCHPAR_member_ids"])
    s3_path = os.environ["BATCHPAR_outinfo"]
    db = os.environ["BATCHPAR_db"]

    # Generate the groups for these members
    output = []
    for member_id in member_ids:
        response = get_member_details(member_id, max_results=200)
        output += get_member_groups(response)
    logging.info("Got %s groups", len(output))

    # Load connection to the db, and create the tables
    objs = insert_data("BATCHPAR_config", "mysqldb", db,
                       Base, GroupMember, output)
    logging.info("Inserted %s groups", len(objs))

    # Mark the task as done
    s3 = boto3.resource('s3')
    s3_obj = s3.Object(*parse_s3_path(s3_path))
    s3_obj.put(Body="")

    return len(objs)

if __name__ == "__main__":
    run()
