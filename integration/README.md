# HL7v2 Integration with $convert-data

This directory contains tools for testing Azure FHIR's `$convert-data` operation with sample HL7v2 data.

## Contents

- **`sample_hl7v2_data.py`**: Sample HL7v2 messages for 2 patients
- **`convert_and_load_hl7v2.py`**: Script to convert and load data using `$convert-data`
- **`README.md`**: This file

## Sample Data

The sample data includes realistic HL7v2 messages for two patients:

### Patient 1: John Doe (65-year-old male with cardiac issues)
- **ADT_A01**: Hospital admission to cardiology unit
- **ORU_R01**: Complete Blood Count (CBC) lab results with elevated troponin

### Patient 2: Jane Smith (72-year-old female with diabetes)
- **ADT_A01**: Hospital admission to endocrinology unit
- **ORU_R01**: Basic Metabolic Panel (BMP) with elevated glucose and HbA1c

Each message includes:
- Proper HL7v2 segment structure (MSH, EVN, PID, PV1, OBR, OBX)
- Dynamic timestamps
- Realistic clinical values
- Consistent patient identifiers

## Prerequisites

### Required Environment Variables

Set in your `.env` file or environment:

```bash
FHIR_URL=https://your-workspace-service.fhir.azurehealthcareapis.com
```

### Required RBAC Role

Your user or service principal must have:
- **FHIR Data Contributor** role on the FHIR service

To check/assign:

```bash
# Get your user ID
MY_USER_ID=$(az ad signed-in-user show --query id -o tsv)

# Assign role
az role assignment create \
  --role "FHIR Data Contributor" \
  --assignee $MY_USER_ID \
  --scope "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${FHIR_RESOURCE_GROUP}/providers/Microsoft.HealthcareApis/workspaces/${FHIR_WORKSPACE_NAME}/fhirservices/${FHIR_SERVICE_NAME}"
```

## Usage

### View Sample Data

Display the HL7v2 messages:

```bash
python integration/sample_hl7v2_data.py
```

### Convert and Load Data

#### Convert All Patients (Dry-run)

Test conversion without posting to FHIR server:

```bash
python integration/convert_and_load_hl7v2.py --dry-run
```

#### Convert and Load All Patients

Convert and POST resources to FHIR server:

```bash
python integration/convert_and_load_hl7v2.py
```

#### Convert Single Patient

Process only one patient's data:

```bash
# Patient 1 only
python integration/convert_and_load_hl7v2.py --patient-id PAT001

# Patient 2 only
python integration/convert_and_load_hl7v2.py --patient-id PAT002
```

#### Save Converted Resources to Files

Save FHIR bundles to JSON files:

```bash
python integration/convert_and_load_hl7v2.py --output-dir ./output --dry-run
```

#### Verbose Output

Display detailed conversion information:

```bash
python integration/convert_and_load_hl7v2.py --verbose
```

## Command-Line Options

```
--fhir-url URL              FHIR service URL (default: from FHIR_URL env var)
--patient-id {PAT001,PAT002,all}  Which patient to convert (default: all)
--dry-run                   Convert but don't POST to FHIR server
--template-collection REF   Template collection (default: microsofthealth/fhirconverter:default)
--output-dir DIR            Save converted resources as JSON files
--verbose                   Display detailed output
```

## Expected Results

When running successfully, the script will:

1. **Convert 4 HL7v2 messages** (2 per patient)
   - 2 x ADT_A01 → Patient + Encounter resources
   - 2 x ORU_R01 → Observation + DiagnosticReport resources

2. **Create approximately 8-12 FHIR resources**:
   - 2 Patient resources
   - 2 Encounter resources
   - 8-10 Observation resources (lab results)
   - 2 DiagnosticReport resources

3. **Display summary statistics**:
   ```
   Total messages processed:    4
   Successfully converted:      4
   Conversion failures:         0

   Resource types converted:
     - Patient: 2
     - Encounter: 2
     - Observation: 10
     - DiagnosticReport: 2

   FHIR Server Upload:
     Resources created:         16
     Upload failures:           0
   ```

## Troubleshooting

### Authentication Errors

```
Error: 401 Unauthorized
```

**Solution**: Ensure you're logged in to Azure and have FHIR Data Contributor role:

```bash
az login
az account show
```

### Conversion Errors

```
Conversion failed: 400 Bad Request
```

**Possible causes**:
- Invalid HL7v2 message structure
- Missing required segments
- Template not found

**Solution**: Run with `--verbose` to see detailed error messages

### Template Issues

```
Template 'ADT_A01' not found
```

**Solution**: Verify template collection reference:

```bash
python integration/convert_and_load_hl7v2.py \
  --template-collection microsofthealth/fhirconverter:default
```

## Verifying Loaded Data

After successfully loading, query the FHIR server to verify:

```bash
# List patients
python scripts/query_fhir_data.py --resource-type Patient --count 10

# Get specific patient data
python scripts/query_fhir_data.py --patient-id <patient-id>

# Query observations
python scripts/query_fhir_data.py --resource-type Observation --count 20
```

## Next Steps

- Review converted FHIR resources using `--output-dir`
- Customize sample data in `sample_hl7v2_data.py` for your use cases
- Add additional message types (ORM, SIU, etc.)
- Integrate with your own HL7v2 message sources

## Related Documentation

- `docs/CONVERT_DATA_USAGE.md`: Technical reference for `$convert-data` operation
- `README.md`: Main project documentation
- `SYNTHEA_DEMOGRAPHICS.md`: Bulk FHIR data loading with Synthea
