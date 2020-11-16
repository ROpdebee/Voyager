"""Discovery part of the pipeline."""
from typing import Set

from tqdm import tqdm

from config import DiscoverConfig
from models.galaxy import GalaxyRole
from pipeline.base import ResultMap, Stage
from services.galaxy import GalaxyAPI


class Discover(Stage[GalaxyRole, DiscoverConfig]):
    """Discover roles to put in the dataset."""

    cache_file_name = 'roles.json'

    def run(self) -> ResultMap[GalaxyRole]:
        """Run the stage."""
        galaxy_api = GalaxyAPI()
        it_roles = galaxy_api.search_roles(limit=self.config.count)

        if not self.config.progress:
            return ResultMap(it_roles)
        return ResultMap(tqdm(
                it_roles, desc='Searching roles', total=self.config.count))

    def report_results(self, results: ResultMap[GalaxyRole]) -> None:
        """Report statistics on gathered roles."""
        max_download = 0
        min_download = float('inf')

        authors: Set[str] = set()

        for role in results.values():
            max_download = max(max_download, role.download_count)
            min_download = min(min_download, role.download_count)

            authors.add(role.github_user)

        print('--- Role Discovery ---')
        print(
                f'Discovered {len(results)} roles written by {len(authors)}'
                ' authors.')
        print(f'Max download count: {max_download}')
        print(f'Min download count: {min_download}')
