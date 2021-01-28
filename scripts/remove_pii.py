"""Anonymise the collected data, remove or obfuscate PII."""

import yaml
import sys
from pathlib import Path
import hashlib
import tqdm

from yaml import CLoader as Loader, CDumper as Dumper

assert __name__ == '__main__', 'Can only run this as script, not module'

dataset_path = Path(sys.argv[1])
anon_path = dataset_path.with_name(dataset_path.name + '_anon')

# Galaxy metadata
gm = dataset_path / 'GalaxyMetadata'
gm_idx = yaml.load((gm / 'index.yaml').read_text())
(anon_path / 'GalaxyMetadata').mkdir(exist_ok=True, parents=True)
for name, f in tqdm.tqdm(gm_idx.items()):
    if name == 'User':
        continue

    if name == 'Namespace':
        namespaces = yaml.load((gm / f).read_text(), Loader=Loader)
        for namespace in namespaces.values():
            for attr in ('avatar_url', 'company_name', 'email', 'location'):
                del namespace[attr]
        (anon_path / 'GalaxyMetadata' / f).write_text(yaml.dump(namespaces, Dumper=Dumper))

    elif name == 'ProviderNamespace':
        pns = yaml.load((gm / f).read_text(), Loader=Loader)
        for pn in pns.values():
            for attr in ('avatar_url', 'company_name', 'email', 'location', 'display_name'):
                try:
                    del pns[attr]
                except KeyError:
                    pass
        (anon_path / 'GalaxyMetadata' / f).write_text(yaml.dump(pns, Dumper=Dumper))

    elif name == 'Role':
        roles = yaml.load((gm / f).read_text(), Loader=Loader)
        for r in roles.values():
            try:
                del r['company']
            except KeyError:
                pass
        (anon_path / 'GalaxyMetadata' / f).write_text(yaml.dump(roles, Dumper=Dumper))

    else:
        (anon_path / 'GalaxyMetadata' / f).write_text((gm / f).read_text())

(anon_path / 'GalaxyMetadata' / 'index.yaml').write_text(yaml.dump({name: f for name, f in gm_idx.items() if name != 'User'}, Dumper=Dumper))

# Repository metadata
rm = dataset_path / 'RepositoryMetadata'
rm_idx = yaml.load((rm / 'index.yaml').read_text())
anon_rm = anon_path / 'RepositoryMetadata'
for rid, mpath in tqdm.tqdm(rm_idx.items()):
    anon_path = anon_rm / mpath
    anon_path.parent.mkdir(exist_ok=True, parents=True)
    content = yaml.load((rm / mpath).read_text(), Loader=Loader)
    for commit in content['commits']:
        for attr in ('author_email', 'author_name', 'committer_email', 'committer_name'):
            if commit[attr] is not None:
                commit[attr] = hashlib.sha1(commit[attr].encode()).hexdigest()
    for tag in content['tags']:
        for attr in ('tagger_email', 'tagger_name'):
            if tag[attr] is not None:
                tag[attr] = hashlib.sha1(tag[attr].encode()).hexdigest()

    anon_path.write_text(yaml.dump(content, Dumper=Dumper))
