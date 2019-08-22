# -*- coding: utf-8 -*-
#
# Copyright 2018 Outlier Bio, LLC
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

"""
NOTE: overwhelmingly based on this_, where the following documentation
has been directly lifted. The main difference to the latter, is that
AWS jobs are submitted via :code:`**kwargs` in order to allow more
flexibility (and probably more future-proofing if new parameters are
added to boto3).

.. _this: https://luigi.readthedocs.io/en/stable/api/luigi.contrib.batch.html#luigi.contrib.batch.BatchClient

AWS Batch wrapper for Luigi

From the AWS website:

    AWS Batch enables you to run batch computing workloads on the AWS Cloud.

    Batch computing is a common way for developers, scientists, and engineers
    to access large amounts of compute resources, and AWS Batch removes the
    undifferentiated heavy lifting of configuring and managing the required
    infrastructure. AWS Batch is similar to traditional batch computing
    software. This service can efficiently provision resources in response to
    jobs submitted in order to eliminate capacity constraints, reduce compute
    costs, and deliver results quickly.

See `AWS Batch User Guide`_ for more details.

To use AWS Batch, you create a jobDefinition JSON that defines a `docker run`_
command, and then submit this JSON to the API to queue up the task. Behind the
scenes, AWS Batch auto-scales a fleet of EC2 Container Service instances,
monitors the load on these instances, and schedules the jobs.

This `boto3-powered`_ wrapper allows you to create Luigi Tasks to submit Batch
``jobDefinition``s. You can either pass a dict (mapping directly to the
``jobDefinition`` JSON) OR an Amazon Resource Name (arn) for a previously
registered ``jobDefinition``.

Requires:

- boto3 package
- Amazon AWS credentials discoverable by boto3 (e.g., by using ``aws configure``
  from awscli_)
- An enabled AWS Batch job queue configured to run on a compute environment.

Written and maintained by Jake Feala (@jfeala) for Outlier Bio (@outlierbio)

.. _`docker run`: https://docs.docker.com/reference/commandline/run
.. _jobDefinition: http://http://docs.aws.amazon.com/batch/latest/userguide/job_definitions.html
.. _`boto3-powered`: https://boto3.readthedocs.io
.. _awscli: https://aws.amazon.com/cli
.. _`AWS Batch User Guide`: http://docs.aws.amazon.com/AmazonECS/latest/developerguide/ECS_GetStarted.html

"""

import json
import logging
import random
import string
import time

import luigi
logger = logging.getLogger(__name__)

try:
    import boto3
except ImportError:
    logger.warning('boto3 is not installed. BatchTasks require boto3')


class BatchJobException(Exception):
    pass


POLL_TIME = 10


def _random_id():
    return 'batch-job-' + ''.join(random.sample(string.ascii_lowercase, 8))


class BatchClient(object):

    def __init__(self, poll_time=POLL_TIME, **kwargs):
        self.poll_time = poll_time
        self._client = boto3.client('batch', **kwargs)
        self._log_client = boto3.client('logs', **kwargs)
        self._queue = None
        #self._queue = self.get_active_queue()

    def get_active_queue(self):
        """Get name of first active job queue"""

        # Get dict of active queues keyed by name
        queues = {q['jobQueueName']: q for q in self._client.describe_job_queues()['jobQueues']
                  if q['state'] == 'ENABLED' and q['status'] == 'VALID'}
        if not queues:
            raise Exception('No job queues with state=ENABLED and status=VALID')

        # Pick the first queue as default
        return list(queues.keys())[0]

    def get_job_id_from_name(self, job_name):
        """Retrieve the first job ID matching the given name"""
        jobs = self._client.list_jobs(jobQueue=self._queue, jobStatus='RUNNING')['jobSummaryList']
        matching_jobs = [job for job in jobs if job['jobName'] == job_name]
        if matching_jobs:
            return matching_jobs[0]['jobId']

    def get_job_status(self, job_id):
        """Retrieve task statuses from ECS API

        :param job_id (str): AWS Batch job uuid

        Returns one of {SUBMITTED|PENDING|RUNNABLE|STARTING|RUNNING|SUCCEEDED|FAILED}
        """
        response = self._client.describe_jobs(jobs=[job_id])

        # Error checking
        status_code = response['ResponseMetadata']['HTTPStatusCode']
        if status_code != 200:
            msg = 'Job status request received status code {0}:\n{1}'
            raise Exception(msg.format(status_code, response))
        if len(response['jobs']) == 0:
            return 'FAILED'
            #time.sleep(60)
            #return self.get_job_status(job_id)

        return response['jobs'][0]['status']

    def get_logs(self, log_stream_name, get_last=50):
        """Retrieve log stream from CloudWatch"""
        response = self._log_client.get_log_events(
            logGroupName='/aws/batch/job',
            logStreamName=log_stream_name,
            startFromHead=False)
        events = response['events']
        return '\n'.join(e['message'] for e in events[-get_last:])

    def submit_job(self, **kwargs):
        """Wrap submit_job with useful defaults"""
        if "jobName" not in kwargs:
            kwargs["jobName"] = _random_id()
        if "jobQueue" in kwargs:
            self._queue = kwargs["jobQueue"]
        response = self._client.submit_job(**kwargs)
        #jobName=job_name,
        #    jobQueue=queue or self.get_active_queue(),
        #    jobDefinition=job_definition,
        #    parameters=parameters,
        #    **kwargs
        #)
        return response['jobId']

    def terminate_job(self, **kwargs):
        """Wrap terminate_job"""
        self._client.terminate_job(**kwargs)

    def hard_terminate(self, job_ids, reason, iattempt=0, **kwargs):
        """Terminate all jobs with a hard(ish) exit via an Exception.
        The function will also wait for jobs to be explicitly terminated"""

        # Try to kill all the jobs and then wait a couple of seconds
        for job_id in job_ids:
            self.terminate_job(jobId=job_id, reason=reason, **kwargs)        
        time.sleep(30)

        # Check which jobs are still running
        job_ids = [job_id for job_id in job_ids 
                   if self.get_job_status(job_id) 
                   not in ("FAILED", "SUCCEEDED")]
        if len(job_ids) > 0 and iattempt < 10:
            print("Still got", len(job_ids),
                  "hanging batch jobs to terminate")
            return self.hard_terminate(job_ids, reason, 
                                       iattempt=iattempt+1, 
                                       **kwargs)
    
        if iattempt >= 10:
            reason += "\n NOTE: {} jobs could not be killed!".format(len(job_ids))
        # When finished terminating, shut it all down
        raise BatchJobException(reason)

    def wait_on_job(self, job_id):
        """Poll task status until STOPPED"""

        while True:
            status = self.get_job_status(job_id)
            if status == 'SUCCEEDED':
                logger.info('Batch job {} SUCCEEDED'.format(job_id))
                return True
            elif status == 'FAILED':
                # Raise and notify if job failed
                jobs = self._client.describe_jobs(jobs=[job_id])['jobs']
                job_str = json.dumps(jobs, indent=4)
                logger.debug('Job details:\n' + job_str)

                log_stream_name = jobs[0]['attempts'][0]['container']['logStreamName']
                logs = self.get_logs(log_stream_name)
                raise BatchJobException('Job {} failed: {}'.format(
                    job_id, logs))

            time.sleep(self.poll_time)
            logger.debug('Batch job status for job {0}: {1}'.format(
                job_id, status))

    def register_job_definition(self, json_fpath):
        """Register a job definition with AWS Batch, using a JSON"""
        with open(json_fpath) as f:
            job_def = json.load(f)
        response = self._client.register_job_definition(**job_def)
        status_code = response['ResponseMetadata']['HTTPStatusCode']
        if status_code != 200:
            msg = 'Register job definition request received status code {0}:\n{1}'
            raise Exception(msg.format(status_code, response))
        return response

