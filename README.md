# Voyager: Explorer of the (Ansible) Galaxy

Voyager is a tool to discover and collect a dataset of Ansible roles from [Ansible Galaxy](https://galaxy.ansible.com) and extract structural changes between versions of a role.

## Requirements
- Python >= 3.8
- [Poetry](https://python-poetry.org/docs/#installation)

## Installing
- `cd /path/to/voyager`
- `poetry install`

## Running
- `poetry run -- python main.py`
- Check the help text.

### Examples
Assuming `poetry shell` is spawned.

- `python main.py --progress --report --dataset my_data galaxy-scrape`
  Create a new dataset named `my_data` and start harvesting data from the Ansible Galaxy API.
  Show progress while searching for roles, include a report on the gathered roles.
- `python main.py --dataset my_data extract-role-metadata`
  Extract the harvested API pages into the Galaxy metadata schema.
- `python main.py --report --dataset my_data clone`
  Clone repositories discovered in the harvested Galaxy metadata.
- `python main.py --dataset my_data extract-git-metadata`
  Extract git repository metadata, i.e. commits and tags, from the git repositories.
- `python main.py --dataset my_data extract-structural-models`
  Extract structural models for each git tag that matches the semantic versioning format.
- `python main.py --dataset my_data extract-structural-models --commits`
  Alternative to the previous command, but extract models for each commit rather than each version.
- `python main.py --dataset my_data extract-structural-diffs`
  Distil changes between the structural model versions.

Hint: Commands can be mixed and omitted quite flexibly. For example, executing all phases of the pipeline could be executed in one command as such:
- `python main.py --report --progress --dataset my_data extract-structural-diffs`
