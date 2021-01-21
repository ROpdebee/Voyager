"""Main entry point."""

from click import BadParameter

import pipeline
import pipeline.base

from config import MainConfig
from util.cli import register_command, register_subcommand
from migrations import perform_migrations


@register_command
def main(config: MainConfig) -> None:
    """Ansible Semantic Versioning tool pipeline."""
    # Let errors be handled by Click
    try:
        config.output_directory.mkdir(parents=True, exist_ok=True)
        print(f'Setting output directory to {config.output_directory}')
        # Check if migrations are necessary and perform them
        # perform_migrations(config.output_directory)
    except BadParameter:
        pass


# Register all commands as stages
for stage_type, config_type in pipeline.base.STAGES.items():
    register_subcommand(main, config_type, stage_type)

# TODO(ROpdebee): Would be cool to include a requires=... kw in the command
#                 decorator so that the user doesn't have to type out a very
#                 long command lines like `tool.py discover --count=100 clone
#                 analyze-commit-counts analyze-commit-sizes analyze-changes
#                 ...` but can just state what they want and the tool figures
#                 out and runs the prerequisites (e.g.,
#                 tool.py --dataset test analyze-commit-counts automatically
#                 runs discover and clone). Should also fail when required
#                 input is missing (e.g. dataset hasn't been discovered yet,
#                 we need a --count argument). Could prompt for those values,
#                 but that could become too complex when we have to deal with
#                 multiple types. Also make sure that stages can be run in
#                 "cache-only" mode so it fails when the cache does not exist
#                 and it would normally access configuration values that
#                 haven't been parsed. (optional kwarg when calling the
#                 decorator?)


if __name__ == '__main__':  # pragma: no branch
    main(obj=None)
