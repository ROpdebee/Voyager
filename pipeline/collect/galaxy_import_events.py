"""Pipeline segment to collect raw API pages of role import events."""
from typing import Set

import json

from pathlib import Path

from tqdm import tqdm

from config import MainConfig
from models.galaxy import GalaxyImportEventAPIResponse, GalaxySearchAPIPage
from pipeline.base import ResultMap, Stage
from pipeline.collect.galaxy_search import GalaxySearch
from services.galaxy import GalaxyAPI


class GalaxyImportEvents(
        Stage[GalaxyImportEventAPIResponse, MainConfig],
        requires=GalaxySearch):
    """Discover roles to put in the dataset."""

    dataset_dir_name = 'GalaxyImportEvents'

    def run(
            self, galaxy_search: ResultMap[GalaxySearchAPIPage]
    ) -> ResultMap[GalaxyImportEventAPIResponse]:
        """Run the stage."""
        role_ids: List[int] = []
        for page_num in galaxy_search:
            page = galaxy_search[page_num]
            role_ids.extend(role['id'] for role in page.response['results'])

        galaxy_api = GalaxyAPI()
        it_role_events = galaxy_api.load_import_events(role_ids)

        if not self.config.progress:
            return ResultMap(it_role_events)
        return ResultMap(tqdm(
                it_role_events, desc='Loading import events',
                total=len(role_ids)))

    def report_results(
            self, results: ResultMap[GalaxyImportEventAPIResponse]
    ) -> None:
        """Report statistics on loaded pages."""
        print('--- Role Import Events ---')
        print(f'Loaded import events for {len(results)} roles')
