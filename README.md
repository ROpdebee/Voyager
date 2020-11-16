# SCARE: Structural Changes of Ansible Role Evolution

Tool to discover and collect a dataset of Ansible roles from [Ansible Galaxy](https://galaxy.ansible.com) and extract structural changes between versions of a role.

## Requirements
- Python >= 3.8
- [Poetry](https://python-poetry.org/docs/#installation)

## Installing
- `cd /path/to/ansible_semver`
- `poetry install`
- (Optional) Run the tests: `poetry run -- python -m pytest`

## Running
- `poetry run -- python main.py`
- Check the help text.

### Examples
Assuming `poetry shell` is spawned.

- `python main.py --progress --report --dataset my_data discover --count=200`
  Create a new dataset named `my_data` of the 200 most popular Ansible roles. Show progress while searching for roles, include a report on the gathered roles.
- `python main.py --dataset my_data clone --progress extract-versions --report`
  Clone the repositories of the previously created dataset `my_data` with a progress bar. Extract the versions from each of these repositories, and include a report of the extraction.
- `python main.py --report --dataset my_data analyse-versions`
  Analyze the versions in the dataset and create a report.

Hint: Commands can be mixed and omitted quite flexibly. The previous three commands can be squashed into a one-liner in many ways, e.g.:
- `python main.py --report --progress --dataset my_data discover --count=200 analyse-versions`
  This will discover roles and analyze the versions in one go. It will intermediately clone the repositories and extract the versions automatically, since these are required inputs to the next stages.

## Tests
*Note:* The commands in this section assume that the `PYTHONPATH` is correctly set for the Poetry virtual environment. You can ensure this is the case in one of two ways:

1. Prepend `poetry run --` to each command, e.g., `poetry run -- python -m pytest`.
2. (Easier) Spawn a shell in the virtual environment using `poetry shell` and run the commands directly.

*Note:* Always run `python -m pytest` instead of a bare `pytest` to make sure the tests are discovered correctly.

### Unit Tests
Run `python -m pytest` in the main source directory to run the unit tests. It will automatically generate a coverage report. You can convert this report to HTML by running `coverage html`. The HTML report is then generated under the `htmlcov` directory.

### Smoke Tests
The smoke tests verify that the program can be executed and seems to behave normally under normal usage scenarios. They execute the typical commands and mainly verify the command's return code. By default, the smoke tests aren't run during normal testing. They can be enabled in one of two ways:

- `python -m pytest --smoke`, to run the smoke tests alongside the unit tests.
- `python -m pytest -m smoke`, to run only the smoke tests.

### Integration Tests
The unit tests verify most of the interactions with third-party APIs (e.g., Ansible Galaxy API) using cached responses which were recorded at the time the test was first written. The integration tests, however, don't use cached responses and perform actual requests. Since these are slower, they are disabled by default, and can be enabled through one of two ways:

- `python -m pytest --integration`, to run the integration tests alongside the unit tests.
- `python -m pytest -m integration`, to run only the integration tests.

Note that the integration tests may fail at any point in time in case of changes or problems with the third-party API(s). Moreover, the integration tests are fairly shallow and simply verify whether API requests can be made, parsed, and processed correctly, but do not check whether the output data is actually correct, since most of the API data is volatile.

### Running Multiple Test Suites
To enable multiple tests, often it suffices to merge the command line options shown above. For example, to run unit tests, smoke tests, AND integration tests in one go, the following command will suffice: `python -m pytest --smoke --integration`.

To run multiple kinds of tests, but exclude the unit tests, you need to enable only the marks that you want to run. For example, to run smoke tests and integration tests, but NO unit tests, run `python -m pytest -m 'smoke and integration'`.
