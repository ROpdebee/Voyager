"""Pipeline segment to collect raw API page responses from Ansible Galaxy."""
from typing import Set

import json

from pathlib import Path

from tqdm import tqdm

from config import MainConfig
from models.galaxy import GalaxyAPIPage
from pipeline.base import ResultMap, Stage
from services.galaxy import GalaxyAPI


class GalaxySearch(Stage[GalaxyAPIPage, MainConfig]):
    """Discover roles to put in the dataset."""

    dataset_dir_name = 'GalaxySearch'

    def run(self) -> ResultMap[GalaxyAPIPage]:
        """Run the stage."""
        galaxy_api = GalaxyAPI()
        it_roles = galaxy_api.search_roles()

        if not self.config.progress:
            return ResultMap(it_roles)
        return ResultMap(tqdm(it_roles, desc='Searching roles'))

    def report_results(self, results: ResultMap[GalaxyAPIPage]) -> None:
        """Report statistics on loaded pages."""
        print('--- Role Search ---')
        print(f'Loaded {len(results)} pages of API results')
        print(
            'Reported total count of roles: '
            f'{results["1"].response["count"]}')

    def dump(self, results: ResultMap[GalaxyAPIPage], out: Path) -> None:
        """Dump each page individually to a JSON file with its content."""
        for page_num in results:
            fpath = out / 'galaxy_search' / f'page_{page_num}.json'
            fpath.write_text(json.dumps(results[page_num]))
