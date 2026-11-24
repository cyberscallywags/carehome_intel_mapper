# Care home data

`uv run task ingest` writes `carehomes.json` here: the care homes read from the Care Quality
Commission's public data. The API loads it when it starts; until it exists the API serves
made-up sample homes. Everything in this folder except this file is ignored by git, so it is
also a convenient place to keep the spreadsheet you downloaded from CQC.

See the project's Care home data page in the docs for where the data comes from.
