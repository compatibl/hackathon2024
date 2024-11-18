from typing import Any
import numpy as np
import pandas as pd

AGREEMENT_THRESHOLD = 0.20  # we want the top value to come up at least 20% of the time to avoid hallucinations

def try_str_to_float(x: str) -> str:
    """
    Converts to int (if str is an integer) or float (if number is not an integer) then back to str; else returns original str
    """
    try:
        if int(x) == float(x):
            return str(int(x))
    except ValueError:
        pass
    try:
        return str(float(x))
    except ValueError:
        return x

def manage_results(results_list: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Manage conflicts from different results from calling the LLM.
    :param results_list: a list of results of multiple runs (e.g. list of json outputs)
    :return: a single json_output
    """
    # cast types to float if possible
    for i in range(len(results_list)):
        for key in results_list[i]:
            results_list[i][key] = try_str_to_float(results_list[i][key])

    df = pd.DataFrame(results_list)
    print("\n" + df.to_string())

    # get most common results
    modal_results = df.mode().iloc[0].dropna()

    # make sure each results has agreement above AGREEMENT_THRESHOLD
    for key, val in modal_results.items():
        count = sum(df[key] == val)
        if count / len(df) < AGREEMENT_THRESHOLD:
            print(key, count, len(df))
            modal_results[key] = np.nan

    modal_results.dropna(inplace=True)

    # cast types to str
    modal_results = modal_results.astype("str")

    json_output = modal_results.to_dict()
    return json_output


# use to select which features to rerun - all
def get_all_features(*args):
    return None, None


# use to select which features to rerun - non-empty ones
def get_non_empty_features(params_list):

    if not params_list:
        return None, None

    features = pd.DataFrame(params_list).columns.to_list()

    return len(features), features


if __name__ == "__main__":
    dummy_list = [
        {"label_a": "a", "label_b": "2", "label_c": "1", "label_d": "10", "label_e": "1", "label_f": "0.2"},
        {"label_a": "a", "label_b": "1", "label_c": "2", "label_f": "0.20"},
        {"label_a": "a", "label_b": "1", "label_c": "3", "label_d": "10","label_f": "0.20"},
        {"label_a": "a", "label_b": "1", "label_c": "4", },
        {"label_a": "b", "label_b": "1", "label_c": "5", "label_d": "10"},
    ]
    res = manage_results(dummy_list)
    print(res)
