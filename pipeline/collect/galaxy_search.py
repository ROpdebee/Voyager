"""Pipeline segment to collect raw API page responses from Ansible Galaxy."""
from typing import Set

import json

from pathlib import Path

from tqdm import tqdm

from config import MainConfig
from models.galaxy import GalaxySearchAPIPage
from pipeline.base import ResultMap, Stage
from services.galaxy import GalaxyAPI


class GalaxySearch(Stage[GalaxySearchAPIPage, MainConfig]):
    """Discover roles to put in the dataset."""

    dataset_dir_name = 'GalaxySearch'

    def run(self) -> ResultMap[GalaxySearchAPIPage]:
        """Run the stage."""
        galaxy_api = GalaxyAPI()
        it_pages = galaxy_api.search_roles()

        if not self.config.progress:
            return ResultMap(it_pages)
        return ResultMap(tqdm(it_pages, desc='Searching roles'))

    def report_results(self, results: ResultMap[GalaxySearchAPIPage]) -> None:
        """Report statistics on loaded pages."""
        print('--- Role Search ---')
        print(f'Loaded {len(results)} pages of API results')
        print(
            'Reported total count of roles: '
            f'{results["1"].response["count"]}')
