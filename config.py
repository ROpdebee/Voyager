"""Configurations."""

from pathlib import Path

import click

from util.config import Config, Option


class MainConfig(Config):
    """Global configurations for all commands."""

    report: Option[bool] = Option(
            'Output a report after a task has completed.', default=False)
    progress: Option[bool] = Option(
            'Print the progress of a task.', default=False)
    dataset: Option[str] = Option(
            'The name of the dataset to create/use', final=True)
    output: Option[Path] = Option(
            'Output directory', click_type=click.Path(
                file_okay=False, dir_okay=True, writable=True,
                resolve_path=True),
            converter=lambda p: Path(str(p)),
            default=Path('data'), final=True)
    force: Option[bool] = Option(
            'Force regeneration of cached results', default=False)

    @property
    def output_directory(self) -> Path:
        """Get the output directory."""
        return self.output / self.dataset


class ExtractRoleMetadataConfig(MainConfig):
    """Configuration for role metadata extraction."""

    count: Option[int] = Option('Top number of roles to keep', required=False)


class CloneConfig(MainConfig):
    """Configuration for cloning."""

    resume: Option[bool] = Option(
            'Resuming cloning from a previous run.', default=True)


class ExtractStructuralModelsConfig(MainConfig):
    """Configuration for structural model extraction."""

    commits: Option[bool] = Option(
            'Extract a structural model for each commit. If disabled, extracts for semantic versions only.', default=False)

class DiffConfig(MainConfig):
    """Configuration for structural diffing."""
    dump_changes: Option[bool] = Option(
            'Dump the extracted changes to the reports directory.',
            default=False)
