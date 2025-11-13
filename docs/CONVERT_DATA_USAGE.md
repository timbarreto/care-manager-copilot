# FHIR $convert-data Operation Guide

## Overview

The `$convert-data` operation is an Azure FHIR service capability that converts legacy healthcare data formats into FHIR-compliant resources. Unlike the `$import` operation which bulk-loads existing FHIR data from blob storage, `$convert-data` performs real-time transformation of non-FHIR formats during ingestion.

### Purpose and Use Cases

- **Legacy System Integration**: Convert HL7v2 messages from hospital information systems
- **Clinical Document Import**: Transform C-CDA documents into FHIR resources
- **Data Migration**: Modernize historical data from older formats
- **Interoperability**: Bridge between systems using different healthcare data standards

### Comparison with `$import`

| Feature | `$convert-data` | `$import` |
|---------|-----------------|-----------|
| Input Format | HL7v2, C-CDA, JSON | FHIR NDJSON only |
| Storage Required | No (inline data) | Yes (blob storage) |
| Processing Mode | Synchronous | Asynchronous |
| Volume | Single messages | Bulk operations |
| Template Required | Yes | No |
| RBAC | FHIR Data Contributor | FHIR Data Contributor + Storage Blob Data Contributor |

## Supported Input Formats

### HL7 Version 2.x

Common message types supported through default templates:

- **ADT_A01**: Patient admission
- **ADT_A04**: Patient registration
- **ADT_A08**: Patient update
- **ORU_R01**: Observation results (lab, radiology)
- **ORM_O01**: Order messages
- **SIU_S12**: Schedule information

### C-CDA (Consolidated Clinical Document Architecture)

Clinical documents including:

- Continuity of Care Documents (CCD)
- Discharge Summaries
- Progress Notes
- Consultation Notes

### JSON

Custom JSON formats can be converted using user-defined templates.

### FHIR

FHIR resources can be validated and normalized through the converter.

### Template Collections

Templates define the transformation logic from source format to FHIR resources:

- **Default Templates**: `microsofthealth/fhirconverter:default`
- **Custom Templates**: Can be hosted in Azure Container Registry
- **Template Types**: Liquid templates that map source data to FHIR resource structures

## Sample Data Generation Approach

### HL7v2 Message Generation Strategy

Sample HL7v2 messages are generated using a structured approach that ensures valid message format while allowing dynamic content:

#### Message Structure

1. **Segment Definition**: Each message type consists of required and optional segments
2. **Field Population**: Fields are populated with realistic test data following HL7v2 data types
3. **Timestamp Generation**: Dynamic timestamps ensure messages represent current context
4. **Identifier Management**: Consistent patient and resource identifiers across messages

#### Generation Method

The Python-based generation approach includes:

- **Template-based construction**: Pre-defined message templates for each type
- **Dynamic field injection**: Runtime population of timestamps, identifiers, and variable data
- **Validation**: Segment structure verification before conversion
- **Encoding compliance**: Proper use of separators (`|`, `^`, `~`, `\`, `&`)

#### Message Types and Segments

**ADT_A01 (Patient Admission)**:
- MSH: Message Header (sending/receiving systems, timestamp)
- PID: Patient Identification (demographics, identifiers)
- PV1: Patient Visit (location, attending physician, visit number)

**ORU_R01 (Lab Results)**:
- MSH: Message Header
- PID: Patient Identification
- OBR: Observation Request (order information)
- OBX: Observation Result (individual test results with values)

### Data Realism Considerations

Generated samples should reflect realistic healthcare scenarios:

- **Patient demographics**: Age-appropriate conditions and treatments
- **Clinical validity**: Lab values within plausible ranges
- **Temporal consistency**: Visit dates before result dates
- **Reference integrity**: Patient IDs match across related messages

## Conversion Process Architecture

### Authentication Flow

1. **Credential Acquisition**: Uses `DefaultAzureCredential` from Azure Identity SDK
2. **Token Scope**: Requests token for `{FHIR_URL}/.default` scope
3. **Bearer Token**: Included in Authorization header for API requests
4. **Token Refresh**: Automatically handled by credential provider

### API Request Structure

The `$convert-data` operation accepts a FHIR Parameters resource:

**Required Parameters**:
- `inputData`: The source data as a string
- `inputDataType`: Format identifier (Hl7v2, Ccda, Json, Fhir)
- `templateCollectionReference`: Container image or default templates
- `rootTemplate`: Specific template name for the message type

**Optional Parameters**:
- `jsonDeserializationTreatDatesAsStrings`: For JSON input handling

### Template Selection and Mapping

**Default Template Mapping**:
- HL7v2 ADT messages → Patient, Encounter resources
- HL7v2 ORU messages → Observation, DiagnosticReport resources
- C-CDA documents → Composition, multiple clinical resources

**Template Resolution**:
1. Identify message type from input data
2. Select corresponding root template
3. Apply template transformations
4. Generate FHIR resource bundle

### Response Handling

**Success Response (HTTP 200)**:
- Returns FHIR Bundle resource
- Contains converted resources with generated IDs
- Preserves source identifiers in appropriate fields
- Includes metadata about conversion

**Error Responses**:
- HTTP 400: Invalid input data or template issues
- HTTP 401: Authentication failure
- HTTP 403: Insufficient permissions
- HTTP 500: Server-side conversion errors

## RBAC Requirements

### Required Role

**FHIR Data Contributor**: Grants permission to read and write FHIR data, including calling operations like `$convert-data`.

### Role Assignment

Assign to the identity running the conversion:

- **User Principal**: For local development/testing
- **Service Principal**: For automated processes
- **Managed Identity**: For Azure-hosted applications

### Permission Scope

The role must be assigned at the FHIR service resource level:

```
/subscriptions/{subscription-id}/resourceGroups/{resource-group}/providers/Microsoft.HealthcareApis/workspaces/{workspace}/fhirservices/{service}
```

### Comparison with $import Permissions

**$convert-data**:
- FHIR Data Contributor only

**$import**:
- FHIR Data Contributor (to call the operation)
- Storage Blob Data Contributor (for the FHIR service managed identity)
- System-assigned managed identity enabled on FHIR service

The `$convert-data` operation is simpler as it does not require storage account access or managed identity configuration.

## Integration Workflow

### End-to-End Process

1. **Data Preparation**
   - Generate or receive source data (HL7v2/C-CDA)
   - Validate message structure
   - Identify appropriate template

2. **Authentication**
   - Acquire Azure credentials
   - Obtain FHIR service access token
   - Prepare authorization headers

3. **Conversion Request**
   - Construct Parameters resource
   - POST to `{FHIR_URL}/$convert-data`
   - Include Prefer: respond-async if supported

4. **Response Processing**
   - Parse returned Bundle resource
   - Extract individual FHIR resources
   - Handle references between resources

5. **Optional: Persistence**
   - POST converted resources to FHIR server
   - Or use as transient data for analytics
   - Or export to other systems

### Error Handling

**Validation Failures**:
- Check segment structure in HL7v2 messages
- Verify required fields are present
- Ensure data type compliance

**Conversion Errors**:
- Review template compatibility
- Check for unsupported segments or fields
- Validate source data encoding

**Authentication Issues**:
- Verify RBAC role assignment
- Confirm token scope matches FHIR URL
- Check Azure credentials are current

### Output Processing Options

**Direct Ingestion**:
- POST each resource from Bundle to FHIR server
- Maintain reference integrity
- Handle resource dependencies

**Batch Processing**:
- Aggregate multiple conversions
- Submit as FHIR batch/transaction
- Optimize for throughput

**Data Export**:
- Extract converted resources
- Transform to other formats if needed
- Integration with downstream systems

## References

### Azure Documentation

- [Azure FHIR Service Documentation](https://learn.microsoft.com/azure/healthcare-apis/fhir/)
- [FHIR Converter](https://github.com/microsoft/FHIR-Converter)
- [Azure Health Data Services](https://learn.microsoft.com/azure/healthcare-apis/)

### HL7 Specifications

- [HL7 Version 2 Product Suite](https://www.hl7.org/implement/standards/product_brief.cfm?product_id=185)
- [HL7v2 Message Structure](https://www.hl7.org/implement/standards/product_brief.cfm?product_id=185)

### Template Resources

- [FHIR Converter Templates Repository](https://github.com/microsoft/FHIR-Converter/tree/main/data/Templates)
- [Liquid Template Language](https://shopify.github.io/liquid/)
- [Custom Template Development Guide](https://github.com/microsoft/FHIR-Converter/blob/main/docs/TemplateManagementCLI.md)

### Related Documentation in this Repository

- `README.md`: Project overview and setup
- `SYNTHEA_DEMOGRAPHICS.md`: Synthetic data generation for testing
- `scripts/load_synthea_data_bulk.py`: Bulk FHIR import reference implementation
