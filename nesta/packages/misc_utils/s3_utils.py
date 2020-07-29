import pickle
import boto3


def pickle_to_s3(data, bucket, prefix):
    """Writes out data to s3 as pickle, so it can be picked up by a task.

    Args:
        data (:obj:`list` of :obj:`str`): A batch of records.
        bucket (str): Name of the s3 bucket.
        prefix (str): Identifier for the batched object.

    Returns:
        (str): name of the file in the s3 bucket (key).

    """
    # Pickle data
    data = pickle.dumps(data)

    # s3 setup
    s3 = boto3.resource("s3")
    filename = f"{prefix}.pickle"
    obj = s3.Object(bucket, filename)
    obj.put(Body=data)

    return filename


def s3_to_pickle(bucket, prefix):
    """Loads a pickled file from s3.

    Args:
       bucket (str): Name of the s3 bucket.
       prefix (str): Name of the pickled file.

    """
    s3 = boto3.resource("s3")
    obj = s3.Object(bucket, f"{prefix}.pickle")
    return pickle.loads(obj.get()["Body"].read())
