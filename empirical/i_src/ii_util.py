#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import IPython
from sklearn.preprocessing import LabelEncoder
import numpy as np
import gc
import matplotlib.pyplot as plt


def display(*dfs, head=True):
    """
    Dynamically display on or more pandas DF in an interactive Python env. such as
    Jupyter Notebook. The "IPython.display.display(..)" Ensures the DF renders
    properly in Jupyter, allowing multiple outputs in a single cell

    Args:
        *dfs: One or more pandas DataFrames to display.
        head (bool, optional): If True, displays only the first five rows of each DataFrame.
                               If False, displays the full DataFrame. Defaults to True.
    Returns:
        None: Outputs the DataFrame(s) directly in the notebook.
    """

    for df in dfs:
        IPython.display.display(df.head() if head else df)


# def on_kaggle():
#     """
#     Check if the code is running in a Kaggle notebook.

#     Returns:
#         bool: True if running in a Kaggle environment, False otherwise.
#     """

#     return "KAGGLE_KERNEL_RUN_TYPE" in os.enviorn


def reduce_mem_usage(df: pd.DataFrame, verbose=False) -> pd.DataFrame:
    """
    Reduce memory usage of a pandas DataFrame by downcasting numerical columns.
    Downcasting reduces the data type of a variable to a smaller, more memory-efficient
    type without losing information.

    Args:
        df (pd.DataFrame): The DataFrame to optimize.
        verbose (bool, optional): If True, prints memory usage reduction details. Defaults to False.

    Returns:
        pd.DataFrame: The optimized DataFrame with reduced memory usage.
    """

    start_mem = df.memory_usage().sum() / 1024**2
    int_columns = df.select_dtypes(include=["int"]).columns
    float_columns = df.select_dtypes(include=["float"]).columns

    for col in int_columns:
        df[col] = pd.to_numeric(df[col], downcast="integer")

    for col in float_columns:
        df[col] = pd.to_numeric(df[col], downcast="float")

    end_mem = df.memory_usage().sum() / 1024**2
    if verbose:
        print(
            "Mem. usage decreased to {:5.2f} Mb ({:.1f}% reduction)".format(
                end_mem, 100 * (start_mem - end_mem) / start_mem
            )
        )
    return df


def read_csv_data(path: str, file_name: str, df_name: str) -> pd.DataFrame:
    """
    Reads a CSV file and prints its name and shape.

    Args:
        path (str): Directory path of the CSV file.
        file_name (str): CSV file name.
        df_name (str): Name to associate with the DataFrame.

    Returns:
        pd.DataFrame: The loaded DataFrame.
    """

    df = pd.read_csv(f"{path}/{file_name}").pipe(reduce_mem_usage)
    print(f"{df_name} shape: {df.shape}")

    return df


def encode_categorical(df, cols):
    """
    Encodes specified categorical columns in the DataFrame using LabelEncoder.

    This function applies LabelEncoder to the specified columns, encoding non-null
    categorical values as integers while leaving NaN values untouched.

    Args:
        df (pd.DataFrame): The DataFrame containing the data to be encoded.
        cols (list): A list of column names (strings) to be encoded.

    Returns:
        pd.DataFrame: The DataFrame with the specified categorical columns encoded.

    Example:
        df = encode_categorical(df, ['category_column'])
    """

    for col in cols:
        # Leave NaN as it is.
        le = LabelEncoder()
        not_null = df[col][df[col].notnull()]
        df[col] = pd.Series(le.fit_transform(not_null), index=not_null.index)

    return df


def extract_num(ser):
    """
    Extracts the first sequence of digits from each string in a pandas Series
    and converts the result to integers.

    Args:
        ser (pd.Series): A pandas Series containing strings from which digits will be extracted.

    Returns:
        pd.Series: A pandas Series with the extracted integers.
    """

    return ser.str.extract(r"(\d+)").astype(np.int16)


# def days_pred(submission):
#     x = submission.shape[1] - 1
#     return x


def reshape_sales(sales, submission, d_thresh=0, verbose=True):
    # melt sales data, get it ready for training
    id_columns = ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]

    # get product table.
    product = sales[id_columns]

    sales = sales.melt(
        id_vars=id_columns,
        var_name="d",
        value_name="demand",
    )
    sales = reduce_mem_usage(sales)

    # separate test dataframes.
    vals = submission[submission["id"].str.endswith("validation")]
    evals = submission[submission["id"].str.endswith("evaluation")]

    # change column names.
    DAYS_PRED = submission.shape[1] - 1
    vals.columns = ["id"] + [f"d_{d}" for d in range(1914, 1914 + DAYS_PRED)]
    evals.columns = ["id"] + [f"d_{d}" for d in range(1942, 1942 + DAYS_PRED)]

    # merge with product table
    evals["id"] = evals["id"].str.replace("_evaluation", "_validation")
    vals = vals.merge(product, how="left", on="id")
    evals = evals.merge(product, how="left", on="id")
    evals["id"] = evals["id"].str.replace("_validation", "_evaluation")

    if verbose:
        print("validation")
        display(vals)

        print("evaluation")
        display(evals)

    vals = vals.melt(id_vars=id_columns, var_name="d", value_name="demand")
    evals = evals.melt(id_vars=id_columns, var_name="d", value_name="demand")

    sales["part"] = "train"
    vals["part"] = "validation"
    evals["part"] = "evaluation"

    data = pd.concat([sales, vals, evals], axis=0)

    del sales, vals, evals

    data["d"] = extract_num(data["d"])
    data = data[data["d"] >= d_thresh]

    # delete evaluation for now.
    data = data[data["part"] != "evaluation"]

    gc.collect()

    if verbose:
        print("data")
        display(data)

    return data


def merge_calendar(data, calendar):
    calendar = calendar.drop(["weekday", "wday", "month", "year"], axis=1)
    return data.merge(calendar, how="left", on="d")


def merge_prices(data, prices):
    return data.merge(prices, how="left", on=["store_id", "item_id", "wm_yr_wk"])


def add_demand_features(df, DAYS_PRED=None):
    for diff in [0, 1, 2]:
        shift = DAYS_PRED + diff
        df[f"shift_t{shift}"] = df.groupby(["id"])["demand"].transform(
            lambda x: x.shift(shift)
        )

    for window in [7, 30, 60, 90, 180]:
        df[f"rolling_std_t{window}"] = df.groupby(["id"])["demand"].transform(
            lambda x: x.shift(DAYS_PRED).rolling(window).std()
        )

    for window in [7, 30, 60, 90, 180]:
        df[f"rolling_mean_t{window}"] = df.groupby(["id"])["demand"].transform(
            lambda x: x.shift(DAYS_PRED).rolling(window).mean()
        )

    for window in [7, 30, 60]:
        df[f"rolling_min_t{window}"] = df.groupby(["id"])["demand"].transform(
            lambda x: x.shift(DAYS_PRED).rolling(window).min()
        )

    for window in [7, 30, 60]:
        df[f"rolling_max_t{window}"] = df.groupby(["id"])["demand"].transform(
            lambda x: x.shift(DAYS_PRED).rolling(window).max()
        )

    df["rolling_skew_t30"] = df.groupby(["id"])["demand"].transform(
        lambda x: x.shift(DAYS_PRED).rolling(30).skew()
    )
    df["rolling_kurt_t30"] = df.groupby(["id"])["demand"].transform(
        lambda x: x.shift(DAYS_PRED).rolling(30).kurt()
    )
    return df


def add_price_features(df):
    df["shift_price_t1"] = df.groupby(["id"])["sell_price"].transform(
        lambda x: x.shift(1)
    )
    df["price_change_t1"] = (df["shift_price_t1"] - df["sell_price"]) / (
        df["shift_price_t1"]
    )
    df["rolling_price_max_t365"] = df.groupby(["id"])["sell_price"].transform(
        lambda x: x.shift(1).rolling(365).max()
    )
    df["price_change_t365"] = (df["rolling_price_max_t365"] - df["sell_price"]) / (
        df["rolling_price_max_t365"]
    )

    df["rolling_price_std_t7"] = df.groupby(["id"])["sell_price"].transform(
        lambda x: x.rolling(7).std()
    )
    df["rolling_price_std_t30"] = df.groupby(["id"])["sell_price"].transform(
        lambda x: x.rolling(30).std()
    )
    return df.drop(["rolling_price_max_t365", "shift_price_t1"], axis=1)


def add_time_features(df, dt_col):
    df[dt_col] = pd.to_datetime(df[dt_col])
    attrs = [
        "year",
        "quarter",
        "month",
        "week",
        "day",
        "dayofweek",
    ]

    for attr in attrs:
        dtype = np.int16 if attr == "year" else np.int8
        df[attr] = getattr(df[dt_col].dt, attr).astype(dtype)

    df["is_weekend"] = df["dayofweek"].isin([5, 6]).astype(np.int8)
    return df


class CustomTimeSeriesSplitter:
    def __init__(self, DAYS_PRED, n_splits=5, train_days=80, test_days=20, day_col="d"):
        self.DAYS_PRED = DAYS_PRED
        self.n_splits = n_splits
        self.train_days = train_days
        self.test_days = test_days
        self.day_col = day_col

    def split(self, X, y=None, groups=None):
        SEC_IN_DAY = 3600 * 24
        sec = (X[self.day_col] - X[self.day_col].iloc[0]) * SEC_IN_DAY
        duration = sec.max()

        train_sec = self.train_days * SEC_IN_DAY
        test_sec = self.test_days * SEC_IN_DAY
        total_sec = test_sec + train_sec

        if self.n_splits == 1:
            train_start = duration - total_sec
            train_end = train_start + train_sec

            train_mask = (sec >= train_start) & (sec < train_end)
            test_mask = sec >= train_end

            yield sec[train_mask].index.values, sec[test_mask].index.values

        else:
            # step = (duration - total_sec) / (self.n_splits - 1)
            step = self.DAYS_PRED * SEC_IN_DAY

            for idx in range(self.n_splits):
                # train_start = idx * step
                shift = (self.n_splits - (idx + 1)) * step
                train_start = duration - total_sec - shift
                train_end = train_start + train_sec
                test_end = train_end + test_sec

                train_mask = (sec > train_start) & (sec <= train_end)

                if idx == self.n_splits - 1:
                    test_mask = sec > train_end
                else:
                    test_mask = (sec > train_end) & (sec <= test_end)

                yield sec[train_mask].index.values, sec[test_mask].index.values

    def get_n_splits(self):
        return self.n_splits


def show_cv_days(cv, X, dt_col, day_col):
    for ii, (tr, tt) in enumerate(cv.split(X)):
        print(f"----- Fold: ({ii + 1} / {cv.n_splits}) -----")
        tr_start = X.iloc[tr][dt_col].min()
        tr_end = X.iloc[tr][dt_col].max()
        tr_days = X.iloc[tr][day_col].max() - X.iloc[tr][day_col].min() + 1

        tt_start = X.iloc[tt][dt_col].min()
        tt_end = X.iloc[tt][dt_col].max()
        tt_days = X.iloc[tt][day_col].max() - X.iloc[tt][day_col].min() + 1

        df = pd.DataFrame(
            {
                "start": [tr_start, tt_start],
                "end": [tr_end, tt_end],
                "days": [tr_days, tt_days],
            },
            index=["train", "test"],
        )

        display(df)


def plot_cv_indices(cv, X, dt_col, lw=10):
    n_splits = cv.get_n_splits()
    _, ax = plt.subplots(figsize=(20, n_splits))

    # Generate the training/testing visualizations for each CV split
    for ii, (tr, tt) in enumerate(cv.split(X)):
        # Fill in indices with the training/test groups
        indices = np.array([np.nan] * len(X))
        indices[tt] = 1
        indices[tr] = 0

        # Visualize the results
        ax.scatter(
            X[dt_col],
            [ii + 0.5] * len(indices),
            c=indices,
            marker="_",
            lw=lw,
            cmap=plt.cm.coolwarm,
            vmin=-0.2,
            vmax=1.2,
        )

    # Formatting
    MIDDLE = 15
    LARGE = 20
    ax.set_xlabel("Datetime", fontsize=LARGE)
    ax.set_xlim([X[dt_col].min(), X[dt_col].max()])
    ax.set_ylabel("CV iteration", fontsize=LARGE)
    ax.set_yticks(np.arange(n_splits) + 0.5)
    ax.set_yticklabels(list(range(n_splits)))
    ax.invert_yaxis()
    ax.tick_params(axis="both", which="major", labelsize=MIDDLE)
    ax.set_title("{}".format(type(cv).__name__), fontsize=LARGE)
    return ax


def train_lgb(bst_params, fit_params, X, y, cv, drop_when_train=None):
    pass


def rmse(y_true, y_pred):
    pass


def make_submission(test, submission):
    pass


def main():
    pass


if __name__ == "__main__":
    main()
