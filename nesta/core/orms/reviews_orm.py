#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Oct  9 15:07:36 2019

@author: jdjumalieva
"""

'''
Employee Reviews ORM
===========

'''

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.mysql import VARCHAR, BIGINT, TEXT
from sqlalchemy.types import JSON, INT, DATE
from sqlalchemy import Column, ForeignKey
from sqlalchemy.orm import relationship

Base = declarative_base()


class RawReviews(Base):
    """Main table with the data on 100K employee reviews"""
    __tablename__ = 'reviews_raw_reviews'

    id = Column(VARCHAR(50), primary_key=True, index=True)
    job_title = Column(VARCHAR(200))
    review_date = Column(DATE)
    overall_rating = Column(BIGINT)
    review_text = Column(TEXT)
#    name = Column(VARCHAR(200, collation='utf8mb4_unicode_ci'))
#    domain = Column(TEXT)
#    funding_rounds = Column(INT)
#    funding_total_usd = Column(BIGINT)
#    founded_on = Column(DATE)
#    last_funding_on = Column(DATE)
#    closed_on = Column(DATE)
#    email = Column(VARCHAR(200, collation='utf8mb4_unicode_ci'))
#    long_description = Column(TEXT(collation='utf8mb4_unicode_ci'))
#    is_health = Column(BOOLEAN)
#    mesh_terms = Column(TEXT)


class Factors(Base):
    """Table to link terms describing job satisfaction factors to original
    review ids"""
    __tablename__ = 'reviews_factors'

    id = Column(INT, primary_key=True)
    factor_name = Column(VARCHAR(200))
       

class FactorsInText(Base):
    """Table to link terms describing job satisfaction factors to original
    review ids"""
    __tablename__ = 'reviews_factors_in_text'

    factor_id = Column(VARCHAR(50), ForeignKey('reviews_factors.id'), 
                   primary_key=True)
    review_id = Column(VARCHAR(50), ForeignKey('reviews_raw_reviews.id'), 
                   primary_key=True)
    reviews = relationship('RawReviews')