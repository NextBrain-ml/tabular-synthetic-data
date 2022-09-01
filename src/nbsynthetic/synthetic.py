# Copyright 2022 Softpoint Consultores SL. All Rights Reserved.
#
# Licensed under MIT License (the "License");
# you may not use this file except in compliance with the License.
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

import warnings
import numpy as np
import pandas as pd
from pandas.core.dtypes.dtypes import CategoricalDtype
from sklearn.pipeline import make_pipeline
from sklearn.compose import make_column_selector as selector
from sklearn.preprocessing import MinMaxScaler, \
    QuantileTransformer, KBinsDiscretizer

warnings.filterwarnings('ignore', '.*do not.*', )
pd.options.mode.chained_assignment = None


def columns_type(df: pd.DataFrame):
    """
    Args:
        df(pd.DataFrame):
            input data

    Returns:
        two lists with numerical and 
        categorical columns names.
    """
    numerical_columns_selector = selector(
        dtype_exclude=CategoricalDtype
    )
    categorical_columns_selector = selector(
        dtype_include=CategoricalDtype
    )
    numerical_columns = numerical_columns_selector(df)
    categorical_columns = categorical_columns_selector(df)
    return numerical_columns, categorical_columns


def data_transformation(
    df: pd.DataFrame,
    numerical_columns,
    categorical_columns,
):
    """
    Args:
        df(pd.DataFrame):
            input data
        numerical_columns:
            list with numerical columns names 
        categorical_columns:
            list with categorical columns name

    Returns:
        prepared dataframe for input"""

    categorical_scaler = make_pipeline(
        MinMaxScaler(
            feature_range=(-1, 1),
            clip=True
        )
    )

    if len(df) > 99:
        n_quantiles = 100
    else:
        n_quantiles = len(df)

    numerical_scaler = make_pipeline(
        # A quantile transform will map a variable’s
        # probability distribution to another probability
        # distribution.By performing a rank
        # transformation, a quantile transform smooths out
        # unusual distributions and is less influenced by
        # outliers than scaling methods.
        # Ref: https://scikit-learn.org/stable/modules/preprocessing.html#preprocessing-transformer
        QuantileTransformer(
            n_quantiles=n_quantiles,
            output_distribution='uniform',
        ),
        MinMaxScaler(
            feature_range=(-1, 1),
            clip=True
        )
    )
    scaled_X = df.copy()
    for cat_c in categorical_columns:
        scaled_X[cat_c] = categorical_scaler.fit_transform(
            np.array(df[cat_c]).reshape(-1, 1)
        ).flatten()

    for num_c in numerical_columns:
        scaled_X[num_c] = numerical_scaler.fit_transform(
            np.array(df[num_c]).reshape(-1, 1)
        ).flatten()

    return np.array(scaled_X),\
        categorical_scaler, numerical_scaler


def generate_data(
    df: pd.DataFrame,
    x_synthetic,
    categorical_columns,
    numerical_columns,
    categorical_scaler,
    numerical_scaler
):
    """
    Args:
        df(pd.DataFrame):
            input data
        x_synthetic:
            data generated by GAN network  
        categorical_columns:
            list with categorical columns name  
        numerical_columns:
                list with numerical columns names     
        categorical_scaler: 
                scikit learn transfomed used for
                input data preparation for categorical
                features
        numerical_scaler: 
                scikit learn transfomed used for
                input data preparation for numerical
                features
    Returns:
        Synthetic dataframe (pd.DataFrame)"""

    newdf = pd.DataFrame(
        x_synthetic,
        columns=df.columns
    )
    for cat_c in categorical_columns:
        if np.unique(df[cat_c]).shape[0] > 1:
            newdf[cat_c] = categorical_scaler.inverse_transform(
                np.array(
                    newdf[cat_c]).reshape(-1, 1)
            )
            kbins = KBinsDiscretizer(
                n_bins=np.unique(df[cat_c]).shape[0],
                encode='ordinal',
                strategy='uniform'
            )
            newdf[cat_c] = kbins.fit_transform(
                np.array(newdf[cat_c]).reshape(-1, 1)
            ).astype(int)
            newdf[cat_c] = newdf[cat_c].astype('category')
        else:
            pass

    for num_c in numerical_columns:
        newdf[num_c] = numerical_scaler.inverse_transform(
            np.array(
                newdf[num_c]).reshape(-1, 1)
        ).flatten().astype('float64')

    for cat_c in categorical_columns:
        if np.unique(df[cat_c]).shape[0] == 2:
            newdf[cat_c].replace(
                [np.unique(newdf[cat_c])[0],
                 np.unique(newdf[cat_c])[1]],
                [np.unique(df[cat_c])[0],
                 np.unique(df[cat_c])[1]],
                inplace=True
            )
        else:
            pass

    return newdf


def synthetic_data(
    GAN,
    df: pd.DataFrame,
    samples: int,
    initial_lr=0.0002,
    dropout=0.5,
    batch_size=48,
    epochs=10
):
    """Args:

          GAN (keras.model):
            Vanilla GAN
          df (pd.DataFrame): 
            input data frame
          samples (int):
            number of instances for the
            synthetic dataset
          initial_lr:
              initial learning rate for NN
          droput:
              apply Dropout to input 

      Returns:

          Synthetic dataframe (pd.DataFrame)
          """

    if sum(pd.isnull(df).sum()) > 0:
        raise ValueError(
            'There are nan values in your dataset. You have to remove or replace them.')

    for c in df.columns:
        if isinstance(df[c].dtype, object) and isinstance(df.iloc[0][c], str):
            raise ValueError(
                f"Column '{c}' contains strings. We suggest to encode it. ")

    n_features = len(df.columns)

    numerical_columns,\
        categorical_columns = columns_type(df)
    scaled_X,\
        categorical_scaler,\
        numerical_scaler = data_transformation(
            df,
            numerical_columns,
            categorical_columns
        )

    def train_gan(
        scaled_X,
        n_features,
        initial_lr,
        dropout
    ):
        
        # validate parameters
        arrays = tuple(np.array(scaled_X))
        if not arrays:
            raise ValueError('`arrays` must not be empty.')
        for a in arrays:
            if not hasattr(a, 'shape'):
                raise ValueError('`arrays` must be numpy-like arrays.')
            if len(a.shape) < 1:
                raise ValueError('`arrays` must be at least 1-d arrays.')
        data_length = len(arrays[0])
        for a in arrays[1:]:
            if len(a) != data_length:
                raise ValueError('`arrays` must have the same data length.')

        gan = GAN(
            number_of_features=n_features,
            learning_rate=initial_lr,
            dropout=dropout,
        )
        G_loss,\
            D_loss = gan.train(
                scaled_data=scaled_X,
                epochs=epochs,
                batch_size=batch_size,
            )
        return G_loss, D_loss, gan

    G_loss,\
        D_loss,\
        gan = train_gan(
            scaled_X,
            n_features,
            initial_lr,
            dropout
        )
    if G_loss > 1:
        G_loss,\
            D_loss,\
            gan = train_gan(
                scaled_X,
                n_features,
                initial_lr/10,
                dropout
            )
    else:
        if G_loss > 1:
            G_loss,\
                D_loss,\
                gan = train_gan(
                    scaled_X,
                    n_features,
                    initial_lr/100,
                    dropout
                )
        else:
            pass

    x_synthetic,\
        y_synthetic = gan.create_fake_samples(
            batch_size=samples
        )
    newdf = generate_data(
        df,
        x_synthetic,
        categorical_columns,
        numerical_columns,
        categorical_scaler,
        numerical_scaler
    )
    for c in numerical_columns:
        scaler = MinMaxScaler(
            feature_range=(
                np.min(df[c]),
                np.max(df[c])
            ),
            clip=True
        )
        newdf[c] = scaler.fit_transform(
            np.array(
                newdf[c]).reshape(-1, 1)
        ).flatten()

    return newdf
