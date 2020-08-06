'''
Batch Example
=============

An example of building a pipeline with batched tasks.
'''

from nesta.core.luigihacks import autobatch
from nesta.core.luigihacks import s3
from nesta.core.luigihacks.misctools import find_filepath_from_pathstub as f3p
import luigi
import datetime
import json
import time

S3PREFIX = "s3://nesta-dev/production_batch_example_"


class SomeInitialTask(luigi.ExternalTask):
    '''Dummy task acting as the single input data source'''
    def output(self):
        '''Points to the S3 Target'''        
        return s3.S3Target(S3PREFIX+'input.json')


class SomeBatchTask(autobatch.AutoBatchTask):
    '''A set of batched tasks which increments the age of the muppets by 1 year.

    Args:
        date (datetime): Date used to label the outputs
        batchable (str): Path to the directory containing the run.py batchable
        job_def (str): Name of the AWS job definition
        job_name (str): Name given to this AWS batch job
        job_queue (str): AWS batch queue
        region_name (str): AWS region from which to batch
        poll_time (int): Time between querying the AWS batch job status
    '''
    date = luigi.DateParameter(default=datetime.datetime.today())

    def requires(self):
        '''Gets the input data (json containing muppet name and age)'''
        return SomeInitialTask()

    def output(self):
        '''Points to the S3 Target'''
        return s3.S3Target(S3PREFIX+"intermediate_output_%s.json" % self.date)

    def prepare(self):
        '''Prepare the batch job parameters'''
        # Open the input file
        instream = self.input().open("rb")
        job_params = json.load(instream)
        s3fs = s3.S3FS()

        # Add the mandatory `outinfo' and `done' fields
        for i, params in enumerate(job_params):
            params["outinfo"] = ("s3://nesta-production-intermediate/"
                                 "batch-example-{}-{}".format(self.date, i))            
            params["done"] = s3fs.exists(params["outinfo"])
        return job_params

    def combine(self, job_params):
        '''Combine the outputs from the batch jobs'''
        outdata = []
        for params in job_params:
            _body = s3.S3Target(params["outinfo"]).open("rb")
            _data = _body.read().decode('utf-8')
            outdata.append(json.loads(_data))

        with self.output().open("wb") as f:
            f.write(json.dumps(outdata).encode('utf-8'))


class RootTask(luigi.Task):
    '''The root task, which adds the surname 'Muppet'
    to the names of the muppets.

    Args:
        date (datetime): Date used to label the outputs
    '''
    date = luigi.DateParameter(default=datetime.datetime.today())

    def requires(self):
        '''Get the output from the batchtask'''
        return SomeBatchTask(date=self.date,
                             env_files=[f3p("/nesta")],
                             batchable=(f3p("batchables/examples/batch_example/")),
                             job_def="py36_amzn1_image",
                             job_name="batch-example-%s" % self.date,
                             job_queue="HighPriority",
                             region_name="eu-west-2",
                             poll_time=60)

    def output(self):
        '''Points to the S3 Target'''
        return s3.S3Target(S3PREFIX+"final_output_%s.json" % self.date)

    def run(self):
        '''Appends 'Muppet' the muppets' names'''

        time.sleep(10)
        instream = self.input().open('rb')
        data = json.load(instream)
        for row in data:
            row["name"] += " Muppet"

        with self.output().open('wb') as outstream:
            outstream.write(json.dumps(data).encode('utf8'))
