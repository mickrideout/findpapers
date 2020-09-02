import requests
import datetime
import logging
import re
import math
import xmltodict
from lxml import html
from typing import Optional
from fake_useragent import UserAgent
import findpapers.utils.common_util as util
from findpapers.models.search import Search
from findpapers.models.paper import Paper
from findpapers.models.publication import Publication

DATABASE_LABEL = 'PubMed'
BASE_URL = 'https://eutils.ncbi.nlm.nih.gov'
MAX_ENTRIES_PER_PAGE = 50

SESSION = requests.Session()


def _get_search_url(search: Search, start_record: Optional[int] = 0) -> str:
    """
    This method return the URL to be used to retrieve data from PubMed database
    See https://www.ncbi.nlm.nih.gov/books/NBK25500/ for query tips

    Parameters
    ----------
    search : Search
        A search instance
    start_record : str, optional
        Sequence number of first record to fetch, by default 0

    Returns
    -------
    str
        a URL to be used to retrieve data from PubMed database
    """

    url = f'{BASE_URL}/entrez/eutils/esearch.fcgi?db=pubmed&term={search.query} AND has abstract [FILT] AND "journal article"[Publication Type]'

    if search.since is not None or search.until is not None:
        since = datetime.date(
            1, 1, 1) if search.since is None else search.since
        until = datetime.date.today() if search.until is None else search.until

        url += f' AND {since.strftime("%Y/%m/%d")}:{until.strftime("%Y/%m/%d")}[Date - Publication]'

    if start_record is not None:
        url += f'&retstart={start_record}'

    url += f'&retmax={MAX_ENTRIES_PER_PAGE}'

    return url


def _get_api_result(search: Search, start_record: Optional[int] = 0) -> dict:  # pragma: no cover
    """
    This method return results from PubMed database using the provided search parameters

    Parameters
    ----------
    search : Search
        A search instance
    start_record : str, optional
        Sequence number of first record to fetch, by default 0

    Returns
    -------
    dict
        a result from PubMed database
    """

    url = _get_search_url(search, start_record)

    headers = {'User-Agent': str(UserAgent().chrome)}

    return util.try_success(lambda: xmltodict.parse(SESSION.get(url, headers=headers).content), pre_delay=1)


def _get_paper_entry(pubmed_id: str) -> dict:  # pragma: no cover
    """
    This method return paper data from PubMed database using the provided PubMed ID

    Parameters
    ----------
    pubmed_id : str
        A PubMed ID

    Returns
    -------
    dict
        a paper entry from PubMed database
    """

    url = f'{BASE_URL}/entrez/eutils/efetch.fcgi?db=pubmed&id={pubmed_id}&rettype=abstract'
    headers = {'User-Agent': str(UserAgent().chrome)}

    return util.try_success(lambda: xmltodict.parse(SESSION.get(url, headers=headers).content), pre_delay=1)


def _get_publication(paper_entry: dict) -> Publication:
    """
    Using a paper entry provided, this method builds a publication instance

    Parameters
    ----------
    paper_entry : dict
        A paper entry retrived from PubMed API

    Returns
    -------
    Publication
        A publication instance
    """

    article = paper_entry.get('PubmedArticleSet').get(
        'PubmedArticle').get('MedlineCitation').get('Article')

    publication_title = article.get('Journal').get('Title')
    publication_issn = article.get('Journal').get('ISSN').get('#text')

    publication = Publication(publication_title, None,
                              publication_issn, None, 'Journal')

    return publication


def _get_paper(paper_entry: dict, publication: Publication) -> Paper:
    """
    Using a paper entry provided, this method builds a paper instance

    Parameters
    ----------
    paper_entry : dict
        A paper entry retrived from IEEE API
    publication : Publication
        A publication instance that will be associated with the paper

    Returns
    -------
    Paper
        A paper instance
    """

    article = paper_entry.get('PubmedArticleSet').get(
        'PubmedArticle').get('MedlineCitation').get('Article')

    paper_title = article.get('ArticleTitle')

    if 'ArticleDate' in article:
        paper_publication_date_day = article.get('ArticleDate').get('Day')
        paper_publication_date_month = article.get('ArticleDate').get('Month')
        paper_publication_date_year = article.get('ArticleDate').get('Year')
    else:
        paper_publication_date_day = 1
        paper_publication_date_month = util.get_numeric_month_by_string(
            article.get('Journal').get('JournalIssue').get('PubDate').get('Month'))
        paper_publication_date_year = article.get('Journal').get(
            'JournalIssue').get('PubDate').get('Year')

    paper_doi = None
    paper_ids = paper_entry.get('PubmedArticleSet').get('PubmedArticle').get(
        'PubmedData').get('ArticleIdList').get('ArticleId')
    for paper_id in paper_ids:
        if paper_id.get('@IdType') == 'doi':
            paper_doi = paper_id.get('#text')
            break

    paper_abstract = None
    if isinstance(article.get('Abstract').get('AbstractText'), list):
        paper_abstract = '\n'.join(
            [x.get('#text') for x in article.get('Abstract').get('AbstractText') if x.get('#text') is not None])
    else:
        paper_abstract = article.get('Abstract').get('AbstractText')

    try:
        paper_keywords = set([x.get('#text') for x in paper_entry.get('PubmedArticleSet').get(
            'PubmedArticle').get('MedlineCitation').get('KeywordList').get('Keyword')])
    except Exception:
        paper_keywords = set()

    try:
        paper_publication_date = datetime.date(int(paper_publication_date_year), int(
            paper_publication_date_month), int(paper_publication_date_day))
    except Exception:
        paper_publication_date = datetime.date(
            int(paper_publication_date_year), 1, 1)

    paper_authors = []
    for author in article.get('AuthorList').get('Author'):
        paper_authors.append(
            f"{author.get('ForeName')} {author.get('LastName')}")

    paper_pages = None
    paper_number_of_pages = None
    try:
        paper_pages = article.get('Pagination').get('MedlinePgn')
        if paper_pages.isdigit():
            paper_number_of_pages = 1
        else:
            pages_split = paper_pages.split('-')
            paper_number_of_pages = abs(int(pages_split[0])-int(pages_split[1]))+1
    except Exception:  # pragma: no cover
        pass

    paper = Paper(paper_title, paper_abstract, paper_authors, publication,
                  paper_publication_date, [], paper_doi, None, paper_keywords, None, 
                  paper_number_of_pages, paper_pages)

    return paper


def run(search: Search):
    """
    This method fetch papers from IEEE database using the provided search parameters
    After fetch the data from IEEE, the collected papers are added to the provided search instance

    Parameters
    ----------
    search : Search
        A search instance
    api_token : str
        The API key used to fetch data from IEEE database,

    Raises
    ------
    AttributeError
        - The API token cannot be null
    """

    papers_count = 0
    result = _get_api_result(search)

    total_papers = int(result.get('eSearchResult').get('Count'))

    logging.info(f'{total_papers} papers to fetch')

    while(papers_count < total_papers and not search.reached_its_limit(DATABASE_LABEL)):

        for pubmed_id in result.get('eSearchResult').get('IdList').get('Id'):

            if papers_count >= total_papers or search.reached_its_limit(DATABASE_LABEL):
                break
            try:

                paper_entry = _get_paper_entry(pubmed_id)

                if paper_entry is not None:

                    title = paper_entry.get('PubmedArticleSet').get('PubmedArticle').get(
                        'MedlineCitation').get('Article').get('ArticleTitle')

                    logging.info(title)

                    publication = _get_publication(paper_entry)
                    paper = _get_paper(paper_entry, publication)

                    paper.add_database(DATABASE_LABEL)

                    search.add_paper(paper)

            except Exception as e:  # pragma: no cover
                logging.error(e, exc_info=True)

            papers_count += 1
            logging.info(f'{papers_count}/{total_papers} PubMed papers fetched')

        if papers_count < total_papers and not search.reached_its_limit(DATABASE_LABEL):
            result = _get_api_result(search, papers_count)