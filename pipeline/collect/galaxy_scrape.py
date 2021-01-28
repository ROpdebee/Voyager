"""Pipeline segment to collect raw API page responses from Ansible Galaxy."""
from typing import Any, Dict, Iterator, List, Optional, Set, cast

import json

from pathlib import Path

from tqdm import tqdm

from config import MainConfig
from models.galaxy import GalaxyAPIPage
from pipeline.base import ResultMap, Stage
from services.galaxy import GalaxyAPI


API_URLS = {
    'namespaces': 'https://galaxy.ansible.com/api/v1/namespaces/',
    'platforms': 'https://galaxy.ansible.com/api/v1/platforms/',
    'provider_namespaces': 'https://galaxy.ansible.com/api/v1/provider_namespaces/',
    'repositories': 'https://galaxy.ansible.com/api/v1/repositories/',
    'roles': 'https://galaxy.ansible.com/api/v1/roles/',
    'role_search': 'https://galaxy.ansible.com/api/v1/search/roles/',
    'tags': 'https://galaxy.ansible.com/api/v1/tags/',
    # 'users': 'https://galaxy.ansible.com/api/v1/users/',
    'community_surveys': 'https://galaxy.ansible.com/api/v1/community_surveys/repository/',
    'content': 'https://galaxy.ansible.com/api/v1/content/',  # Mainly for more detailed quality scores.
}

PAGE_SIZES = {
    'roles': 250,
    'content': 100,
}


class GalaxyScrape(Stage[GalaxyAPIPage, MainConfig]):
    """Discover roles to put in the dataset."""

    dataset_dir_name = 'GalaxyScrape'

    def run(self) -> ResultMap[GalaxyAPIPage]:
        """Run the stage."""
        all_results: List[GalaxyAPIPage] = []
        for name, url in API_URLS.items():
            pages = self.load_pages(name, url)
            all_results.extend(pages)

        # Might happen that some roles in the role page fail to load because
        # of 500 Internal Server Error at Galaxy side. Can't fix this. The
        # role page includes more information though, and we've got both the
        # role search and the roles themselves. Any roles in the search page
        # that aren't present in the role pages need to be loaded separately
        # too. We'll give these incremental page numbers.
        all_results = self.import_missing_roles(all_results)
        return ResultMap(all_results)


    def import_missing_roles(self, results: List[GalaxyAPIPage]) -> List[GalaxyAPIPage]:
        role_ids: Set[int] = set()
        role_search_ids: Set[int] = set()
        highest_role_page_num = 0

        for page in results:
            if page.page_type == 'roles':
                highest_role_page_num = max(
                        highest_role_page_num, page.page_num)
                for role in cast(List[Dict[str, Any]], page.response['results']):
                    role_ids.add(role['id'])

            if page.page_type == 'role_search':
                for role in cast(List[Dict[str, Any]], page.response['results']):
                    role_search_ids.add(role['id'])

        missing_ids = role_search_ids - role_ids

        new_pages: List[Any] = []
        api = GalaxyAPI()
        for role_id in tqdm(missing_ids, desc='Loading missing roles'):
            role_page = api.load_role(role_id)
            if role_page is not None:
                new_pages.append(role_page)

        # Imitate the JSON of the role page.
        page_content = {'results': new_pages}
        results.append(GalaxyAPIPage(
                'roles', highest_role_page_num + 1, json.dumps(page_content)))

        return results


    def load_pages(self, page_name: str, page_url: str) -> List[GalaxyAPIPage]:
        cached_results = self.try_load_pages(page_name)
        if cached_results is not None:
            return cached_results

        api = GalaxyAPI()
        page_size = PAGE_SIZES.get(page_name, 500)
        it_pages = api.load_pages(page_name, page_url, page_size=page_size)
        pbar = tqdm(
                desc=f'Loading {page_name} pages', unit='pages', leave=False)
        results: List[GalaxyAPIPage] = []

        total_set = False
        for page in it_pages:
            if not total_set:
                pbar.total = (cast(int, page.response['count']) // page_size) + 1
                total_set = True
            pbar.update(1)
            results.append(page)

        pbar.close()

        self.save_pages(results)
        return results

    def save_pages(self, results: List[GalaxyAPIPage]) -> None:
        dataset_dir_path = self.config.output_directory / self.dataset_dir_name
        for page in results:
            page.dump(dataset_dir_path)

    def try_load_pages(self, page_name: str) -> Optional[List[GalaxyAPIPage]]:
        dataset_dir_path = self.config.output_directory / self.dataset_dir_name
        existing_files = list(dataset_dir_path.glob(f'{page_name}_*.json'))
        if not existing_files:
            return None

        cached_results = []
        for file in existing_files:
            comps = file.stem.split('_')
            file_type = '_'.join(comps[:-1])
            page_num = int(comps[-1])
            cached_results.append(
                    GalaxyAPIPage.load(f'{file_type}/{page_num}', file))

        return cached_results

    def report_results(self, results: ResultMap[GalaxyAPIPage]) -> None:
        """Report statistics on loaded pages."""
        print('--- Galaxy Scrape ---')
        print(f'Loaded {len(results)} pages of API results')
