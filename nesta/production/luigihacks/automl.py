"""
automl
------

Automatic piping of Machine Learning tasks
(which are AutoBatchTasks) using
a configuration file. Data inputs and outputs are
chained according to S3Targets, although
obviously any batchable can access database data
if required.
"""

import luigi
from nesta.production.luigihacks import autobatch
from nesta.production.luigihacks.parameter import DictParameterPlus
from nesta.production.luigihacks import s3
from nesta.production.luigihacks.misctools import find_filepath_from_pathstub
import os
import json
import logging
import math
import numpy as np
import itertools
from copy import deepcopy
import re
from collections import defaultdict
from collections import Counter
import boto3

FLOAT = r'([-+]?\d*\.\d+|\d+)'
NP_ARANGE = fr'np.arange\({FLOAT},{FLOAT},{FLOAT}\)'

def _MLTask(**kwargs):
    '''
    Factory function for dynamically creating py:class`MLTask`
    tasks with a specific class name. This helps to differentiate
    py:class`MLTask` tasks from one another in the luigi scheduler.

    Args:
        kwargs (dict): All keyword arguments to construct an MLTask.
    Returns:
        MLTask object.
    '''
    _type = type(kwargs['job_name'].title(), (MLTask,), {})
    return _type(**kwargs)

def expand_pathstub(pathstub):
    """Expand the pathstub.

    Args:
        pathstub (list or str): A pathstub or list of pathstubs to expand.
    Returns:
        fullpath (list or str): A fullpath or list of fullpaths
    """
    # Expand from a list...
    if type(pathstub) is list:
        return [find_filepath_from_pathstub(_v) for _v in pathstub]
    # ...or from a string (assumed)
    else:
        return find_filepath_from_pathstub(pathstub)

def expand_envs(row, env_keys):
    """Expand any pathstubs in row for matching keys.

    Args:
        row (dict): row of data to search for pathstubs.
        env_keys (list): Keys to consider to pathsub expansion.
    Returns:
        row (dict): Input row modified with pathsub expansion.
    """
    for key in env_keys:
        if key in row:
            row[key] = expand_pathstub(row[key])
    return row

def arange(expression):
    """Expand and string representation of np.arange into a function call.

    Args:
        expression (str): String representation of :obj:`np.arange` function call.
    Yields:
        Result of :obj:`np.arange` function call.
    """
    args = re.findall(NP_ARANGE, expression.replace(' ',''))[0]
    return list(np.arange(*[float(arg) for arg in args]))

def expand_value_range(value_range_expression):
    """Expand the value range expression.

    Args:
        value_range_expression: Value range or expression to expand.
    Return:
        iterable.
    """
    if type(value_range_expression) is str:
        # Grid search
        if value_range_expression.startswith('np.arange'):
            value_range_expression = arange(value_range_expression)
        # Random search
        elif value_range_expression.startswith('np.random'):
            raise NotImplementedError('Random search space '
                                      'not implemented yet')
    # If not an iterable, make it an iterable
    try:
        iter(value_range_expression)
    except TypeError:
        value_range_expression = [value_range_expression]
    return value_range_expression

def expand_hyperparams(row):
    """Generate all hyperparameter combinations for this task.

    Args:
        row (dict): Row containing hyperparameter space to expand
    Returns:
        rows (list): List of dict to every combination of hyperparameters
    """
    if 'hyperparameters' not in row:
        return [row]
    expanded_hyps = {name: expand_value_range(values)
                     for name, values
                     in row.pop('hyperparameters').items()}
    hyp_names = expanded_hyps.keys()
    hyp_value_sets = itertools.product(*expanded_hyps.values())
    # Generate one row per hyperparameters combination
    return [dict(hyperparameters={name: value for name, value
                                  in zip(hyp_names, hyp_values)},
                 **row)
            for hyp_values in hyp_value_sets]

def ordered_groupby(collection, column):
    """Group collection by a column, maintaining the key
    order from the collection.

    Args:
        collection (list): List of flat dictionaries.
        column (str): Column (dict key) by which to group the list.
    Returns:
        grouped (dict): Dict of the column to subcollections.
    """
    # Figure out the group order
    group_order = []
    for row in collection:
        group = row[column]
        if group not in group_order:
            group_order.append(group)
    # Group by in order
    return {group: [row for row in collection
                    if row[column] == group]
            for group in group_order}


def cascade_child_params(chain_params):
    """Find upstream child parameters and cascade these
    to the parent.

    Args:
        chain_params (list): List of task parameters
    Returns:
        chain_params (list): List of task parameters, with children expanded.
    """
    _chain_params = defaultdict(list)
    for job_name, rows in chain_params.items():
        for row in rows:
            uid = generate_uid(job_name, row)
            # Only parents after this point
            if row["child"] is None:
                row['uid'] = uid
                _chain_params[job_name].append(deepcopy(row))
                continue
            # Cascade parameters to parents (including UID)
            child = row["child"]
            child_rows = _chain_params[child]
            for child_row in child_rows:
                _row = deepcopy(row)
                _row["child"] = child_row["uid"]
                _row['uid'] = uid + '.' + child_row["uid"]
                for k, v in child_row.items():
                    if k == "hyperparameters":
                        continue
                    if k not in _row:
                        _row[k] = v
                _chain_params[job_name].append(_row)
    return _chain_params


def generate_uid(job_name, row):
    """Generate the UID from the job name and children"""
    uid = job_name.upper()
    try:
        hyps = row["hyperparameters"]
    except KeyError:
        pass
    else:
        uid += '.' + ".".join(f"{k}_{v}".replace('.','-')
                              for k, v in hyps.items())
    finally:
        return uid


def deep_split(s3_path):
    """Return subbucket path: <s3:pathto/subbucket_name>/keys

    Args:
        s3_path (str): S3 path string.
    Returns:
        subbucket_path (str): Path to the subbucket.
    """
    s3_bucket, s3_key = s3.parse_s3_path(s3_path)
    subbucket, _ = os.path.split(s3_key)
    return s3_bucket, subbucket, s3_key


def subsample(rows):
    """Extract 3 rows from rows for testing purposes.
    The first, last and middlish value are extracted.

    Args:
        rows (list): Data to be subsetted.
    Returns:
        _rows (list): 3 points sampled from the input.
    """
    n = len(rows)
    if n > 3:
        rows = [rows[0], rows[-1], rows[int((n+1)/2)]]
    return rows


def bucket_filter(s3_path_prefix, uids):
    """
    Get all json objects in the bucket starting with a valid UID.
    
    Args:
        uids (list): List of UIDs which the s3 keys must start with.
    Yields:
        key, json
    """
    bucket_name, _, _ = deep_split(s3_path_prefix)
    bucket = boto3.resource('s3').Bucket(bucket_name)        
    for obj in bucket.objects.all():
        key = obj.key.split('/')[-1]
        if not key.endswith('json'):
            continue
        elif not any(key.startswith(uid) for uid in uids):
            continue
        yield obj.key, json.load(obj.get()['Body'])


class MLTask(autobatch.AutoBatchTask):
    """A task which automatically spawns children if they exist.
    Note that other args are intended for autobatch.AutoBatchTask.

    Args:
        job_name (str): Name of the task instance, for book-keeping.
        #s3_path_in (str): Path to the input data.
        s3_path_out (str): Path to the output data.
        batch_size (int): Size of batch chunks.
        n_batches (int): The number of batches to submit (alternative to :obj:`batch_size`)
        child (dict): Parameters to spawn a child task with.
        hyper (dict): Extra environmental variables to pass to the batchable.
    """
    job_name = luigi.Parameter()
    s3_path_out = luigi.Parameter()
    input_task = luigi.TaskParameter(default=luigi.Task,
                                     significant=False)
    input_task_kwargs = DictParameterPlus(default={})
    batch_size = luigi.IntParameter(default=None)
    n_batches = luigi.IntParameter(default=None)
    child = DictParameterPlus(default=None)
    use_intermediate_inputs = luigi.BoolParameter(default=False)
    combine_outputs = luigi.BoolParameter(default=True)
    hyperparameters = DictParameterPlus(default={})

    def requires(self):
        """Spawns a child if one exists, otherwise points
        to a static input."""
        if self.child is not None:
            msg = f"MLTask with child = {self.child['job_name']}"
            task = _MLTask(**self.child)
        elif self.input_task is luigi.Task:
            raise ValueError('input_task cannot be empty if no child '
                             'has been specified')
        else:
            msg = f"{str(self.input_task)} with {self.input_task_kwargs}"
            task = self.input_task(**self.input_task_kwargs)
        #else:
        #    msg = f"DummyInput from {self.s3_path_in}"
        #    task = DummyInputTask(s3_path_in=self.s3_path_in)
        logging.debug(f"{self.job_name}: Spawning {msg}")
        return task

    def output(self):
        """Points to the output"""
        if self.combine_outputs:
            return s3.S3Target(f"{self.s3_path_out}.json")
        return s3.S3Target(f"{self.s3_path_out}.length")

    @property
    def s3_path_in(self):
        target = self.input()
        return f's3://{target.s3_bucket}/{target.s3_key}'

    def derive_file_length_path(self):
        """Determine the s3 path to the file which contains the
        the number of lines in the main (json) file.
        """
        fname = self.s3_path_in
        ext = fname.split('.')[-1]
        if ext not in ('json', 'length'):
            raise ValueError('Input file must either be json'
                             f'or length file. Got {ext} from {fname}')
        elif ext == 'json':
            fname = fname.replace('.json','')
        if not fname.endswith('.length'):
            fname = f"{fname}.length"
        return fname

    def get_input_length(self):
        """Retrieve the length of the input, which is stored as the value
        of the output.length file."""
        fname = self.derive_file_length_path()
        f = s3.S3Target(fname).open('rb')
        total = json.load(f)
        if type(total) is not int:
            raise TypeError('Expected to find integer count in '
                            f'{fname}. Instead found {type(total)}')
        f.close()
        return total

    def set_batch_parameters(self):
        # Assert that the batch size parameters aren't contradictory
        if self.batch_size is None and self.n_batches is None:
            raise ValueError("Neither batch_size for n_batches set")

        # Calculate the batch size parameters
        total = self.get_input_length()
        if self.n_batches is not None:
            if self.n_batches > total:
                self.n_batches = total
            self.batch_size = math.ceil(total/self.n_batches)
        else:
            if self.batch_size > total:
                self.batch_size = total
            n_full = math.floor(total/self.batch_size)
            n_unfull = int(total % self.batch_size > 0)
            self.n_batches = n_full + n_unfull

        logging.debug(f"{self.job_name}: Will use {self.n_batches} to "
                      f"process the task {total} "
                      f"with batch size {self.batch_size}")
        return total

    def calculate_batch_indices(self, i, total):
        """Calculate the indices of this batch"""
        if (self.batch_size is None or self.n_batches is None
            or self.batch_size > total or self.n_batches > total):
            raise ValueError('set_batch_parameters not yet called')
        first_index = i*self.batch_size
        last_index = (i+1)*self.batch_size
        if i >= self.n_batches:
            raise ValueError('Exceeded maximum batch index '
                             f'({self.n_batches}) with {i}')
        if i == self.n_batches-1:
            last_index = total
        return first_index, last_index

    def yield_batch(self):
        s3_key = self.s3_path_out
        # Mode 1: each batch is one of the intermediate inputs
        if self.use_intermediate_inputs:
            first_idx = 0
            last_idx = -1
            s3_resource = boto3.resource('s3')
            bucket, subbucket, _ = deep_split(self.s3_path_in)
            in_keys = s3_resource.Bucket(bucket).objects
            i = 0
            for _in_key in in_keys.all():
                in_key = _in_key.key
                if not in_key.endswith(".json"):
                    continue
                if not in_key.startswith(subbucket):
                    continue
                out_key = f"{s3_key}-{i}.json"
                _in_key = f"s3://{bucket}/{in_key}"
                yield first_idx, last_idx, _in_key, out_key
                i += 1
        # Mode 2: each batch is a subset of the single input
        else:
            total = self.set_batch_parameters()
            for i in range(0, self.n_batches):
                first_idx, last_idx = self.calculate_batch_indices(i, total)
                out_key = (f"{s3_key}-{first_idx}_"
                           f"{last_idx}.json")
                yield first_idx, last_idx, self.s3_path_in, out_key

    def prepare(self):
        """Prepare the batch task parameters"""
        # Generate the task parameters
        s3fs = s3.S3FS()
        job_params = []
        n_done = 0
        for first_idx, last_idx, in_key, out_key in self.yield_batch():
            # Fill the default params
            done = s3fs.exists(out_key)
            params = {"s3_path_in": in_key,
                      "first_index": first_idx,
                      "last_index": last_idx,
                      "outinfo": out_key,
                      "done": done}
            # Add in any bonus paramters
            for k, v in self.hyperparameters.items():
                params[k] = v
            # Append and book-keeping
            n_done += int(done)
            job_params.append(params)
        # Done
        logging.debug(f"{self.job_name}: {n_done} of {len(job_params)} "
                      "have already been done.")
        return job_params

    def combine_all_outputs(self, job_params):
        size = 0
        outdata = []
        for params in job_params:
            _body = s3.S3Target(params["outinfo"]).open("rb")
            _data = _body.read().decode('utf-8')
            _outdata = json.loads(_data)
            # Combine if required
            if len(job_params) == 1:
                outdata = _outdata
            elif self.combine_outputs:
                outdata += _outdata
            # Get the length of the data
            if type(_outdata) is not list:
                _outdata = _outdata['data']['rows']
            size += len(_outdata)
        return size, outdata

    def combine(self, job_params):
        """Combine output by concatenating results."""
        # Download and join
        logging.debug(f"{self.job_name}: Combining "
                      f"{len(job_params)}...")
        size, outdata = self.combine_all_outputs(job_params)
        # Write the output
        logging.debug(f"{self.job_name}: Writing the output "
                      f"(length {len(outdata)})...")
        if self.combine_outputs:
            f = self.output().open("wb")
            f.write(json.dumps(outdata).encode('utf-8'))
            f.close()

        # Write the output length as well, for book-keeping
        f = s3.S3Target(f"{self.s3_path_out}.length").open("wb")
        f.write(str(size).encode("utf-8"))
        f.close()


class AutoMLTask(luigi.Task):
    """Parse and launch the MLTask chain based on an input
    configuration file.

    Args:
        input_task (luigi.Task): A task class to be the sole
                                 pipeline requirement.
        input_task_kwargs (dict): kwargs for input_task.__init__
        s3_path_prefix (str): Prefix of all paths to the output data.
        task_chain_filepath (str): File path of the task chain
                                   configuration file.
        test (bool): Whether or not to run batch tasks in test mode.
        autobatch_kwargs (dict): Extra arguments to pass to autobatch.__init__ (Note that MLTask inherits from AutoBatchTask).
        maximize_loss (bool): Maximise the loss function?
        gp_optimizer_kwargs (kwargs): kwargs for the GP optimizer.
    """
    input_task = luigi.TaskParameter()
    input_task_kwargs = DictParameterPlus(default={})
    s3_path_prefix = luigi.Parameter()
    task_chain_filepath = luigi.Parameter()
    test = luigi.BoolParameter(default=True)
    autobatch_kwargs = DictParameterPlus(default={})
    maximize_loss = luigi.BoolParameter(default=False)
    gp_optimizer_kwargs = luigi.DictParameter(default={})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        AutoMLTask.task_parameters = {}  # To keep track of children

    def generate_seed_search_tasks(self, env_keys=["batchable",
                                                   "env_files"]):
        """Generate task parameters, which could be fixed,
        grid or random. Note: random not yet implemented.

        Parse the chain parameters into a dictionary, and expand
        filepaths if specified.

        Args:
            env_keys (list): List (or list of lists) of partial
                             (note, not necessarily relative)
                             filepaths to expand into absolute
                             filepaths.
                             See :obj:`find_filepath_from_pathstub`
                             for more information.
        """
        with open(self.task_chain_filepath) as f:
            _chain_params = json.load(f)
        # Expand filepaths, children and hyperparameters
        chain_params = []
        child = None
        for row in _chain_params:
            # The previous task is this child if child not specified
            row['child'] = row['child'] if 'child' in row else child
            row = expand_envs(row, env_keys)
            rows = expand_hyperparams(row)
            chain_params += subsample(rows) if self.test else rows
            # This task is the proceeding task's child, by default
            child = row['job_name']
        # Group parameters by job name
        chain_params = ordered_groupby(chain_params, 'job_name')
        # Impute missing parent information from children
        chain_params = cascade_child_params(chain_params)
        return chain_params

    def make_path(self, uid):
        """Make the in/output path from the task uid"""
        if uid is None:
            return None
        return os.path.join(self.s3_path_prefix,
                            f'{uid}.TEST_{self.test}')

    def launch(self, chain_params):
        """Launch jobs from the parameters"""
        # Generate all kwargs for tasks
        kwargs_dict = {}
        all_children = set()
        for job_name, all_parameters in chain_params.items():
            AutoMLTask.task_parameters[job_name] = all_parameters
            for pars in all_parameters:
                path_in = self.make_path(pars['child'])
                path_out = self.make_path(pars.pop('uid'))
                kwargs_dict[path_out] = dict(s3_path_out=path_out,
                                             s3_path_in=path_in,
                                             test=self.test,
                                             **pars)
                all_children.add(path_in)
                # Special case: if no input, set the input task
                if path_in is None:
                    _kwargs = self.input_task_kwargs
                    kwargs_dict[path_out]['input_task'] = self.input_task
                    kwargs_dict[path_out]['input_task_kwargs'] = _kwargs

        # Launch the tasks
        for uid, kwargs in kwargs_dict.items():
            child_uid = kwargs.pop('s3_path_in')
            if child_uid is not None:
                kwargs['child'] = kwargs_dict[child_uid]
            # Only yield "pure" parents (those with no parents)
            if uid not in all_children:
                yield kwargs

    def requires(self):
        """Generate task parameters and yield MLTasks"""
        # Generate the parameters
        chain_params = self.generate_seed_search_tasks()
        # chain_params += self.generate_optimization_tasks() ## <-- blank optimisation tasks
        for kwargs in self.launch(chain_params):
            yield _MLTask(**kwargs, **self.autobatch_kwargs)

    def output(self):
        return s3.S3Target(f"{self.s3_path_prefix}.{self.test}.best")


    def extract_losses(self, uids):
        """Extract the loss values from each output json file"""
        # 1 - 2*[1 OR 0] = [-1 OR 1]
        loss_sign = 1 - 2*int(self.maximize_loss)
        # Find the losses
        return {key: loss_sign * js['loss']
                for key, js in 
                bucket_filter(self.s3_path_prefix, uids)}

    def run(self):
        # Get the UIDs for the final tasks
        final_task = list(AutoMLTask.task_parameters.keys())[-1]        
        uids = [generate_uid(final_task, row)
                for row in AutoMLTask.task_parameters[final_task]]
        losses = self.extract_losses(uids)
        # Least common = minimum loss
        best_key = Counter(losses).most_common()[-1][0]
        f = self.output().open("wb")
        f.write(best_key.encode('utf-8'))
        f.close()

        if len(self.gp_optimizer_kwargs) > 0:
            raise NotImplementedError('Gaussian Processes not implemented')
