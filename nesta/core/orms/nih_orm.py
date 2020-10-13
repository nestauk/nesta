'''
NIH schema
==============

The schema for the World RePORTER data.
'''

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.mysql import VARCHAR as _VARCHAR
from sqlalchemy.dialects.mysql import TEXT as _TEXT
from sqlalchemy.types import INTEGER, JSON, DATETIME
from sqlalchemy import Column, Table


Base = declarative_base()
TEXT = _TEXT(collation='utf8mb4_unicode_ci')
VARCHAR = lambda *args, **kwargs: _VARCHAR(*args, 
                                           collation='utf8mb4_unicode_ci', 
                                           **kwargs)


class Projects(Base):
    __tablename__ = 'nih_projects'

    application_id = Column(INTEGER, primary_key=True)
    activity = Column(VARCHAR(3))
    administering_ic = Column(VARCHAR(2))
    application_type = Column(INTEGER)
    arra_funded = Column(VARCHAR(1))
    award_notice_date = Column(DATETIME)
    budget_start = Column(DATETIME)
    budget_end = Column(DATETIME)
    cfda_code = Column(TEXT)
    core_project_num = Column(VARCHAR(50), index=True)
    ed_inst_type = Column(TEXT)
    foa_number = Column(TEXT)
    full_project_num = Column(VARCHAR(50), index=True)
    funding_ics = Column(JSON)
    funding_mechanism = Column(TEXT)
    fy = Column(INTEGER, index=True)
    ic_name = Column(VARCHAR(100), index=True)
    org_city = Column(VARCHAR(50), index=True)
    org_country = Column(VARCHAR(50), index=True)
    org_dept = Column(VARCHAR(100), index=True)
    org_district = Column(INTEGER)
    org_duns = Column(JSON)
    org_fips = Column(VARCHAR(2), index=True)
    org_ipf_code = Column(INTEGER)
    org_name = Column(VARCHAR(92), index=True)
    org_state = Column(VARCHAR(2), index=True)
    org_zipcode = Column(VARCHAR(10))
    phr = Column(TEXT)
    pi_ids = Column(JSON)
    pi_names = Column(JSON)
    program_officer_name = Column(TEXT)
    project_start = Column(DATETIME)
    project_end = Column(DATETIME)
    project_terms = Column(JSON)
    project_title = Column(TEXT)
    serial_number = Column(VARCHAR(6))
    study_section = Column(VARCHAR(4))
    study_section_name = Column(TEXT)
    suffix = Column(VARCHAR(6))
    support_year = Column(VARCHAR(2))
    direct_cost_amt = Column(INTEGER)
    indirect_cost_amt = Column(INTEGER)
    total_cost = Column(INTEGER)
    subproject_id = Column(INTEGER)
    total_cost_sub_project = Column(INTEGER)
    nih_spending_cats = Column(JSON)


class Abstracts(Base):
    __tablename__ = 'nih_abstracts'

    application_id = Column(INTEGER, primary_key=True)
    abstract_text = Column(TEXT)


class Publications(Base):
    __tablename__ = 'nih_publications'

    pmid = Column(INTEGER, primary_key=True)
    author_name = Column(TEXT)
    affiliation = Column(TEXT)
    author_list = Column(JSON)
    country = Column(VARCHAR(50), index=True)
    issn = Column(VARCHAR(9))
    journal_issue = Column(VARCHAR(75))
    journal_title = Column(VARCHAR(400), index=True)
    journal_title_abbr = Column(VARCHAR(200))
    journal_volume = Column(VARCHAR(100))
    lang = Column(VARCHAR(3))
    page_number = Column(VARCHAR(200))
    pub_date = Column(DATETIME)
    pub_title = Column(VARCHAR(400), index=True)
    pub_year = Column(INTEGER, index=True)
    pmc_id = Column(INTEGER, index=True)

     
class Patents(Base):
    __tablename__ = 'nih_patents'
    
    patent_id = Column(VARCHAR(20), primary_key=True)
    patent_title = Column(TEXT)
    project_id = Column(VARCHAR(50), index=True)
    patent_org_name = Column(TEXT)


class LinkTables(Base):
    __tablename__ = 'nih_linktables'

    pmid = Column(INTEGER, primary_key=True)
    project_number = Column(VARCHAR(50), index=True)


class ClinicalStudies(Base):
    __tablename__ = "nih_clinicalstudies"
    
    clinicaltrials_govid = Column(VARCHAR(20), primary_key=True)
    core_project_number = Column(VARCHAR(50), index=True)
    study = Column(TEXT)
    study_status = Column(VARCHAR(30), index=True)
