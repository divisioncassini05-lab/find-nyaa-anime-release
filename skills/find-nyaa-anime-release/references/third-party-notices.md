# Third-party sources and licenses

## Shipped parser dependencies (unmodified Python source)

| Component | Pinned distribution | Role | License |
| --- | --- | --- | --- |
| [Aniparse](https://github.com/MeGaNeKoS/Aniparse) | PyPI `aniparse==2.0.0` | Production hypotheses through our adapter | MPL-2.0 |
| [Anitopy](https://github.com/igorcmoura/anitopy) | PyPI `anitopy==2.1.1` | Offline comparison only | MPL-2.0 |

Original package metadata, source and LICENSE files remain under `scripts/parser_dependencies`, including distribution `RECORD` hashes. `requirements-parsers.txt` pins versions. Our adapter is separate; no package source is patched. The installation manifest records deployed file SHA-256 hashes. MPL notices and source must be retained when redistributing these files.

## Shipped identity data

The `data/identity_catalog.json` subset is derived from [anime-offline-database release 2026-27](https://github.com/manami-project/anime-offline-database/releases/tag/2026-27), source date 2026-07-04. Source payload SHA-256: `395be786fb2f98f1fca9e963911b9332110098a080e7e2569902bbc5641d1a41`. It contains identity/aliases for 13 pre-existing tracked AniList IDs, not release or schedule assertions.

License: ODbL 1.0 + DbCL 1.0; full upstream notice is in `data/AOD-LICENSE.txt`, taken from commit `96da26358c8e599a9c076818aee247c68cb69401`. The source and transformation are available via `build_offline_snapshot.py` and `offline_identity.py`. Preserve attribution and applicable database license obligations for redistribution.

## Architecture references only — no code copied

- [Sonarr ReleaseSearchService](https://github.com/Sonarr/Sonarr/blob/5352e16d95a785aee1b760a7593857350c6a94ec/src/NzbDrone.Core/IndexerSearch/ReleaseSearchService.cs), `v5-develop` snapshot `5352e16d95a785aee1b760a7593857350c6a94ec`, GPL-3.0: work/alias/numbering planning before indexer queries.
- [AutoBangumi tokenizer resolver](https://github.com/EstrellaXD/Auto_Bangumi/blob/fd798519fee7efacfe2d64897e0e8b04f0cee2f2/backend/src/module/parser/analyser/tokenizer/resolver.py), `main` snapshot `fd798519fee7efacfe2d64897e0e8b04f0cee2f2`, MIT: retain evidence, positions and conflicts rather than treating rule order as proof. Its tokenizer is preview, not adopted wholesale.
- [Anime-Lists mapping schema](https://github.com/Anime-Lists/anime-lists/tree/6953cdaff5d128a068c98432ec3efc5aba909d67), examined snapshot `6953cdaff5d128a068c98432ec3efc5aba909d67`: explicit AniDB-to-TVDB mapping fields. No repository license was identified in the reviewed material. No upstream code/XML dataset is shipped; tests use synthetic XML. The importer handles user-supplied, appropriately licensed data only.

Repository-head references are dated research snapshots, not parser dependency pins. Runtime Aniparse/Anitopy use the exact PyPI distributions above. Prowlarr, Sonarr services, and AutoBangumi services are not installed or started.
