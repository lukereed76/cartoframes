import pandas as pd

from .repository.dataset_repo import get_dataset_repo
from .repository.variable_repo import get_variable_repo

_DATASET_ID_FIELD = 'id'


class Dataset(pd.Series):

    @property
    def _constructor(self):
        return Dataset

    @property
    def _constructor_expanddim(self):
        return Datasets

    @staticmethod
    def by_id(dataset_id):
        return get_dataset_repo().by_id(dataset_id)

    def variables(self):
        return get_variable_repo().by_dataset(self[_DATASET_ID_FIELD])

    def __eq__(self, other):
        return self.equals(other)

    def __ne__(self, other):
        return not self == other


class Datasets(pd.DataFrame):

    @property
    def _constructor(self):
        return Datasets

    @property
    def _constructor_sliced(self):
        return Dataset

    @staticmethod
    def all():
        return get_dataset_repo().all()

    @staticmethod
    def by_id(dataset_id):
        return Dataset.by_id(dataset_id)

    def __eq__(self, other):
        return self.equals(other)

    def __ne__(self, other):
        return not self == other
