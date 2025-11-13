# Synthea Demographics Configuration for ILS

## Overview

This document describes how to generate synthetic patient data with demographics appropriate for ILS (Integrated Long-term Services) populations, which focus on Medicare, Medicaid, and Dual-Eligible markets with emphasis on long-term care services.

## Target Demographics

ILS serves:
- **Older Adults (65+)**: ~80% of population
  - 65-74 years: ~25%
  - 75-84 years: ~30%
  - 85-100 years: ~25%
- **Younger Adults with Disabilities (18-64)**: ~20% of population
  - Special needs populations
  - Medicaid and Dual-Eligible beneficiaries

## Quick Start

### Generate ILS-Specific Demographics

Use the `generate_ils_demographics.py` script to automatically create the appropriate demographic mix:

```bash
# Generate 100 patients with ILS demographics in Miami, FL
python generate_ils_demographics.py --total-patients 100 --city Miami --state Florida

# Custom output directory
python generate_ils_demographics.py --total-patients 200 --output-dir synthea/custom_cohort

# Reproducible generation with seed
python generate_ils_demographics.py --total-patients 100 --seed 12345 --city Miami --state Florida
```

### Manual Generation by Age Cohort

If you need fine-grained control, use the base script with age parameters:

```bash
# Elderly Medicare patients (80-95)
python generate_synthea_ndjson.py --num-patients 50 --min-age 80 --max-age 95 \
    --city Miami --state Florida --output-dir synthea/elderly

# Young adults with disabilities (18-40)
python generate_synthea_ndjson.py --num-patients 20 --min-age 18 --max-age 40 \
    --city Miami --state Florida --output-dir synthea/young_disabled

# Standard Medicare eligible (65-75)
python generate_synthea_ndjson.py --num-patients 30 --min-age 65 --max-age 75 \
    --city Miami --state Florida --output-dir synthea/medicare_standard
```

## Demographic Distribution

### `generate_ils_demographics.py` Distribution

| Age Range | Category | Percentage | Patient Type |
|-----------|----------|------------|--------------|
| 18-44 | Young Adults with Disabilities | 8% | Medicaid, Special Needs |
| 45-64 | Middle-Aged Adults with Disabilities | 12% | Medicaid, Dual-Eligible |
| 65-74 | Young-Old Medicare | 25% | Medicare |
| 75-84 | Old Medicare | 30% | Medicare, Early LTC |
| 85-100 | Oldest-Old LTC Focus | 25% | Medicare, Long-Term Care |

### Rationale

This distribution reflects:
1. **Medicare Focus**: 80% of patients are 65+, matching Medicare eligibility
2. **Long-Term Care**: 55% are 75+, reflecting higher LTC needs
3. **Disability Services**: 20% under 65, representing younger Medicaid/Dual-Eligible beneficiaries
4. **Oldest-Old Emphasis**: 25% are 85+, matching intensive LTC requirements

## Command Reference

### `generate_ils_demographics.py`

```bash
python generate_ils_demographics.py [OPTIONS]

Options:
  --total-patients, -t INT    Total patients to generate (default: 100)
  --output-dir PATH           Output directory (default: synthea/ils_demographics)
  --city TEXT                 City name (e.g., 'Miami')
  --state TEXT                State name (e.g., 'Florida')
  --version TEXT              Synthea version (default: 3.4.0)
  --seed INT                  Base seed for reproducibility
```

### `generate_synthea_ndjson.py` (Enhanced)

```bash
python generate_synthea_ndjson.py [OPTIONS]

New Age Control Options:
  --min-age INT               Minimum age for generated patients
  --max-age INT               Maximum age for generated patients
                             (both required when using age filtering)

Other Options:
  --num-patients, -p INT      Number of patients (default: 25)
  --output-dir PATH           Output directory (default: synthea_ndjson)
  --city TEXT                 City name
  --state TEXT                State name
  --seed INT                  Seed for deterministic runs
  --version TEXT              Synthea version (default: 3.4.0)
```

## Examples

### Example 1: Small Test Cohort (50 patients)

```bash
python generate_ils_demographics.py \
  --total-patients 50 \
  --city Miami \
  --state Florida \
  --output-dir synthea/test_cohort
```

### Example 2: Large Production Cohort (500 patients)

```bash
python generate_ils_demographics.py \
  --total-patients 500 \
  --city Miami \
  --state Florida \
  --seed 42 \
  --output-dir synthea/production
```

### Example 3: Specific Age Group Only

```bash
# Generate only oldest-old patients (85-100)
python generate_synthea_ndjson.py \
  --num-patients 100 \
  --min-age 85 \
  --max-age 100 \
  --city Miami \
  --state Florida \
  --output-dir synthea/oldest_old
```

## Output Structure

Both scripts generate FHIR R4 NDJSON files:

```
synthea/ils_demographics/
├── Patient.ndjson
├── Encounter.ndjson
├── Condition.ndjson
├── Observation.ndjson
├── MedicationRequest.ndjson
├── Procedure.ndjson
├── CarePlan.ndjson
├── Claim.ndjson
└── ... (other FHIR resources)
```

Each `.ndjson` file contains one FHIR resource per line.

## Tips

1. **Reproducibility**: Always use `--seed` for reproducible data generation
2. **Location Matters**: City/State affect demographics, provider networks, and disease prevalence
3. **Multiple Runs**: The ILS demographics script automatically combines multiple age cohorts
4. **File Size**: 100 patients ≈ 10-20 MB of NDJSON data
5. **Git Ignore**: The `synthea/` directory is already in `.gitignore`

## Technical Notes

- Uses Synthea 3.4.0 by default
- FHIR R4 compliant
- Synthea JAR cached in `.synthea_cache/`
- Each patient includes full medical history with encounters, conditions, medications, etc.
- Age-specific disease modules automatically apply based on patient age
