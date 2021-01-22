"""Discovery part of the pipeline."""
from typing import Any, Dict, Iterator, Mapping, Sequence, Set, cast

import itertools

from tqdm import tqdm

from config import ExtractRoleMetadataConfig
from models.role_metadata import GalaxyMetadata, MetadataMap
from models.galaxy import GalaxyAPIPage
from models.serialize import CONVERTER
from pipeline.base import ResultMap, Stage, CacheMiss
from pipeline.collect.galaxy_scrape import GalaxyScrape


from pprint import pprint

class ExtractRoleMetadata(
        Stage[GalaxyMetadata, ExtractRoleMetadataConfig], requires=GalaxyScrape
):
    """Extract metadata from the collected roles."""

    dataset_dir_name = 'GalaxyMetadata'

    def run(
            self, galaxy_scrape: ResultMap[GalaxyAPIPage]
    ) -> ResultMap[GalaxyMetadata]:
        """Run the stage."""
        metadata_map = MetadataMap(list(galaxy_scrape._storage.values()))
        metadata_map.verify_schema()

        num_roles = cast(int, galaxy_scrape['roles/1'].response['count'])

        meta = GalaxyMetadata.from_metamap(metadata_map)

        return ResultMap([meta])

    def report_results(self, results: ResultMap[GalaxyMetadata]) -> None:
        """Report statistics on gathered roles."""

        print('--- Role Metadata Extraction ---')
        attrs = [
                'community_surveys', 'content', 'namespaces',
                'provider_namespaces', 'repositories', 'roles', 'tags',
                'users']
        for attr in attrs:
            print(f'#{attr}: {len(getattr(results["dummy"], attr))}')


    def store_in_dataset(self, results: ResultMap[GalaxyMetadata]) -> None:
        """Store the results of a stage in the dataset."""
        dataset_dir_path = self.config.output_directory / self.dataset_dir_name
        dataset_dir_path.mkdir(exist_ok=True, parents=True)
        results['dummy'].dump(dataset_dir_path)

    def load_from_dataset(self) -> ResultMap[GalaxyMetadata]:
        """Load the results of a previous run from the dataset.

        Raises `CacheMiss` when not found in the dataset.
        """
        dataset_dir_path = self.config.output_directory / self.dataset_dir_name

        try:
            return ResultMap([GalaxyMetadata.lazy_load('dummy', dataset_dir_path)])
        except:
            raise CacheMiss()
