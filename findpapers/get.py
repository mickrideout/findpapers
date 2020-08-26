import os
import datetime
import logging
from typing import Optional, List
from findpapers.models.search import Search
import findpapers.searcher.scopus_searcher as scopus_searcher
import findpapers.searcher.ieee_searcher as ieee_searcher

logger = logging.getLogger(__name__)


def get(query: str, since: Optional[datetime.date] = None, until: Optional[datetime.date] = None,
        limit: Optional[int] = None, scopus_api_token: Optional[str] = None, ieee_api_token: Optional[str] = None) -> Search:

    search = Search(query, since, until, limit)

    if ieee_api_token is None:
        ieee_api_token = os.getenv('IEEE_API_TOKEN')
    
    if not search.has_reached_its_limit() and ieee_api_token is not None:
        logger.info('Fetching papers from IEEE library...')
        try:
            ieee_searcher.run(search, ieee_api_token)
        except Exception: # pragma: no cover
            logger.error('Error while fetching papers from IEEE library')

    if scopus_api_token is None:
        scopus_api_token = os.getenv('SCOPUS_API_TOKEN')
    
    if scopus_api_token is not None:
        logger.info('Fetching papers from Scopus library...')
        try:
            scopus_searcher.run(search, scopus_api_token)
            scopus_searcher.enrich_publication_data(search, scopus_api_token)
        except Exception: # pragma: no cover
            logger.error('Error while fetching papers from Scopus library')

    return search
