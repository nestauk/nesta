# CHANGELOG

# 9/4/21

* New fields corresponding to NiH project outputs, which are mainly IDs that could be linked to other open datasets:

    * `terms_id_clinicalTrial`: Clinical trial IDs for this project that can be linked directly to `https://www.clinicaltrials.gov/ct2/show/{clinical_trial_id}`
    * `terms_id_pubmedId`: PubMed IDs for this project that can be direclty linked to `https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}`
    * `terms_title_patent` and `terms_id_patent`: Patent titles and IDs. Would require linking to patstat for more info.

* Deduplication according to strategy implemented in [this PR](nestauk/nesta#300), which helps explain the following new fields for the format `terms_{X}_project` with `X` =

    * `exactDupeId`, `exactDupeTitle`: refering to IDs and titles of projects which we have removed from the dataset for being exact duplicates. Only distinct titles are provided, and any funding allocations, start and end dates and funding are incorporated into the deduplicated recorded in the logical way (earliest start date, latest end date, sum of funding)
    * `nearDupeId`: referring to IDs of projects with similarity >= 0.8
    * `verySimilarId`: referring to IDs of projects with 0.8 > similarity >= 0.65
    * `similarId`: referring to IDs of projects with 0.65 > similarity >= 0.4
    
    For example:
    
    * [this project](https://search-general-wvbdcvn3kmpz6lvjo2nkx36pbu.eu-west-2.es.amazonaws.com/nih_v0/_search?q=_id:2180092) has several exact dupes and [one near dupe](https://search-general-wvbdcvn3kmpz6lvjo2nkx36pbu.eu-west-2.es.amazonaws.com/nih_v0/_search?q=_id:3297189), which itself has one exact dupe
    * [this project](https://search-general-wvbdcvn3kmpz6lvjo2nkx36pbu.eu-west-2.es.amazonaws.com/nih_v0/_search?q=_id:100160) has [one very similar but non-identical project](https://search-general-wvbdcvn3kmpz6lvjo2nkx36pbu.eu-west-2.es.amazonaws.com/nih_v0/_search?q=_id:100296)
    * [this project](https://search-general-wvbdcvn3kmpz6lvjo2nkx36pbu.eu-west-2.es.amazonaws.com/nih_v0/_search?q=_id:100074) and [this project](https://search-general-wvbdcvn3kmpz6lvjo2nkx36pbu.eu-west-2.es.amazonaws.com/nih_v0/_search?q=_id:7220147) are fairly similar
    
    
    
* An additional form of deduplication was discovered as discussed in [this PR](nestauk/nesta#337), which says that what NiH tell you is a primary key isn't really a primary key. Instead we impute a primary key based on the core ID as per the PR and consolidate projects accordingly.

* mesh terms are no longer supported as discussed [here](https://github.com/nestauk/nesta/pull/328#discussion_r512646286), [here](https://data-analytic-nesta.slack.com/archives/CK76G6NDD/p1603801230010600) and elsewhere.

* The curation of `json_funding_project` is dealt with more gracefully and so the sub-schema (i.e. in the mapping) has been updated from e.g.:

    ```json
    {
      "year": 1988,
      "cost_ref": 3654295,
      "start_date": 2011-07-31,
      "end_date": 1988-04-01
    }
    ```
    
    to
    
    ```json
    {
      "year": 1988,
      "total_cost": 3654295,
      "project_end": "2011-07-31",
      "project_start": "1988-04-01"
    }
    ```
    
* Cleaning steps implemented in [this PR](nestauk/nesta#327):

     * Split `;` `terms` into an array
     * CAPS --> Camel Case
     * Address the bad dq issue highlighted in nestauk/nesta#51
     * Check Greek characters (etc) parse ok
     * Check question marks (bad unicode parsing) fixed
     * `"NULL"`, `""`, `"N/A"`, `[]` --> `null`
     
     
