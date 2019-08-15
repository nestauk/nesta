import pandas as pd
import itertools
from collections import Counter
##string length
def string_length(input):#, column):
    '''string_length
    Calculates the character-length of strings.

    Args:
        input (:obj:`iter` of :obj:`str`): A sequence of string objects.


    Returns:
        flat_length_series (:obj:`pandas.core.series.Series`): A series onject of string lengths.
    '''

    series = pd.Series(input)

    flat_length_list = series[~pd.isnull(series)].str.len().values
    flat_length_series = pd.Series(flat_length_list)

    return flat_length_series


def string_counter(input):
    '''string_counter?


    Args:
        input (:obj:`iter` of :obj:`list`): A sequence of string objects.

    Returns:
        count_output (:obj:`pandas.core.series.Series`): A series object of strings and string freuqencies.
    '''

    series = pd.Series(input)
    count = Counter(series)
    count_output = pd.Series(count)
    return count_output

##keyword
# def delimiter_splitter(n, delimiter):
#     '''delimiter_splitter
#     Args:
#         n (:obj:`str`): A string.
#         delimiter (:obj:`str`): A string of a delimiter (punctuation, white space, etc).
#
#     Returns:
#         output (:obj:`list`): A list of string tokens.
#
#     '''
#
#     if delimiter in n:
#         if delimiter+' ' in n:
#             output = n.split(delimiter+' ')
#             return output
#         else:
#             output = n.split(delimiter)
#             return output
#     else:
#         output = [n]
#         return output
#
# def split_and_replace(input, delimiter):
#
#     '''split_and_replace
#
#     Args:
#         input (:obj:`iter` of :obj:`list`): A sequence of string objects.
#         delimiter (:obj:`str`): A string of a delimiter (punctuation, white space, etc).
#
#     Returns:
#         flat_output_clean (:obj:`list`): A list of string tokens.
#     '''
#
#     series = pd.Series(input)
#     output = input.dropna().apply(lambda x: delimiter_splitter(x,delimiter) if type(x) == str else None).values.tolist()
#     flat_output = [val for sublist in output for val in sublist if val != '']
#     flat_output_clean = [val.lower().replace(".", "") for val in flat_output if '?' not in val]
#
#     return flat_output_clean
