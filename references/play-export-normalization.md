# Play Export Normalization

## Purpose

Different Play/ASO tools export different column names.  
`aso_play_export_normalizer.py` converts those files into the standard schema expected by:

- `scripts/aso_play_competitor_import_analyzer.py`

## Standard Output Schema

- `app_name`
- `package_name`
- `developer`
- `category`
- `locale`
- `country`
- `short_description`
- `full_description`
- `avg_rating`
- `rating_count`
- `installs`
- `price`
- `url`

## Recommended Flow

1. Normalize raw export:

```bash
python scripts/aso_play_export_normalizer.py \
  --input assets/play-raw-export-template.csv \
  --output assets/play-competitor-import-normalized.csv \
  --print-columns
```

2. If source headers are unusual, apply explicit mapping:

```bash
python scripts/aso_play_export_normalizer.py \
  --input assets/play-raw-export-template.csv \
  --mapping-json assets/play-export-mapping-template.json \
  --output assets/play-competitor-import-normalized.csv
```

3. Run Play competitor analyzer:

```bash
python scripts/aso_play_competitor_import_analyzer.py \
  --input assets/play-competitor-import-normalized.csv \
  --app-scope android_only \
  --output-dir out \
  --prefix play_competitors
```

## Strict Mode

Use `--strict` to fail fast when core columns cannot be mapped.

